import asyncio
import random
import os
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
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
BREVO_API_KEY = os.getenv("BREVO_API_KEY")    # Brevo API kaliti

# Bot va Groq sozlamalari
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

# Foydalanuvchi holatlari (FSM)
class AuthState(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()
    authenticated = State()

verified_users = set()       # Tasdiqlangan foydalanuvchilar ID lari
verification_codes = {}      # Tasdiqlash kodlari
user_histories = {}          # Chat tarixi (xotira)

# Chiqish tugmasi uchun klaviatura yaratish funksiyasi
def get_chat_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🚪 Chiqish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# /start buyrug'i
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id in verified_users:
        await message.answer(
            "✅ Siz allaqachon tizimdasiz. Menga istalgan savolingizni yuborishingiz mumkin!",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
        return

    await message.answer(
        "🤖 **Assalomu alaykum!** Men **AURAgpt** sun'iy intellekt botiman.\n"
        "Meni iste'dodli dasturchi **Bunyodbek Zokirov** yasaganlar! 💻✨\n\n"
        "Botdan foydalanish uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`):",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_email)

# Emailni qabul qilish va Brevo HTTP API orqali kod yuborish
@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy Gmail manzilini kiriting (masalan: `ismingiz@gmail.com`):")
        return

    code = str(random.randint(100000, 999999))
    verification_codes[message.from_user.id] = code

    # Brevo HTTP API orqali xat yuborish
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "AURAgpt Bot", "email": SENDER_EMAIL},
        "to": [{"email": email}],
        "subject": "AURAgpt - Tasdiqlash kodi",
        "textContent": f"Sizning AURAgpt boti uchun tasdiqlash kodingiz: {code}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201, 202]:
            await state.update_data(email=email)
            await message.answer(f"📩 **{email}** manziliga 6 xonali tasdiqlash kodi yuborildi. Iltimos, kodni kiriting:", parse_mode="Markdown")
            await state.set_state(AuthState.waiting_for_code)
        else:
            await message.answer(f"⚠ Xatolik (Brevo): {response.text}")
    except Exception as e:
        await message.answer(f"⚠ Tarmoq xatoligi: {str(e)}")

# Kodni tekshirish
@dp.message(AuthState.waiting_for_code, F.text)
async def process_code(message: types.Message, state: FSMContext):
    user_code = message.text.strip()
    real_code = verification_codes.get(message.from_user.id)

    if user_code == real_code:
        verified_users.add(message.from_user.id)
        # Eski chat tarixini tozalash (yangi kirish uchun)
        user_histories[message.from_user.id] = [
            {
                "role": "system", 
                "content": "Sen AURAgpt nomli sun'iy intellekt botisan. Seni Bunyodbek Zokirov ismli dasturchi yasagan. Agar kimdir seni kim yasaganini so'rasa, har doim Bunyodbek Zokirov yasaganini faxr bilan ayt. Shuningdek, foydalanuvchining ismi va ma'lumotlarini suhbat davomida eslab qol."
            }
        ]
        
        await message.answer(
            "🎉 Tabriklayman! Pochta muvaffaqiyatli tasdiqlandi. Endi AURAgpt botidan to'liq foydalanishingiz mumkin!",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
    else:
        await message.answer("❌ Noto'g'ri kod. Iltimos, pochtangizga kelgan kodni qaytadan kiriting:")

# Chiqish tugmasi bosilganda
@dp.message(F.text == "🚪 Chiqish")
async def logout_user(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in verified_users:
        verified_users.remove(user_id)
    if user_id in user_histories:
        del user_histories[user_id]
    if user_id in verification_codes:
        del verification_codes[user_id]
        
    await state.clear()
    
    # Klavierni olib tashlash va boshlang'ich holatga qaytarish
    await message.answer(
        "🚪 Tizimdan muvaffaqiyatli chiqdingiz.\n"
        "Qaytadan kirish uchun /start buyrug'ini bosing.",
        reply_markup=types.ReplyKeyboardRemove()
    )

# Groq AI bilan xotirali muloqot
@dp.message(AuthState.authenticated, F.text)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_histories:
        user_histories[user_id] = [
            {
                "role": "system", 
                "content": "Sen AURAgpt nomli sun'iy intellekt botisan. Seni Bunyodbek Zokirov ismli dasturchi yasagan. Agar kimdir seni kim yasaganini so'rasa, har doim Bunyodbek Zokirov yasaganini faxr bilan ayt. Shuningdek, foydalanuvchining ismi va ma'lumotlarini suhbat davomida eslab qol."
            }
        ]

    user_histories[user_id].append({"role": "user", "content": message.text})
    
    # Xotira hajmini nazorat qilish
    if len(user_histories[user_id]) > 21:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-20:]

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=user_histories[user_id]
        )
        response_text = completion.choices[0].message.content
        
        user_histories[user_id].append({"role": "assistant", "content": response_text})
        
        await message.answer(response_text, reply_markup=get_chat_keyboard())
    except Exception as e:
        await message.answer(f"⚠ Xatolik yuz berdi: {str(e)}", reply_markup=get_chat_keyboard())

async def main():
    Thread(target=run_flask).start()
    print("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
