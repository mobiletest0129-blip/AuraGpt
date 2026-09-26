import os
import asyncio
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import aiohttp

# --- RENDER UCHUN ODDIY VA ISHONCHLI WEB-SERVER ---
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

# Veb-serverni alohida oqimda (thread) ishga tushiramiz
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# --- BOT VA GROQ API SOZLAMALARI ---
TOKEN = "8830513411:AAHuDd6_AWoaXdwTAKRge7CLPYbONCUrhIU"
GROQ_API_KEY = "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"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

greeted_users = set()
user_histories = {}

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    try:
        user_id = message.from_user.id
        greeted_users.add(user_id)
        user_histories[user_id] = []
        await message.answer("Assalomu alaykum! 😊 / Здравствуйте! / Hello!\nMen AURAgpt botiman. 🤖 Xotiram va rasm ko'rish qobiliyatim ishlayapti, savollaringizga tayyorman! ✨")
    except Exception as e:
        logging.error(f"Start xatosi: {e}")

# --- RASMLARNI QABUL QILIB TAHLIL QILISH QISMI ---
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    
    welcome_prefix = ""
    if user_id not in greeted_users:
        greeted_users.add(user_id)
        welcome_prefix = "Assalomu alaykum! 😊 / Hello! 👋\n\n"

    # Eng sifatli rasmni olamiz
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_path = file_info.file_path
    
    # Telegram serveridan rasmga to'g'ridan-to'g'ri havola
    image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    
    user_caption = message.caption or "Bu rasmda nima tasvirlangan? Iltimos, tushuntirib bering."

    waiting_msg = await message.answer("🖼 Rasm tahlil qilinmoqda... / Анализирую изображение... / Analyzing image...")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Vision (ko'rishni qo'llab-quvvatlaydigan) model
    vision_model = 'llama-3.2-11b-vision-preview'
    
    payload = {
        "model": vision_model,
        "messages": [
            {
                "role": "system",
                "content": "You are AURAgpt, an AI assistant created by Bunyodbek Zokirov. Detect the language of the user's caption or request (Uzbek, Russian, or English) and reply concisely in that exact same language, describing or answering about the image. Include friendly emojis."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_caption
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            }
        ],
        "max_tokens": 1024
    }

    answer = None
    last_error = ""

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30) as response:
                res_json = await response.json()
                if "choices" in res_json:
                    answer = res_json["choices"][0]["message"]["content"]
                else:
                    last_error = res_json.get("error", {}).get("message", str(res_json))
        except Exception as e:
            last_error = str(e)

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=waiting_msg.message_id)
    except:
        pass
        
    fanswer = answer if answer else f"⚠️ Xatolik / Ошибка / Error:\n<code>{last_error}</code>"
    await message.answer(welcome_prefix + fanswer, parse_mode="HTML" if not answer else None)


# --- ODDIY MATNLI XABarlar UCHUN ---
@dp.message(F.text)
async def chat_with_ai(message: types.Message):
    user_text = message.text
    user_id = message.from_user.id
    
    welcome_prefix = ""
    if user_id not in greeted_users:
        greeted_users.add(user_id)
        welcome_prefix = "Assalomu alaykum! 😊 / Hello! 👋\n\n"

    if user_id not in user_histories:
        user_histories[user_id] = []

    waiting_msg = await message.answer("⏳ O'ylayapman... / Думаю... / Thinking...")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    models = [
        'llama-3.3-70b-versatile',
        'llama-3.1-8b-instant',
        'openai/gpt-oss-120b'
    ]
    
    system_prompt = {
        "role": "system", 
        "content": "You are AURAgpt, an AI assistant created by Bunyodbek Zokirov. ALWAYS pay close attention to the previous chat history to remember user details, such as their name, preferences, or facts they shared earlier. If anyone asks who created you, answer proudly that you were created by Bunyodbek Zokirov. Detect the language of the user's message (Uzbek, Russian, or English) and reply concisely in that exact same language. Always include friendly emojis (like 😊, ✨, 🚀, 🤖) in your responses."
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
                async with session.post("https://api.groq.com/openai/v1/chat/completions", json=data, headers=headers, timeout=20) as response:
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
        
    fanswer = answer if answer else f"⚠️ Xatolik / Ошибка / Error:\n<code>{last_error}</code>"
    if not answer and len(user_histories[user_id]) > 0:
        user_histories[user_id].pop()
        
    await message.answer(welcome_prefix + fanswer, parse_mode="HTML" if not answer else None)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
