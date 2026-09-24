import os
import asyncio
import logging
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- 1. RENDER UCHUN PORT OCHUVCHI WEB-SERVER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AuraGpt bot is running 24/7!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

# Veb-serverni alohida oqimda ishga tushiramiz
threading.Thread(target=run_server, daemon=True).start()

# --- 2. BOT VA AI SOZLAMALARI ---
TOKEN = "8830513411:AAEsmDgU5uMJGoeY22bKpzzaYCrUIEnzboA"
GROQ_API_KEY = "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"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Assalomu alaykum! Men AURAgpt botiman. Menga istalgan savol yozishingiz mumkin.")

@dp.message()
async def chat_with_ai(message: types.Message):
    user_text = message.text
    
    # Groq API ga so'rov yuborish
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": user_text}]
    }
    
    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=data, headers=headers)
        res_json = response.json()
        answer = res_json["choices"][0]["message"]["content"]
        await message.answer(answer)
    except Exception as e:
        await message.answer("Kechirasiz, sun'iy intellektga ulanishda xatolik yuz berdi.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
