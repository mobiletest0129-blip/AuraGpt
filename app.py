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
from groq import Groq
from flask import Flask
from threading import Thread

app_flask = Flask('')

@app_flask.route('/')
def home():
    return "AURAgpt Bot is active!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")       
BREVO_API_KEY = os.getenv("BREVO_API_KEY")    

# Groq Console da ko'rsatilgan model
MODELS_LIST = [
    "openai/gpt-oss-120b"
]

admin_env = os.getenv("ADMIN_ID")
ADMIN_ID = int(admin_env) if admin_env else 0  

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Tasdiqlangan foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id INTEGER PRIMARY KEY,
            email TEXT
        )
    ''')
    # Chat tarixini bazada saqlash jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
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
    # To'g'ri qo'shish va yangilash (ON CONFLICT)
    cursor.execute('''
        INSERT INTO verified_users (user_id, email) 
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET email=excluded.email
    ''', (user_id, email))
    conn.commit()
    conn.close()

def remove_verified_user(user_id: int):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM verified_users WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM chat_history WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, email FROM verified_users')
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- Bazadan chat tarixini boshqarish funksiyalari ---
def get_user_history(user_id: int):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT role, content FROM chat_history WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        system_content = (
            "Sen AURAgpt nomli sun'iy intellekt botisan! 🤖✨ Seni Bunyodbek Zokirov ismli zo'r dasturchi yaratgan. "
            "Agar kimdir seni kim yasaganini so'rasa, har doim Bunyodbek Zokirov yasaganini katta faxr va quvonch bilan ayt! 😎💻 "
            "Sen dunyodagi 200 dan ortiq tillarni mukammal tushunasan va foydalanuvchi qaysi tilda yozsa, "
            "aynan o'sha tilda juda xushmuomala, iliq, ravon va aniq javob berasan. Har bir javobingda chiroyli va o'rinli smayliklardan (😊🔥🚀💡👍) faol foydalan!"
        )
        save_message_to_db(user_id, "system", system_content)
        return [{"role": "system", "content": system_content}]
    
    history = [{"role": row[0], "content": row[1]} for row in rows]
    return history

def save_message_to_db(user_id: int, role: str, content: str):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)', (user_id, role, content))
    conn.commit()
    
    cursor.execute('SELECT COUNT(*) FROM chat_history WHERE user_id = ?', (user_id,))
    count = cursor.fetchone()[0]
    if count > 21:
        cursor.execute('''
            DELETE FROM chat_history 
            WHERE id IN (
                SELECT id FROM chat_history 
                WHERE user_id = ? AND role != 'system' 
                ORDER BY id ASC LIMIT 2
            )
        ''', (user_id,))
        conn.commit()
    conn.close()
# ------------------------------------------------------

class AuthState(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()
    authenticated = State()
    waiting_for_broadcast = State()

verification_codes = {}      

def get_chat_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🚪 Chiqish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if is_user_verified(user_id):
        await message.answer(
            "✅ Siz allaqachon tizimdasiz! Menga istalgan tilda qiziqarli savollaringizni yuborishingiz mumkin! 🚀✨",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
        return

    await message.answer(
        "🤖 **Assalomu alaykum!** Men **AURAgpt** sun'iy intellekt botiman! 🌟\n"
        "Meni juda iste'dodli dasturchi **Bunyodbek Zokirov** yaratganlar! 💻🔥✨\n\n"
        "🌐 Men 200 dan ortiq tillarda mukammal muloqot qila olaman!\n\n"
        "Botdan foydalanishni boshlash uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`): 📧👇",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_email)

@dp.message(Command("users"))
async def show_users_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return  
    
    users = get_all_users()
    if not users:
        await message.answer("📂 Hozircha bazada ro'yxatdan o'tgan foydalanuvchilar yo'q. 📭")
        return
    
    text = "📋 **Tizimdagi barcha foydalanuvchilar:** 👥\n\n"
    for idx, (uid, email) in enumerate(users, 1):
        text += f"{idx}. ID: `{uid}`\n   📧 Email: `{email}`\n\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📢 **Xabar tarqatish rejimi:**\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni (matn, rasm yoki post) yuboring:",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_broadcast)

@dp.message(AuthState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = get_all_users()
    success_count = 0
    fail_count = 0
    
    status_msg = await message.answer("⏳ Xabarlar tarqatilmoqda, iltimos kuting...")
    
    for uid, _ in users:
        try:
            await message.send_copy(chat_id=uid)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1
            
    await status_msg.edit_text(
        f"✅ **Xabar tarqatish yakunlandi!** 🚀\n\n"
        f"👥 Muvaffaqiyatli yuborildi: {success_count} ta\n"
        f"⚠️ Xatolik yuz berdi: {fail_count} ta",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.authenticated)

@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy Gmail manzilini to'g'ri kiriting (masalan: `ismingiz@gmail.com`): 📩")
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
            await message.answer(f"📩 **{email}** manziliga 6 xonali tasdiqlash kodi yuborildi! 🔑 Iltimos, kodni kiriting:", parse_mode="Markdown")
            await state.set_state(AuthState.waiting_for_code)
        else:
            await message.answer(f"⚠️ Xatolik (Brevo): {response.text}")
    except Exception as e:
        await message.answer(f"⚠️ Tarmoq xatoligi yuz berdi: {str(e)}")

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
                    text=f"⚡ **JONLI XABARNOMA!** 🔔\n\n"
                         f"🟢 Yangi foydalanuvchi kirdi: 🎉\n"
                         f"👤 ID: `{user_id}`\n"
                         f"📧 Email: `{email}`",
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"Adminni ogohlantirishda xato: {e}")
        
        get_user_history(user_id)
        
        await message.answer(
            "🎉 Tabriklayman! Pochta muvaffaqiyatli tasdiqlandi! ✅ Endi istalgan tilda o'zingizni qiziqtirgan savollarni berishingiz mumkin! 🚀💬",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
    else:
        await message.answer("❌ Noto'g'ri kod kiritdingiz! 🔄 Iltimos, pochtangizga kelgan kodni qaytadan tekshirib kiriting: 📩")

@dp.message(F.text == "🚪 Chiqish")
async def logout_user(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    remove_verified_user(user_id)
    
    if user_id in verification_codes:
        del verification_codes[user_id]
        
    await state.clear()
    
    try:
        if ADMIN_ID:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚡ **JONLI XABARNOMA!** 🔔\n\n"
                     f"🔴 Foydalanuvchi tizimdan chiqdi: 🚪\n"
                     f"👤 ID: `{user_id}`",
                parse_mode="Markdown"
            )
    except Exception as e:
        print(e)
    
    await message.answer(
        "🚪 Tizimdan muvaffaqiyatli chiqdingiz! 👋\n"
        "Qaytadan kirish uchun /start buyrug'ini bosing. ✨",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(AuthState.authenticated, F.text)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    
    save_message_to_db(user_id, "user", message.text)
    current_history = get_user_history(user_id)

    response_text = None
    last_error = ""
    for model_name in MODELS_LIST:
        try:
            completion = groq_client.chat.completions.create(
                model=model_name,
                messages=current_history
            )
            response_text = completion.choices[0].message.content
            break  
        except Exception as e:
            last_error = str(e)
            print(f"Model {model_name} xato berdi: {last_error}")
            continue  

    if response_text:
        save_message_to_db(user_id, "assistant", response_text)
        await message.answer(response_text, reply_markup=get_chat_keyboard())
    else:
        await message.answer(f"⚠️ Xatolik tafsiloti:\n`{last_error}`", parse_mode="Markdown", reply_markup=get_chat_keyboard())

async def main():
    Thread(target=run_flask).start()
    print("Bot muvaffaqiyatli ishga tushdi! 🚀🤖")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
