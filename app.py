import os
import asyncio
import logging
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- RENDER UCHUN PORT OCHUVchi WEB-SERVER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AuraGpt bot is running 24/7!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# --- BOT VA GROQ API SOZLAMALARI ---
TOKEN = "8830513411:AAHuDd6_AWoaXdwTAKRge7CLPYbONCUrhIU"
GROQ_API_KEY = "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"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

greeted_users = set()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    greeted_users.add(message.from_user.id)
    await message.answer("Assalomu alaykum! 😊 / Здравствуйте! / Hello!\nMen AURAgpt botiman. 🤖 O'zbekcha, Ruscha yoki Inglizcha tillarda istalgan savol yozishingiz mumkin! ✨")

@dp.message()
async def chat_with_ai(message: types.Message):
    user_text = message.text
    user_id = message.from_user.id
    
    welcome_prefix = ""
    if user_id not in greeted_users:
        greeted_users.add(user_id)
        welcome_prefix = "Assalomu alaykum! 😊 / Hello! 👋\n\n"

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
    
    answer = None
    last_error = ""
    
    for model_name in models:
        data = {
            "model": model_name,
            "messages": [
                {
                    "role": "system", 
                    "content": "You are AURAgpt, an AI assistant created by Bunyodbek Zokirov. If anyone asks who created you, who made you, or who is your developer, you must proudly answer that you were created by Bunyodbek Zokirov. Detect the language of the user's message (Uzbek, Russian, or English) and reply concisely in that exact same language. Always include friendly emojis (like 😊, ✨, 🚀, 🤖) in your responses."
                },
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 1024
        }
        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=data, headers=headers, timeout=15)
            res_json = response.json()
            
            if "choices" in res_json:
                answer = res_json["choices"][0]["message"]["content"]
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
        
    if answer:
        await message.answer(welcome_prefix + answer)
    else:
        await message.answer(f"⚠️ Xatolik / Ошибка / Error:\n<code>{last_error}</code>", parse_mode="HTML")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
