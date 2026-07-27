import json
import os
import io
import time
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
import google.generativeai as genai
import urllib3
from urllib.parse import urlparse, urlunparse

# إخفاء تحذيرات شهادات الأمان SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

DATA_FILE = 'state.json'

# هيدرز قوية لتفادي الحظر مع منع الكاش بدون تغيير الرابط
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7,ar;q=0.6',
    'Cache-Control': 'max-age=0, no-cache, no-store, must-revalidate',
    'Pragma': 'no-cache'
}

BLACKLIST_KEYWORDS = [
    'contact', 'accueil', 'presentation', 'historique', 'mot du doyen', 
    'mot du directeur', 'organigramme', 'emplacement', 'archive', 'galerie',
    'اتصل بنا', 'الرئيسية', 'تقديم', 'الهيكلة'
]

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False
    }
    try:
        requests.post(url, json=payload, timeout=10, verify=False)
    except Exception as e:
        print(f"Error sending to Telegram: {e}", flush=True)

def extract_text_from_pdf(pdf_url):
    try:
        res = requests.get(pdf_url, headers=DEFAULT_HEADERS, timeout=12, verify=False)
        if res.status_code == 200:
            pdf_file = io.BytesIO(res.content)
            reader = PdfReader(pdf_file)
            text = ""
            for page in reader.pages[:2]:
                text += page.extract_text() or ""
            return text[:1500]
    except Exception as e:
        print(f"Error reading PDF {pdf_url}: {e}", flush=True)
    return None

def summarize_with_ai(text_content):
    if not GEMINI_API_KEY or not text_content:
        return None
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "أنت مساعد توجيه جامعي بالمغرب. قم بتلخيص هذا البلاغ للطلبة في 3 نقاط موجزة باللغة العربية:\n"
            "1. المضمون والهدف.\n"
            "2. آخر أجل (إن وجد).\n"
            "3. رابط التقديم.\n\n"
            f"النص:\n{text_content}"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini AI Error: {e}", flush=True)
        return None

def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading state.json: {e}", flush=True)
    return {}

def save_state(state):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def clean_url(url):
    """تنظيف الرابط وإزالة التجزئة # مع الحفاظ على متغيرات URL"""
    parsed = urlparse(url.strip())
    cleaned = urlunparse((
        parsed.scheme or 'https',
        parsed.netloc.lower(),
        parsed.path.rstrip('/'),
        parsed.params,
        parsed.query,
        ''
    ))
    return cleaned

def is_valid_announcement(text, href):
    combined = (text + " " + href).lower()
    if any(black in combined for black in BLACKLIST_KEYWORDS):
        return False
        
    keywords = ['.pdf', 'avis', 'concours', 'annonce', 'communique', 'actualite', 'إعلان', 'مباراة', 'بلاغ', 'جديد']
    return any(kw in combined for kw in keywords)

def check_sites():
    if not os.path.exists('sites.json'):
        print("sites.json file missing!", flush=True)
        return

    with open('sites.json', 'r', encoding='utf-8') as f:
        sites = json.load(f)
    
    state = load_state()
    failed_sites = []

    for site_id, site_info in sites.items():
        print(f"Checking {site_info['name']}...", flush=True)
        try:
            # زيادة Timeout إلى 15 ثانية لضمان استجابة المواقع البطيئة
            response = requests.get(site_info['url'], headers=DEFAULT_HEADERS, timeout=15, verify=False)
            
            if response.status_code != 200:
                print(f"Skipping {site_info['name']}: HTTP Status {response.status_code}", flush=True)
                failed_sites.append(f"{site_info['name']} (كود: {response.status_code})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                text = " ".join(a.text.split()) or "إعلان / بلاغ جديد"
                
                if is_valid_announcement(text, href):
                    if href.startswith('/'):
                        href = site_info['url'].rstrip('/') + href
                    elif not href.startswith('http'):
                        href = site_info['url'].rstrip('/') + '/' + href
                    
                    c_url = clean_url(href)
                    if not any(clean_url(l['url']) == c_url for l in links):
                        links.append({"text": text, "url": href})

            # أخذ أول 15 رابط فقط لتفادي جلب الأرشيف القديم
            links = links[:15]

            if not links:
                continue

            # التسجيل المبدئي للرابط إذا كان الموقع جديداً فـ state.json
            if site_id not in state or not state[site_id]:
                state[site_id] = [clean_url(l['url']) for l in links]
                save_state(state)
                print(f"Silently seeded {len(links)} links for {site_info['name']}", flush=True)
                continue

            existing_urls = set(state[site_id])
            new_links = [l for l in links if clean_url(l['url']) not in existing_urls]

            for link in new_links:
                print(f"New announcement found: {link['text']}", flush=True)
                summary_text = ""
                
                if '.pdf' in link['url'].lower():
                    pdf_text = extract_text_from_pdf(link['url'])
                    if pdf_text:
                        ai_summary = summarize_with_ai(pdf_text)
                        if ai_summary:
                            summary_text = f"\n\n📝 <b>ملخص البلاغ (بالذكاء الاصطناعي):</b>\n{ai_summary}"

                msg = (
                    f"🚨 <b>إعلان جديد!</b>\n\n"
                    f"🏫 <b>المؤسسة:</b> {site_info['name']}\n"
                    f"📢 <b>العنوان:</b> {link['text']}"
                    f"{summary_text}\n\n"
                    f"🔗 <b>الرابط المباشر:</b> {link['url']}"
                )
                
                send_telegram_message(msg)
                state[site_id].append(clean_url(link['url']))
                
                # إبقاء أحدث 50 رابط فقط فـ state لكل موقع
                state[site_id] = state[site_id][-50:]
                save_state(state)

        except Exception as e:
            print(f"Error checking {site_info['name']}: {e}", flush=True)
            failed_sites.append(f"{site_info['name']} (سيرفر بطيء / غير متاح)")

    save_state(state)
    print("Done checking all sites.", flush=True)

    # إرسال تقرير تلغرام فقط إذا كانت المواقع الفاشلة أكثر من 10 مواقع
    if len(failed_sites) > 10:
        failed_list_str = "\n".join([f"• {s}" for s in failed_sites[:10]])
        report_msg = (
            f"⚠️ <b>تقرير الفحص: بعض المواقع لم تستجب</b>\n\n"
            f"{failed_list_str}\n\n"
            f"💡 <i>سيقوم البوت بإعادة فحصها تلقائياً.</i>"
        )
        send_telegram_message(report_msg)

if __name__ == "__main__":
    check_sites()
