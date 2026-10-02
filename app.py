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
DATABASE_URL = os.getenv("DATABASE_URL")

MODELS_LIST = [
    "openai/gpt-oss-120b"
]

admin_env = os.getenv("ADMIN_ID")
ADMIN_ID = int(admin_env) if admin_env else 0  

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

# --- Sukinish va haqoratli so'zlar ro'yxati ---
BAD_WORDS = [
    "ahmoq", "tentak", "gandon", "mraz", "suka", "blat", "blyad", "dalbayob", 
    "chmo", "qnt", "qadam", "jalab", "qo'toq", "sikaman", "skaman", "qotoq"
]

# --- PostgreSQL Ma'lumotlar bazasini ulash va yaratish ---
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id BIGINT PRIMARY KEY,
            email TEXT,
            violations INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    conn.commit()

    try:
        cursor.execute('ALTER TABLE verified_users ADD COLUMN IF NOT EXISTS violations INTEGER DEFAULT 0;')
        conn.commit()
    except Exception:
        conn.rollback()
        
    try:
        cursor.execute('ALTER TABLE verified_users ADD COLUMN IF NOT EXISTS is_banned INTEGER DEFAULT 0;')
        conn.commit()
    except Exception:
        conn.rollback()

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
    return row is not None and row[0] == 1

def add_violation(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO verified_users (user_id, email, violations, is_banned) 
        VALUES (%s, 'Noma\'lum', 1, 0)
        ON CONFLICT (user_id) DO UPDATE SET violations = COALESCE(verified_users.violations, 0) + 1
    ''', (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

def add_verified_user(user_id: int, email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
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

# --- /users buyrug'i: Har bir foydalanuvchi alohida xabar va o'z tugmasi bilan ---
@dp.message(Command("users"))
async def show_users_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⚠ Kechirasiz, bu buyruq faqat admin uchun! 🚫")
        return  
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, email, violations, is_banned FROM verified_users')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not rows:
        await message.answer("📂 Hozircha bazada ro'yxatdan o'tgan foydalanuvchilar yo'q. 📭")
        return
    
    await message.answer(f"📋 <b>Tizimdagi jami foydalanuvchilar: {len(rows)} ta</b>", parse_mode="HTML")
    
    for idx, row in enumerate(rows, 1):
        uid = row[0]
        email = row[1] if row[1] else "Noma'lum"
        violations = row[2] if row[2] is not None else 0
        is_banned = row[3] if row[3] is not None else 0
        
        status_text = "🔴 Bloklangan" if is_banned == 1 else "🟢 Faol"
        
        text = (
            f"<b>{idx}.</b> 🆔 ID: <code>{uid}</code>\n"
            f"📧 Email: <code>{email}</code>\n"
            f"⚠️ Qoidabuzarlik: <b>{violations} ta</b> | {status_text}"
        )
        
        builder = InlineKeyboardBuilder()
        btn_text = f"🚫 Ban qilish ({violations} ta)" if is_banned == 0 else "✅ Unban qilish"
        callback_action = f"ban_{uid}" if is_banned == 0 else f"unban_{uid}"
        
        builder.button(text=btn_text, callback_data=callback_action)
        
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())

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
    cursor.close()
    conn.close()
    
    await callback.answer(msg, show_alert=True)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT email, violations, is_banned FROM verified_users WHERE user_id = %s', (uid,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if row:
            email = row[0] if row[0] else "Noma'lum"
            violations = row[1] if row[1] is not None else 0
            is_banned = row[2] if row[2] is not None else 0
            status_text = "🔴 Bloklangan" if is_banned == 1 else "🟢 Faol"
            
            updated_text = (
                f"🆔 ID: <code>{uid}</code>\n"
                f"📧 Email: <code>{email}</code>\n"
                f"⚠️ Qoidabuzarlik: <b>{violations} ta</b> | {status_text}"
            )
            builder = InlineKeyboardBuilder()
            btn_text = f"🚫 Ban qilish ({violations} ta)" if is_banned == 0 else "✅ Unban qilish"
            callback_action = f"ban_{uid}" if is_banned == 0 else f"unban_{uid}"
            builder.button(text=btn_text, callback_data=callback_action)
            
            await callback.message.edit_text(updated_text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        print(f"Xabarni yangilashda xato: {e}")

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
        f"⚠️️ Xatolik: {fail_count} ta",
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
            await message.answer(f"⚠️️ Xatolik (Brevo): {response.text}")
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
        add_violation(user_id)
        await message.answer("❌ Noto'g'ri kod! Qoidabuzarlik yozildi. Qayta urinib ko'ring. 🔄")

@dp.message(AuthState.authenticated, F.document | F.audio | F.video | F.photo)
async def check_bad_files(message: types.Message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        await message.answer("❌ Siz botdan bloklangansiz!")
        return

    add_violation(user_id)
    try:
        await message.delete()
    except Exception:
        pass
        
    await message.answer("⚠️ **Diqqat!** Botga zararli fayl yoki shubhali hujjat yuborish taqiqlangan! Qoidabuzarlik yozildi. 🚫")

@dp.message(AuthState.authenticated, F.text)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        await message.answer("❌ Siz bloklangansiz!")
        return
    
    text_lower = message.text.lower()
    
    if "http://" in text_lower or "https://" in text_lower or "www." in text_lower or ".ru" in text_lower or ".com" in text_lower and ("t.me/" not in text_lower):
        add_violation(user_id)
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer("⚠️ **Diqqat!** Botga shubhali yoki reklama havolalarini yuborish taqiqlangan! Qoidabuzarlik yozildi. 🚫")
        return

    for word in BAD_WORDS:
        if word in text_lower:
            add_violation(user_id)
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer("⚠️ **Ogohlantirish!** Botda so'kinish va haqorat qilish taqiqlangan! Qoidabuzarlik yozildi. 🚫")
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
    await dp.polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
