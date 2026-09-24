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

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Assalomu alaykum! 😊 Men AURAgpt botiman. 🤖 Menga istalgan savol yozishingiz mumkin! ✨")

@dp.message()
async def chat_with_ai(message: types.Message):
    user_text = message.text
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Siz ko'rsatgan barcha 3 ta model ketma-ketlikda
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
                {"role": "system", "content": "You are a helpful assistant. Always include friendly emojis and smiles (like 😊, ✨, 🚀, 🤖) in your responses."},
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
            
    if answer:
        await message.answer(answer)
    else:
        await message.answer(f"⚠️ Xatolik tafsiloti:\n<code>{last_error}</code>\n\nBarcha modellar sinab ko'rildi, lekin javob olinmadi. 🔄", parse_mode="HTML")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
