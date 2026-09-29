import asyncio
import random
import os
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from groq import Groq

# Tokenlar va kalitlar (Render Environment dan olinadi)
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
RESEND_API_KEY = os.getenv("BREVO_API_KEY") # Oldingi o'zgaruvchi nomi saqlangan bo'lsa ham ishlayveradi

# Bot va Groq sozlamalari
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

# Foydalanuvchi holatlari (FSM)
class AuthState(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()
    authenticated = State()

# Tasdiqlangan foydalanuvchilar bazasi va kodlar
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

# Emailni qabul qilish va Resend API orqali kod yuborish
@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy Gmail manzilini kiriting (masalan: `ismingiz@gmail.com`):")
        return

    code = str(random.randint(100000, 999999))
    verification_codes[message.from_user.id] = code

    # Resend API URL va sozlamalari
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": "AURAgpt <onboarding@resend.dev>",
        "to": [email],
        "subject": "AURAgpt - Tasdiqlash kodi",
        "html": f"<p>Sizning AURAgpt boti uchun tasdiqlash kodingiz: <b>{code}</b></p>"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            await state.update_data(email=email)
            await message.answer(f"📩 **{email}** manziliga 6 xonali tasdiqlash kodi yuborildi. Iltimos, kodni kiriting:", parse_mode="Markdown")
            await state.set_state(AuthState.waiting_for_code)
        else:
            print(f"Resend API Error: {response.text}")
            await message.answer("⚠ Xatolik yuz berdi. Pochtaga kod yuborib bo'lmadi. Keyinroq urinib ko'ring:")
    except Exception as e:
        print(f"Request Error: {str(e)}")
        await message.answer("⚠ Xatolik yuz berdi. Pochtaga kod yuborib bo'lmadi.")

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
        await message.answer(f"⚠️️ Sun'iy intellektga ulanishda xatolik yuz berdi: {str(e)}")

async def main():
    print("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
