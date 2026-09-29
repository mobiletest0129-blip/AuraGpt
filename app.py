import os
import asyncio
import logging
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import aiohttp

# --- RENDER UCHUN WEB-SERVER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AuraGpt bot is active!")
        
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
        
    def log_message(self, format, *args):
        pass

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# --- TOKEN VA SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# Ma'lumotlar bazasi vazifasini bajaruvchi vaqtinchalik xotiralar
user_histories = {}
verified_users = set()  # Ro'yxatdan o'tganlar ID si
pending_registrations = {}  # Kod kutayotganlar: {user_id: {"email": email, "code": code}}

def send_email_code(to_email, code):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = "AURAgpt - Tasdiqlash kodi (Verification Code)"
        
        body = f"Sizning AURAgpt botida ro'yxatdan o'tish uchun tasdiqlash kodingiz:\n\n{code}\n\nKodni hech kimga bermang!"
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logging.error(f"Pochta yuborish xatosi: {e}")
        return False

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    if user_id in verified_users:
        await message.answer("Assalomu alaykum! 😊 Siz allaqachon ro'yxatdan o'tgansiz. Savollaringizni yuborishingiz mumkin! 🤖")
    else:
        pending_registrations[user_id] = {"step": "waiting_email"}
        await message.answer("✉️ Assalomu alaykum! AURAgpt botidan foydalanish uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`):")

@dp.message(F.text)
async def handle_text_messages(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    # 1. Agar foydalanuvchi email kiritayotgan bo'lsa
    if user_id in pending_registrations and pending_registrations[user_id].get("step") == "waiting_email":
        if "@gmail.com" not in text.lower():
            await message.answer("⚠️ Iltimos, yaroqli **Gmail** manzilini kiriting (masalan: test@gmail.com):")
            return
        
        code = str(random.randint(100000, 999999))
        pending_registrations[user_id]["email"] = text
        pending_registrations[user_id]["code"] = code
        pending_registrations[user_id]["step"] = "waiting_code"

        sent = send_email_code(text, code)
        if sent:
            await message.answer(f"📩 **{text}** manziliga 6 xonali tasdiqlash kodi yuborildi. Iltimos, pochtangizni tekshirib, kodni shu yerga yuboring:")
        else:
            await message.answer("⚠️ Xatolik yuz berdi. Pochtaga kod yuborib bo'lmadi. Iltimos, boshqa Gmail kiriting yoki keyinroq urinib ko'ring:")
            pending_registrations[user_id]["step"] = "waiting_email"
        return

    # 2. Agar foydalanuvchi tasdiqlash kodini kiritayotgan bo'lsa
    if user_id in pending_registrations and pending_registrations[user_id].get("step") == "waiting_code":
        correct_code = pending_registrations[user_id].get("code")
        if text == correct_code:
            verified_users.add(user_id)
            del pending_registrations[user_id]
            user_histories[user_id] = []
            await message.answer("✅ Tabriklayman! Pochtatingiz muvaffaqiyatli tasdiqlandi. Endi botdan to'liq foydalanishingiz mumkin! 🚀 Savollaringizni yuboring.")
        else:
            await message.answer("❌ Noto'g'ri kod! Iltimos, pochtangizga kelgan 6 xonali kodni qaytadan yuboring:")
        return

    # 3. Ro'yxatdan o'tmagan bo'lsa
    if user_id not in verified_users:
        await message.answer("⚠️ Botdan foydalanish uchun avval ro'yxatdan o'tishingiz kerak. Iltimos, /start buyrug'ini bosing.")
        return

    # --- AI BILAN MULOQOT QISMI (RO'YXATDAN O'TGANLAR UCHUN) ---
    user_text = message.text
    if user_id not in user_histories:
        user_histories[user_id] = []

    waiting_msg = await message.answer("⏳ O'ylayapman...")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    models = [
        'llama-3.3-70b-versatile',
        'llama-3.1-8b-instant',
        'openai/gpt-oss-120b',
        'llama-3.3-70b-specdec',
        'llama-3.1-70b-versatile',
        'llama3-70b-8192',
        'llama3-8b-8192',
        'mixtral-8x7b-32768',
        'gemma2-9b-it'
    ]
    
    system_prompt = {
        "role": "system", 
        "content": (
            "You are AURAgpt, a highly advanced multilingual AI assistant created by Bunyodbek Zokirov. "
            "You are capable of understanding and fluent in over 200 languages worldwide. "
            "ALWAYS detect the language of the user's message accurately and reply fluently in that exact same language. "
            "If anyone asks who created you, proudly state that you were created by Bunyodbek Zokirov. "
            "Always pay close attention to the previous chat history to remember user details, and use friendly emojis (like 😊, ✨, 🚀, 🤖)."
        )
    }

    user_histories[user_id].append({"role": "user", "content": user_text})
    recent_history = user_histories[user_id][-10:]
    messages_payload = [system_prompt] + recent_history

    answer = None
    last_error = ""
    
    async with aiohttp.ClientSession() as session:
        for model_name in models:
            data = {
                "model": model_name,
                "messages": messages_payload,
                "max_tokens": 1024
            }
            try:
                async with session.post("https://api.groq.com/openai/v1/chat/completions", json=data, headers=headers, timeout=15) as response:
                    res_json = await response.json()
                    if "choices" in res_json:
                        answer = res_json["choices"][0]["message"]["content"]
                        user_histories[user_id].append({"role": "assistant", "content": answer})
                        break
                    else:
                        last_error = res_json.get("error", {}).get("message", str(res_json))
            except Exception as e:
                last_error = str(e)
                continue
            
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=waiting_msg.message_id)
    except:
        pass
        
    fanswer = answer if answer else f"⚠️ Xatolik yuz berdi:\n<code>{last_error}</code>"
    if not answer and len(user_histories[user_id]) > 0:
        user_histories[user_id].pop()
        
    await message.answer(fanswer, parse_mode="HTML" if not answer else None)

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        await message.answer("⚠️ Botdan foydalanish uchun avval /start orqali ro'yxatdan o'ting.")
        return
    await message.answer("📸 Rasm qabul qilindi! Hozircha faqat matnli xabarlar va savollar bilan ishlayapmiz. 😊")

async def main():
    if not bot:
        logging.error("Bot obyekti yaratilmadi, TOKEN mavjud emas!")
        return
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
