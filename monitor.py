import json
import os
import io
import time
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
import google.generativeai as genai
import urllib3

# إخفاء تحذيرات شهادات الأمان SSL فـ اللوغ
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# الإعدادات والمتغيرات
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

DATA_FILE = 'state.json'

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
        requests.post(url, json=payload, timeout=5, verify=False)
    except Exception as e:
        print(f"Error sending to Telegram: {e}", flush=True)

def extract_text_from_pdf(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(pdf_url, headers=headers, timeout=5, verify=False)
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

def check_sites():
    if not os.path.exists('sites.json'):
        print("sites.json file missing!", flush=True)
        return

    with open('sites.json', 'r', encoding='utf-8') as f:
        sites = json.load(f)
    
    state = load_state()

    for site_id, site_info in sites.items():
        print(f"Checking {site_info['name']}...", flush=True)
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            # verify=False لتفادي مشاكل الـ SSL و timeout=3 للسرعة
            response = requests.get(site_info['url'], headers=headers, timeout=3, verify=False)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.text.strip() or "إعلان / بلاغ جديد"
                    
                if '.pdf' in href.lower() or 'avis' in href.lower() or 'concours' in href.lower() or 'annonce' in href.lower():
                    if href.startswith('/'):
                        href = site_info['url'].rstrip('/') + href
                    elif not href.startswith('http'):
                        href = site_info['url'].rstrip('/') + '/' + href
                    if href not in [l['url'] for l in links]:
                        links.append({"text": text, "url": href})

            # 1. أول مرة: تسجيل صامت وسريع
            if site_id not in state:
                state[site_id] = [l['url'] for l in links]
                print(f"Seeded {len(links)} links for {site_info['name']}", flush=True)
                continue

            # 2. الإعلانات الجديدة فقط
            new_links = [l for l in links if l['url'] not in state[site_id]]

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
                state[site_id].append(link['url'])

        except Exception as e:
            print(f"Error checking {site_info['name']}: {e}", flush=True)

    save_state(state)
    print("Done checking all sites.", flush=True)

if __name__ == "__main__":
    check_sites()
