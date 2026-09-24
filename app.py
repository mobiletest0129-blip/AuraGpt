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
TOKEN = "8830513411:AAEsmDgU5uMJGoeY22bKpzzaYCrUIEnzboA"
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
    
    # Siz xohlagan barcha faol modellar ro'yxati (birinchisi ishlamasa, keyingisi avtomatik urinib ko'radi)
    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768"
    ]
    
    answer = None
    for model_name in models:
        data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Always include friendly emojis and smiles (like 😊, ✨, 🚀, 🤖) in your responses to make them lively and engaging."},
                {"role": "user", "content": user_text}
            ]
        }
        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=data, headers=headers, timeout=15)
            res_json = response.json()
            
            if "choices" in res_json:
                answer = res_json["choices"][0]["message"]["content"]
                break # Agar model muvaffaqiyatli javob bersa, siklni to'xtatamiz
        except Exception:
            continue
            
    if answer:
        await message.answer(answer)
    else:
        await message.answer("⚠️ Kechirasiz, sun'iy intellekt modellariga ulanishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring! 🔄")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
