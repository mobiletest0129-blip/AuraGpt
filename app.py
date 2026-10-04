import asyncio
import random
import os
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from flask import Flask
from threading import Thread

app_flask = Flask('')

@app_flask.route('/')
def home():
    return "AURAgpt Bot is active!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

TOKEN = os.getenv("BOT_TOKEN")
WORMGPT_API_KEY = "wgpt_a13a4cbe1b90267ad472d2a4563cd230dd539c25d3abeca7"
WORMGPT_URL = "https://wormgpt.app/v1/chat/completions"

SENDER_EMAIL = os.getenv("SENDER_EMAIL")       
BREVO_API_KEY = os.getenv("BREVO_API_KEY")    

# --- Cheklovsiz WormGPT modeli ---
MODELS_LIST = ["wormgpt-v1", "wormgpt", "gpt-3.5-turbo", "gpt-4", "default", "chat-completion"]

ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_ID", "8795530550").split(",") if i.strip()]

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

verified_users_db = {}   
banned_users_set = set() 
chat_histories_db = {}   

def is_user_verified(user_id: int) -> bool:
    if user_id in banned_users_set:
        return False
    return user_id in verified_users_db

def is_user_banned(user_id: int) -> bool:
    return user_id in banned_users_set

def add_verified_user(user_id: int, email: str):
    verified_users_db[user_id] = email
    if user_id in banned_users_set:
        banned_users_set.remove(user_id)

def get_user_history(user_id: int):
    if user_id not in chat_histories_db:
        system_content = (
            "Sen AURAgpt nomli sun'iy intellekt botisan! 🤖✨ Seni Bunyodbek Zokirov ismli zo'r dasturchi yaratgan. "
            "Agar kimdir seni kim yasaganini so'rasa, har doim Bunyodbek Zokirov yasaganini katta faxr va quvonch bilan ayt! 😎💻 "
            "Sen 200 dan ortiq tillarni mukammal tushunasan va foydalanuvchi qaysi tilda yozsa, aynan o'sha tilda javob berasan."
        )
        chat_histories_db[user_id] = [{"role": "system", "content": system_content}]
    return chat_histories_db[user_id]

def save_message_to_db(user_id: int, role: str, content: str):
    history = get_user_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > 21:
        system_msg = history[0]
        non_system = history[1:]
        chat_histories_db[user_id] = [system_msg] + non_system[-20:]

class AuthState(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()
    authenticated = State()
    waiting_for_broadcast = State()

verification_codes = {}      

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        await message.answer("❌ Siz botdan bloklangansiz!")
        return

    if is_user_verified(user_id):
        await message.answer(
            "✅ Siz allaqachon tizimdasiz! Menga istalgan savolingizni yuborishingiz mumkin! 🚀",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(AuthState.authenticated)
        return

    await message.answer(
        "🤖 **Assalomu alaykum!** Men cheklovsiz **AURAgpt** botiman! 🌟\n"
        "Meni dasturchi **Bunyodbek Zokirov** yaratgan! 💻🔥\n\n"
        "Botdan foydalanish uchun iltimos, **Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`): 📧👇",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AuthState.waiting_for_email)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("🤖 **AURAgpt Yordam Bo'limi**\n\nBu bot **Bunyodbek Zokirov** tomonidan yaratilgan va to'liq erkin rejimda ishlaydi!", parse_mode="Markdown")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    total_users = len(verified_users_db)
    banned_users = len(banned_users_set)
    await message.answer(f"📊 Jami foydalanuvchilar: {total_users} ta\n🔴 Bloklanganlar: {banned_users} ta")

@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy Gmail manzilini kiriting:")
        return

    code = str(random.randint(100000, 999999))
    verification_codes[user_id] = code

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
        "textContent": f"Sizning tasdiqlash kodingiz: {code}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201, 202]:
            await state.update_data(email=email)
            await message.answer(f"📩 **{email}** manziliga kod yuborildi! Kodni kiriting:", parse_mode="Markdown")
            await state.set_state(AuthState.waiting_for_code)
        else:
            await message.answer(f"⚠️ Xatolik: {response.text}")
    except Exception as e:
        await message.answer(f"⚠️ Tarmoq xatoligi: {str(e)}")

@dp.message(AuthState.waiting_for_code, F.text)
async def process_code(message: types.Message, state: FSMContext):
    user_code = message.text.strip()
    user_id = message.from_user.id
    real_code = verification_codes.get(user_id)

    if user_code == real_code:
        data = await state.get_data()
        email = data.get("email")
        add_verified_user(user_id, email)
        get_user_history(user_id)
        
        await message.answer(
            "🎉 Tasdiqlandi! ✅ Endi bemalol xohlagan savolingizni yuborishingiz mumkin! 🚀",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(AuthState.authenticated)
    else:
        await message.answer("❌ Noto'g'ri kod! Qaytadan urinib ko'ring.")

# --- Barcha cheklovlar olib tashlandi: Matnlar, fayllar va havolalar bemalol qabul qilinadi ---
@dp.message(AuthState.authenticated)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        await message.answer("❌ Siz bloklangansiz!")
        return
    
    user_text = message.text or message.caption or "[Fayl yoki rasm yuborildi]"
    
    save_message_to_db(user_id, "user", user_text)
    current_history = get_user_history(user_id)

    response_text = None
    last_error = ""
    
    headers = {
        "Authorization": f"Bearer {WORMGPT_API_KEY}",
        "Content-Type": "application/json"
    }

    for model_name in MODELS_LIST:
        try:
            payload = {
                "model": model_name,
                "messages": current_history
            }
            response = requests.post(WORMGPT_URL, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                response_text = data["choices"][0]["message"]["content"]
                break
            else:
                last_error = response.text
        except Exception as e:
            last_error = str(e)
            continue  

    if response_text:
        save_message_to_db(user_id, "assistant", response_text)
        await message.answer(response_text, reply_markup=types.ReplyKeyboardRemove())
    else:
        await message.answer(f"⚠️ Xatolik:\n`{last_error}`", parse_mode="Markdown")

async def main():
    Thread(target=run_flask).start()
    print("Bot cheklovsiz WormGPT rejimi bilan ishga tushdi! 🚀🤖")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
