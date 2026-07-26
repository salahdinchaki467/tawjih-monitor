import json
import os
import io
import time
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
import google.generativeai as genai

# الإعدادات والمتغيرات
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# تعديل المسار ليكون مباشرة في جذر المشروع
DATA_FILE = 'state.json'

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def extract_text_from_pdf(pdf_url):
    """تحميل ملف PDF واستخراج النص منه"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(pdf_url, headers=headers, timeout=15)
        if res.status_code == 200:
            pdf_file = io.BytesIO(res.content)
            reader = PdfReader(pdf_file)
            text = ""
            for page in reader.pages[:3]:
                text += page.extract_text() or ""
            return text[:3000]
    except Exception as e:
        print(f"Error reading PDF {pdf_url}: {e}")
    return None

def summarize_with_ai(text_content):
    """تلخيص النص باستخدام الذكاء الاصطناعي Gemini"""
    if not GEMINI_API_KEY or not text_content:
        return None
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "أنت مساعد توجيه جامعي بالمغرب. قم بتلخيص هذا البلاغ/الإعلان للطلبة في 3 نقاط موجزة ومباشرة باللغة العربية:\n"
            "1. المضمون والهدف من الإعلان.\n"
            "2. آخر أجل للترشيح/التسجيل (إن وجد).\n"
            "3. طريقة أو رابط التقديم.\n\n"
            f"النص:\n{text_content}"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini AI Error: {e}")
        return None

def load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading state.json: {e}")
    return {}

def save_state(state):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def check_sites():
    with open('sites.json', 'r', encoding='utf-8') as f:
        sites = json.load(f)
    
    state = load_state()
    new_updates = False

    for site_id, site_info in sites.items():
        print(f"Checking {site_info['name']}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(site_info['url'], headers=headers, timeout=12)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.text.strip()
                if not text:
                    text = "إعلان / بلاغ جديد"
                    
                if '.pdf' in href.lower() or 'avis' in href.lower() or 'concours' in href.lower() or 'annonce' in href.lower():
                    if href.startswith('/'):
                        href = site_info['url'].rstrip('/') + href
                    elif not href.startswith('http'):
                        href = site_info['url'].rstrip('/') + '/' + href
                    links.append({"text": text, "url": href})
            
            if site_id not in state:
                state[site_id] = []
            
            for link in links:
                if link['url'] not in state[site_id]:
                    summary_text = ""
                    if '.pdf' in link['url'].lower():
                        print(f"Extracting & Summarizing PDF: {link['url']}")
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
                    new_updates = True
                    time.sleep(3)
                    
        except Exception as e:
            print(f"Error checking {site_info['name']}: {e}")

    if new_updates:
        save_state(state)
        print("State updated successfully.")
    else:
        print("No new updates found.")

if __name__ == "__main__":
    check_sites()
