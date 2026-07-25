import json
import os
import requests
from bs4 import BeautifulSoup
import time

# إعدادات Telegram من GitHub Secrets
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

DATA_FILE = 'data/state.json'

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def load_state():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_state(state):
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def check_sites():
    # قراءة المواقع
    with open('sites.json', 'r', encoding='utf-8') as f:
        sites = json.load(f)
    
    state = load_state()
    new_updates = False

    for site_id, site_info in sites.items():
        print(f"Checking {site_info['name']}...")
        try:
            # إضافة headers باش المواقع ما تبلوكيش السكريبت
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(site_info['url'], headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # استخراج جميع الروابط
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.text.strip()
                # نركز على الروابط اللي فيها pdf أو إعلانات (كمثال بسيط)
                if '.pdf' in href.lower() or 'avis' in href.lower() or 'concours' in href.lower():
                    # معالجة الروابط النسبية
                    if href.startswith('/'):
                        href = site_info['url'].rstrip('/') + href
                    links.append({"text": text, "url": href})
            
            # تهيئة حالة الموقع إذا كان جديد
            if site_id not in state:
                state[site_id] = []
            
            # مقارنة الروابط الجديدة مع القديمة
            for link in links:
                if link['url'] not in state[site_id]:
                    # لقينا حاجة جديدة!
                    msg = f"🚨 <b>إعلان جديد!</b>\n\n🏫 <b>المؤسسة:</b> {site_info['name']}\n📄 <b>العنوان:</b> {link['text']}\n🔗 <b>الرابط:</b> {link['url']}"
                    send_telegram_message(msg)
                    state[site_id].append(link['url'])
                    new_updates = True
                    time.sleep(2) # استراحة باش ما نسباموش Telegram
                    
        except Exception as e:
            print(f"Error checking {site_info['name']}: {e}")

    if new_updates:
        save_state(state)
        print("State updated successfully.")
    else:
        print("No new updates found.")

if __name__ == "__main__":
    check_sites()
