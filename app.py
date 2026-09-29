import os
import random
import smtplib
from email.message import EmailMessage
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from groq import Groq

# Tokenlar va sozlamalar (Render Environment Variables'dan o'qiladi)
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Loggingni sozlash (xatoliklarni Render loglarida ko'rsatish uchun)
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

groq_client = Groq(api_key=GROQ_API_KEY)

# Foydalanuvchi holatlari (FSM)
class RegistrationStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()

# Tasdiqlangan foydalanuvchilar va vaqtinchalik kodlar bazasi
verified_users = set()
pending_registrations = {} # {chat_id: {"email": email, "code": code}}

# Pochtaga kod yuborish funksiyasi
def send_otp_email(to_email, code):
    try:
        msg = EmailMessage()
        msg.set_content(f"Sizning AURAgpt botiga kirish uchun tasdiqlash kodingiz: {code}")
        msg["Subject"] = "AURAgpt - Tasdiqlash kodi"
        msg["From"] = EMAIL_USER
        msg["To"] = to_email

        # Gmail SMTP ulanishi (SSL port 465)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        # Xatolikni Render loglariga chiqarish uchun chop etamiz
        print(f"SMTP Error: {str(e)}")
        return False

# /start buyrug'i
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in verified_users:
        await message.answer("Siz allaqachon ro'yxatdan o'tgansiz! Savolingizni yozishingiz mumkin 🤖")
        return

    await message.answer("✉️ Assalomu alaykum! AURAgpt botidan foydalanish uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`):", parse_mode="Markdown")
    await state.set_state(RegistrationStates.waiting_for_email)

# Email qabul qilish va kod yuborish
@dp.message(RegistrationStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, yaroqli **Gmail** manzilini kiriting (masalan: `test@gmail.com`):")
        return

    code = str(random.randint(100000, 999999))
    pending_registrations[message.from_user.id] = {"email": email, "code": code}

    # Pochtaga kod jo'natish
    success = send_otp_email(email, code)
    if success:
        await message.answer(f"✅ Kod `{email}` manziliga yuborildi. Iltimos, pochtangizni tekshirib, 6 xonali kodni kiriting:", parse_mode="Markdown")
        await state.set_state(RegistrationStates.waiting_for_code)
    else:
        await message.answer("⚠️ Xatolik yuz berdi. Pochtaga kod yuborib bo'lmadi. Iltimos, boshqa Gmail kiriting yoki keyinroq urinib ko'ring:")

# Kodni tekshirish
@dp.message(RegistrationStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_code = message.text.strip()

    if user_id in pending_registrations and pending_registrations[user_id]["code"] == user_code:
        verified_users.add(user_id)
        del pending_registrations[user_id]
        await state.clear()
        await message.answer("🎉 Tabriklaymiz! Muvaffaqiyatli ro'yxatdan o'tdingiz. Endi botdan to'liq foydalanishingiz mumkin. Savolingizni yozing!")
    else:
        await message.answer("❌ Noto'g'ri kod. Iltimos, pochtangizga kelgan 6 xonali kodni qaytadan kiriting:")

# Oddiy xabarlar va AI javoblari (Faqat ro'yxatdan o'tganlarga ishlaydi)
@dp.message()
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        await message.answer("⚠️ Botdan foydalanish uchun avval ro'yxatdan o'tishingiz kerak. Iltimos, /start buyrug'ini bosing.")
        return

    # Groq AI orqali javob qaytarish
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": message.text}],
            model="llama-3.3-70b-versatile",
        )
        response_text = chat_completion.choices[0].message.content
        await message.answer(response_text)
    except Exception as e:
        await message.answer("⚠️ Sun'iy intellektga ulanishda xatolik yuz berdi.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
