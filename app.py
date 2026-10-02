import asyncio
import random
import os
import psycopg2
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
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
DATABASE_URL = os.getenv("DATABASE_URL") # Render yoki boshqa hosting taqdim etadigan PostgreSQL ulanish manzili

MODELS_LIST = [
    "openai/gpt-oss-120b"
]

admin_env = os.getenv("ADMIN_ID")
ADMIN_ID = int(admin_env) if admin_env else 0  

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

# --- PostgreSQL Ma'lumotlar bazasini ulash va yaratish ---
def get_db_connection():
    # PostgreSQL bazasiga ulanish
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Tasdiqlangan foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id BIGINT PRIMARY KEY,
            email TEXT,
            violations INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    # Chat tarixini saqlash jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            role TEXT,
            content TEXT
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()

def is_user_verified(user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, is_banned FROM verified_users WHERE user_id = %s', (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row and row[1] == 1:
        return False 
    return row is not None

def is_user_banned(user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM verified_users WHERE user_id = %s', (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row and row[0] == 1

def add_verified_user(user_id: int, email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    # PostgreSQL uchun UPSERT (ON CONFLICT) so'rovi
    cursor.execute('''
        INSERT INTO verified_users (user_id, email, violations, is_banned) 
        VALUES (%s, %s, 0, 0)
        ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email
    ''', (user_id, email))
    conn.commit()
    cursor.close()
    conn.close()

def get_user_history(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT role, content FROM chat_history WHERE user_id = %s', (user_id,))
    rows = cursor.fetchall()
    cursor.close()
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO chat_history (user_id, role, content) VALUES (%s, %s, %s)', (user_id, role, content))
    conn.commit()
    
    cursor.execute('SELECT COUNT(*) FROM chat_history WHERE user_id = %s', (user_id,))
    count = cursor.fetchone()[0]
    if count > 21:
        cursor.execute('''
            DELETE FROM chat_history 
            WHERE id IN (
                SELECT id FROM chat_history 
                WHERE user_id = %s AND role != 'system' 
                ORDER BY id ASC LIMIT 2
            )
        ''', (user_id,))
        conn.commit()
    cursor.close()
    conn.close()

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
        await message.answer("❌ Siz botdan bloklangansiz! 🚫")
        return

    if is_user_verified(user_id):
        await message.answer(
            "✅ Siz allaqachon tizimdasiz! Menga istalgan tilda qiziqarli savollaringizni yuborishingiz mumkin! 🚀✨",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(AuthState.authenticated)
        return

    await message.answer(
        "🤖 **Assalomu alaykum!** Men **AURAgpt** sun'iy intellekt botiman! 🌟\n"
        "Meni juda iste'dodli dasturchi **Bunyodbek Zokirov** yaratganlar! 💻🔥✨\n\n"
        "🌐 Men 200 dan ortiq tillarda mukammal muloqot qila olaman!\n\n"
        "Botdan foydalanishni boshlash uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`): 📧👇",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AuthState.waiting_for_email)

@dp.message(Command("users"))
async def show_users_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return  
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, email, violations, is_banned FROM verified_users')
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not users:
        await message.answer("📂 Hozircha bazada ro'yxatdan o'tgan foydalanuvchilar yo'q. 📭")
        return
    
    text = "📋 **Tizimdagi barcha foydalanuvchilar:** 👥\n\n"
    builder = InlineKeyboardBuilder()
    
    for idx, (uid, email, violations, is_banned) in enumerate(users, 1):
        status_text = "🔴 Bloklangan" if is_banned else "🟢 Faol"
        text += f"{idx}. ID: `{uid}`\n   📧 Email: `{email}`\n   ⚠️ Qoidabuzarlik: {violations} ta | Status: {status_text}\n\n"
        
        if is_banned == 0:
            builder.button(text=f"🚫 Ban: {uid}", callback_data=f"ban_{uid}")
        else:
            builder.button(text=f"✅ Unban: {uid}", callback_data=f"unban_{uid}")
            
    builder.adjust(2)
    await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("ban_") | F.data.startswith("unban_"))
async def process_ban_unban(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!", show_alert=True)
        return
    
    action, uid_str = callback.data.split("_")
    uid = int(uid_str)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    if action == "ban":
        cursor.execute('UPDATE verified_users SET is_banned = 1 WHERE user_id = %s', (uid,))
        msg = f"Foydalanuvchi {uid} bloklandi! 🚫"
    else:
        cursor.execute('UPDATE verified_users SET is_banned = 0 WHERE user_id = %s', (uid,))
        msg = f"Foydalanuvchi {uid} blokdan chiqarildi! ✅"
    conn.commit()
    
    cursor.execute('SELECT user_id, email, violations, is_banned FROM verified_users')
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    text = "📋 **Tizimdagi barcha foydalanuvchilar:** 👥\n\n"
    builder = InlineKeyboardBuilder()
    
    for idx, (u_id, email, violations, is_banned) in enumerate(users, 1):
        status_text = "🔴 Bloklangan" if is_banned else "🟢 Faol"
        text += f"{idx}. ID: `{u_id}`\n   📧 Email: `{email}`\n   ⚠️ Qoidabuzarlik: {violations} ta | Status: {status_text}\n\n"
        
        if is_banned == 0:
            builder.button(text=f"🚫 Ban: {u_id}", callback_data=f"ban_{u_id}")
        else:
            builder.button(text=f"✅ Unban: {u_id}", callback_data=f"unban_{u_id}")
            
    builder.adjust(2)
    
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    except Exception:
        pass
    await callback.answer(msg)

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📢 **Xabar tarqatish rejimi:**\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_broadcast)

@dp.message(AuthState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM verified_users WHERE is_banned = 0')
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    success_count = 0
    fail_count = 0
    
    status_msg = await message.answer("⏳ Xabarlar tarqatilmoqda...")
    
    for (uid,) in users:
        try:
            await message.send_copy(chat_id=uid)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1
            
    await status_msg.edit_text(
        f"✅ **Xabar tarqatish yakunlandi!** 🚀\n\n"
        f"👥 Muvaffaqiyatli: {success_count} ta\n"
        f"⚠️ Xatolik: {fail_count} ta",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.authenticated)

@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        await message.answer("❌ Siz bloklangansiz!")
        return
        
    email = message.text.strip()
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy Gmail manzilini kiriting (masalan: `ismingiz@gmail.com`): 📩")
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
        "textContent": f"Sizning AURAgpt boti uchun tasdiqlash kodingiz: {code}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201, 202]:
            await state.update_data(email=email)
            await message.answer(f"📩 **{email}** manziliga kod yuborildi! 🔑 Kodni kiriting:", parse_mode="Markdown")
            await state.set_state(AuthState.waiting_for_code)
        else:
            await message.answer(f"⚠️ Xatolik (Brevo): {response.text}")
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
        
        try:
            if ADMIN_ID:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚡ **JONLI XABARNOMA!** 🔔\n\n🟢 Yangi foydalanuvchi kirdi: `user_{user_id}`\n📧 Email: `{email}`",
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(e)
        
        get_user_history(user_id)
        
        await message.answer(
            "🎉 Pochta tasdiqlandi! ✅ Endi bemalol savollaringizni yuborishingiz mumkin! 🚀💬",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(AuthState.authenticated)
    else:
        # Kod xato kiritilsa bazada qoidabuzarliklar sonini 1 taga oshiramiz
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO verified_users (user_id, email, violations, is_banned) 
            VALUES (%s, 'Noma\'lum', 1, 0)
            ON CONFLICT (user_id) DO UPDATE SET violations = verified_users.violations + 1
        ''', (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        await message.answer("❌ Noto'g'ri kod! Qayta urinib ko'ring. 🔄")

@dp.message(AuthState.authenticated, F.text)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        await message.answer("❌ Siz botdan bloklangansiz!")
        return
    
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
            continue  

    if response_text:
        save_message_to_db(user_id, "assistant", response_text)
        await message.answer(response_text, reply_markup=types.ReplyKeyboardRemove())
    else:
        await message.answer(f"⚠️ Xatolik:\n`{last_error}`", parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())

async def main():
    Thread(target=run_flask).start()
    print("Bot ishga tushdi! 🚀🤖")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
