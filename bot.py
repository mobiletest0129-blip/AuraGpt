import time
import requests
import threading

# =========================================================
# ⚠️ TELEGRAM VA VIRUSTOTAL KALITLARINGIZ:
API_TOKEN = '8944690228:AAEweDN7IU2NbAkgZD16aSU1GXtWbu2X1aA'
VIRUSTOTAL_KEY = '9816d4bd0effaf4a95d8066b604af40031d9728ba37efc4f33215c667f8d45e3'
# =========================================================

BASE_URL = f"https://api.telegram.org/bot{API_TOKEN}"

def get_updates(offset=None):
    try:
        url = f"{BASE_URL}/getUpdates?timeout=60"
        if offset: url += f"&offset={offset}"
        response = requests.get(url, timeout=65)
        if response.status_code == 200:
            # JSON formatga o'girishdan oldin xavfsiz tekshiramiz
            try:
                return response.json()
            except ValueError:
                print("⚠️ Telegramdan noto'g'ri ma'lumot keldi (JSON emas).")
                return None
    except Exception as e:
        print(f"⏰ Tarmoq uzilishi (getUpdates): {e}. Qayta ulanmoqda...")
    return None

def send_message(chat_id, text, reply_to_message_id=None):
    try:
        url = f"{BASE_URL}/sendMessage"
        payload = {
            "chat_id": chat_id, 
            "text": text, 
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Xabar yuborishda xatolik: {e}")

# 🌐 LINK TEKSHIRISH (XAFSIZ REJIM)
def process_link_analysis(chat_id, message_id, url_to_check):
    try:
        vt_url = "https://www.virustotal.com/api/v3/urls"
        payload = {"url": url_to_check}
        headers = {
            "accept": "application/json", 
            "x-apikey": VIRUSTOTAL_KEY, 
            "content-type": "application/x-www-form-urlencoded"
        }
        res = requests.post(vt_url, data=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            try:
                analysis_id = res.json()['data']['id']
                analysis_url = f"https://www.virustotal.com/api/v3/analyses/{analysis_id}"
                
                time.sleep(4)
                result_res = requests.get(analysis_url, headers={"x-apikey": VIRUSTOTAL_KEY}, timeout=15)
                if result_res.status_code == 200:
                    stats = result_res.json()['data']['attributes']['stats']
                    
                    malicious = stats['malicious']
                    suspicious = stats['suspicious']
                    harmless = stats['harmless']
                    
                    report = (
                        f"🌐 **Havola Skriningi Yakunlandi**\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔗 **URL:** {url_to_check}\n\n"
                        f"🔴 Zararli (Malicious): *{malicious}*\n"
                        f"🟡 Shubhali (Suspicious): *{suspicious}*\n"
                        f"🟢 Xavfsiz (Harmless): *{harmless}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    if malicious > 0:
                        report += "❌ **DIQQAT:** Ushbu havola xavfli deb topildi! Kirish tavsiya etilmaydi."
                    else:
                        report += "✅ Tizim ushbu havolada hech qanday tahdid aniqlamadi."
                        
                    send_message(chat_id, report, message_id)
                    return
            except (ValueError, KeyError):
                pass
    except Exception as e:
        print(f"⚠️ Link tekshirishda xatolik: {e}")
    send_message(chat_id, "❌ Havolani tahlil qilishda texnik xatolik yuz berdi.", message_id)

# 📦 APK VA FAYLLARNI TEKSHIRISH (EXPECTING VALUE XATOSISIZ)
def process_file_analysis(chat_id, message_id, file_id, file_name):
    try:
        file_info_res = requests.get(f"{BASE_URL}/getFile?file_id={file_id}", timeout=10)
        if file_info_res.status_code != 200:
            send_message(chat_id, "❌ Telegramdan fayl ma'lumotlarini olib bo'lmadi.", message_id)
            return
            
        try:
            file_info = file_info_res.json()
        except ValueError:
            send_message(chat_id, "❌ Telegram serveri noto'g'ri javob qaytardi.", message_id)
            return
            
        if not file_info.get('ok'):
            send_message(chat_id, "❌ Telegram serverlaridan faylni yuklab bo'lmadi.", message_id)
            return
        
        file_path = file_info['result']['file_path']
        download_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
        
        file_response = requests.get(download_url, timeout=30)
        if file_response.status_code != 200:
            send_message(chat_id, "❌ Fayl kontentini o'qishda xatolik.", message_id)
            return
        
        vt_url = "https://www.virustotal.com/api/v3/files"
        headers = {"accept": "application/json", "x-apikey": VIRUSTOTAL_KEY}
        files = {"file": (file_name, file_response.content)}
        
        res = requests.post(vt_url, headers=headers, files=files, timeout=30)
        if res.status_code == 200:
            try:
                analysis_id = res.json()['data']['id']
                analysis_url = f"https://www.virustotal.com/api/v3/analyses/{analysis_id}"
                
                for _ in range(20):
                    time.sleep(6)
                    result_res = requests.get(analysis_url, headers={"x-apikey": VIRUSTOTAL_KEY}, timeout=15)
                    if result_res.status_code == 200:
                        try:
                            data = result_res.json()['data']['attributes']
                            if data['status'] == "completed":
                                stats = data['stats']
                                
                                malicious = stats['malicious']
                                suspicious = stats['suspicious']
                                harmless = stats['harmless']
                                
                                report = (
                                    f"📦 **Fayl Ekspertizasi Yakunlandi**\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🗂️ **Nomi:** `{file_name}`\n\n"
                                    f"🔴 Zararli (Malicious): *{malicious}*\n"
                                    f"🟡 Shubhali (Suspicious): *{suspicious}*\n"
                                    f"🟢 Xavfsiz (Harmless): *{harmless}*\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                )
                                if malicious > 0:
                                    report += "🚨 **REJEM: XAVFLI!** Fayl tarkibida troyan yoki zararli skriptlar topildi. Uni o'rnatmang!"
                                else:
                                    report += "🛡️ **REJEM: TOZA.** Fayl xavfsiz, tizim zararli kod aniqlamadi."
                                    
                                send_message(chat_id, report, message_id)
                                return
                        except (ValueError, KeyError):
                            continue
            except (ValueError, KeyError):
                pass
        send_message(chat_id, "⏱️ Skanerlash vaqti tugadi yoki VirusTotal rad etdi.", message_id)
    except Exception as e:
        print(f"⚠️ Fayl tekshirishda xatolik: {e}")
        send_message(chat_id, "❌ Faylni chuqur skanerlashda noma'lum xatolik.", message_id)

def main_bot():
    print("🚀 Crash-Proof Professional AntiVirus Bot muvaffaqiyatli ishga tushdi...")
    last_update_id = None
    
    while True:
        try:
            updates = get_updates(last_update_id)
            if updates and "result" in updates:
                for update in updates["result"]:
                    last_update_id = update["update_id"] + 1
                    if "message" in update:
                        message = update["message"]
                        chat_id = message["chat"]["id"]
                        message_id = message["message_id"]
                        
                        if "text" in message:
                            text = message["text"]
                            if text in ['/start', '/help']:
                                welcome_txt = (
                                    "🛡️ **Professional Tahlil Botiga xush kelibsiz!**\n\n"
                                    "Menga istalgan shubhali internet havola (link) yoki `.apk` formatdagi fayllarni yuboring.\n\n"
                                    "⚙️ _Xizmat 70+ ta eng yirik xalqaro antiviruslar bazasidan foydalanadi._"
                                )
                                send_message(chat_id, welcome_txt, message_id)
                            elif text.startswith(('http://', 'https://')):
                                send_message(chat_id, "🔍 Havola tahlil qilinmoqda, kuting...", message_id)
                                threading.Thread(target=process_link_analysis, args=(chat_id, message_id, text)).start()
                        
                        elif "document" in message:
                            doc = message["document"]
                            file_name = doc.get("file_name", "Noma'lum_fayl")
                            file_size = doc.get("file_size", 0)
                            
                            if file_size > 33554432:
                                send_message(chat_id, "⚠️ Professional xavfsizlik nuqtai nazaridan ruxsat etilgan maksimal hajm: **32 MB**.", message_id)
                                continue
                                
                            send_message(chat_id, f"📥 **{file_name}** qabul qilindi. Skanerlash jarayoni fonda boshlandi, iltimos kuting...", message_id)
                            threading.Thread(target=process_file_analysis, args=(chat_id, message_id, doc["file_id"], file_name)).start()
            
            time.sleep(0.5)
            
        except Exception as main_error:
            print(f"🚨 Global krizis: {main_error}. Bot 5 soniyadan keyin avtomatik tiklanadi...")
            time.sleep(5)

if __name__ == '__main__':
    main_bot()
