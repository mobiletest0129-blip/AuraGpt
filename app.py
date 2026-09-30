import asyncio
import random
import os
import sqlite3
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import FSInputFile
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
SENDER_EMAIL = os.getenv("SENDER_EMAIL")       
BREVO_API_KEY = os.getenv("BREVO_API_KEY")    

# Admin ID ni muhit o'zgaruvchisidan o'qimiz (Render sozlamalariga ADMIN_ID yozib qo'yilishi shart)
admin_env = os.getenv("ADMIN_ID")
ADMIN_ID = int(admin_env) if admin_env else 0  

# Bot va Groq sozlamalari
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

# --- SQLITE BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id INTEGER PRIMARY KEY,
            email TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def is_user_verified(user_id: int) -> bool:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM verified_users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def add_verified_user(user_id: int, email: str):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO verified_users (user_id, email) VALUES (?, ?)', (user_id, email))
    conn.commit()
    conn.close()

def remove_verified_user(user_id: int):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM verified_users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, email FROM verified_users')
    rows = cursor.fetchall()
    conn.close()
    return rows

# Foydalanuvchi holatlari (FSM)
class AuthState(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()
    authenticated = State()

verification_codes = {}      
user_histories = {}          

def get_chat_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🚪 Chiqish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# /start buyrug'i
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if is_user_verified(user_id):
        await message.answer(
            "✅ Siz allaqachon tizimdasiz. Menga istalgan tilda istalgan savolingizni yuborishingiz mumkin!",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
        return

    await message.answer(
        "🤖 **Assalomu alaykum!** Men **AURAgpt** sun'iy intellekt botiman.\n"
        "Meni iste'dodli dasturchi **Bunyodbek Zokirov** yasaganlar! 💻✨\n\n"
        "🌐 Men 200 dan ortiq tillarda muloqot qila olaman.\n\n"
        "Botdan foydalanish uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`):",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_email)

# --- FAQAT ADMIN UCHUN /users BUYRUĞI ---
@dp.message(Command("users"))
async def show_users_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return  # Boshqa foydalanuvchilar uchun umuman javob bermaydi (sir saqlanadi)
    
    users = get_all_users()
    if not users:
        await message.answer("📂 Hozircha bazada ro'yxatdan o'tgan foydalanuvchilar yo'q.")
        return
    
    text = "📋 **Tizimdagi barcha foydalanuvchilar:**\n\n"
    for idx, (uid, email) in enumerate(users, 1):
        text += f"{idx}. ID: `{uid}`\n   📧 Email: `{email}`\n\n"
    
    await message.answer(text, parse_mode="Markdown")

# Emailni qabul qilish
@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy Gmail manzilini kiriting (masalan: `ismingiz@gmail.com`):")
        return

    code = str(random.randint(100000, 999999))
    verification_codes[message.from_user.id] = code

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

# Kodni tekshirish va ADMIN ga jonli xabar yuborish
@dp.message(AuthState.waiting_for_code, F.text)
async def process_code(message: types.Message, state: FSMContext):
    user_code = message.text.strip()
    real_code = verification_codes.get(message.from_user.id)

    if user_code == real_code:
        data = await state.get_data()
        email = data.get("email")
        user_id = message.from_user.id
        
        add_verified_user(user_id, email)
        
        try:
            if ADMIN_ID:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚡ **JONLI YANGILANISH!**\n\n"
                         f"🟢 Yangi foydalanuvchi kirdi:\n"
                         f"👤 ID: `{user_id}`\n"
                         f"📧 Email: `{email}`",
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"Adminni ogohlantirishda xato: {e}")
        
        user_histories[user_id] = [
            {
                "role": "system", 
                "content": (
                    "Sen AURAgpt nomli sun'iy intellekt botisan. Seni Bunyodbek Zokirov ismli dasturchi yasagan. "
                    "Agar kimdir seni kim yasaganini so'rasa, har doim Bunyodbek Zokirov yasaganini faxr bilan ayt. "
                    "Sen dunyodagi 200 dan ortiq tillarni mukammal tushunasan va foydalanuvchi qaysi tilda yozsa, "
                    "aynan o'sha tilda ravon va aniq javob berasan."
                )
            }
        ]
        
        await message.answer(
            "🎉 Tabriklayman! Pochta muvaffaqiyatli tasdiqlandi. Endi istalgan tilda savollaringizni berishingiz mumkin!",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
    else:
        await message.answer("❌ Noto'g'ri kod. Iltimos, pochtangizga kelgan kodni qaytadan kiriting:")

# Chiqish tugmasi va ADMIN ga jonli xabar
@dp.message(F.text == "🚪 Chiqish")
async def logout_user(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    remove_verified_user(user_id)
    
    if user_id in user_histories:
        del user_histories[user_id]
    if user_id in verification_codes:
        del verification_codes[user_id]
        
    await state.clear()
    
    try:
        if ADMIN_ID:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚡ **JONLI YANGILANISH!**\n\n"
                     f"🔴 Foydalanuvchi tizimdan chiqdi:\n"
                     f"👤 ID: `{user_id}`",
                parse_mode="Markdown"
            )
    except Exception as e:
        print(e)
    
    await message.answer(
        "🚪 Tizimdan muvaffaqiyatli chiqdingiz.\n"
        "Qaytadan kirish uchun /start buyrug'ini bosing.",
        reply_markup=types.ReplyKeyboardRemove()
    )

# Groq AI bilan muloqot
@dp.message(AuthState.authenticated, F.text)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_histories:
        user_histories[user_id] = [
            {
                "role": "system", 
                "content": (
                    "Sen AURAgpt nomli sun'iy intellekt botisan. Seni Bunyodbek Zokirov ismli dasturchi yasagan. "
                    "Agar kimdir seni kim yasaganini so'rasa, har doim Bunyodbek Zokirov yasaganini faxr bilan ayt. "
                    "Sen dunyodagi 200 dan ortiq tillarni mukammal tushunasan va foydalanuvchi qaysi tilda yozsa, "
                    "aynan o'sha tilda ravon va to'g'ri javob berasan."
                )
            }
        ]

    user_histories[user_id].append({"role": "user", "content": message.text})
    
    if len(user_histories[user_id]) > 21:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-20:]

    models = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b"
    ]

    response_text = None
    for model_name in models:
        try:
            completion = groq_client.chat.completions.create(
                model=model_name,
                messages=user_histories[user_id]
            )
            response_text = completion.choices[0].message.content
            break  
        except Exception as e:
            print(f"Model {model_name} xato berdi: {str(e)}")
            continue  

    if response_text:
        user_histories[user_id].append({"role": "assistant", "content": response_text})
        await message.answer(response_text, reply_markup=get_chat_keyboard())
    else:
        await message.answer("⚠ Hozirda sun'iy intellekt modellariga ulanishda xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.", reply_markup=get_chat_keyboard())

async def main():
    Thread(target=run_flask).start()
    print("Bot /users buyrug'i bilan ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
