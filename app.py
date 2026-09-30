import asyncio
import random
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from groq import Groq
from flask import Flask
from threading import Thread

# Render port talabini qondirish uchun kichik Flask server
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "AURAgpt Bot is active!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# Tokenlar va kalitlar
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")       # Sizning Gmail pochtangiz
EMAIL_PASSWORD = os.getenv("BREVO_API_KEY")    # Google'dan olingan 16 xonali ilova paroli (dgfpuuwlesktaxh)

# Bot va Groq sozlamalari
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

# Foydalanuvchi holatlari (FSM)
class AuthState(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()
    authenticated = State()

verified_users = set()
verification_codes = {}

# /start buyrug'i
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in verified_users:
        await message.answer("✅ Siz allaqachon ro'yxatdan o'tgansiz. Menga istalgan savolingizni yuborishingiz mumkin!")
        await state.set_state(AuthState.authenticated)
        return

    await message.answer("📧 Assalomu alaykum! AURAgpt botidan foydalanish uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`):", parse_mode="Markdown")
    await state.set_state(AuthState.waiting_for_email)

# Emailni qabul qilish va SMTP orqali kod yuborish
@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy Gmail manzilini kiriting (masalan: `ismingiz@gmail.com`):")
        return

    code = str(random.randint(100000, 999999))
    verification_codes[message.from_user.id] = code

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = email
    msg['Subject'] = "AURAgpt - Tasdiqlash kodi"
    
    body = f"Sizning AURAgpt boti uchun tasdiqlash kodingiz: {code}"
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, email, msg.as_string())
        server.quit()

        await state.update_data(email=email)
        await message.answer(f"📩 **{email}** manziliga 6 xonali tasdiqlash kodi yuborildi. Iltimos, kodni kiriting:", parse_mode="Markdown")
        await state.set_state(AuthState.waiting_for_code)
    except Exception as e:
        print(f"SMTP Error: {str(e)}")
        await message.answer("⚠ Xatolik yuz berdi. Pochtaga kod yuborib bo'lmadi. Parolni yoki sozlamalarni tekshiring.")

# Kodni tekshirish
@dp.message(AuthState.waiting_for_code, F.text)
async def process_code(message: types.Message, state: FSMContext):
    user_code = message.text.strip()
    real_code = verification_codes.get(message.from_user.id)

    if user_code == real_code:
        verified_users.add(message.from_user.id)
        await message.answer("🎉 Tabriklayman! Pochta muvaffaqiyatli tasdiqlandi. Endi AURAgpt botidan to'liq foydalanishingiz mumkin!")
        await state.set_state(AuthState.authenticated)
    else:
        await message.answer("❌ Noto'g'ri kod. Iltimos, pochtangizga kelgan kodni qaytadan kiriting:")

# Groq AI bilan muloqot
@dp.message(AuthState.authenticated, F.text)
async def chat_with_ai(message: types.Message):
    try:
        completion = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": message.text}]
        )
        response_text = completion.choices[0].message.content
        await message.answer(response_text)
    except Exception as e:
        await message.answer(f"⚠ Sun'iy intellektga ulanishda xatolik yuz berdi: {str(e)}")

async def main():
    # Flask serverni alohida oqimda (thread) ishga tushiramiz
    Thread(target=run_flask).start()
    
    print("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
