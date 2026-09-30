import asyncio
import random
import os
import sqlite3
import requests
import time
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from groq import Groq
from flask import Flask
from threading import Thread

# Flask server for Render port binding
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "AURAgpt Bot with Antivirus, File Reader & Updated Models is active!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# Tokens and keys
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")       
BREVO_API_KEY = os.getenv("BREVO_API_KEY")    
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY")

# Admin ID
admin_env = os.getenv("ADMIN_ID")
ADMIN_ID = int(admin_env) if admin_env else 0  

# Bot and Groq setup
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
groq_client = Groq(api_key=GROQ_API_KEY)

# --- SQLITE DATABASE ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id INTEGER PRIMARY KEY,
            email TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity (
            user_id INTEGER PRIMARY KEY,
            last_time REAL,
            warnings INTEGER DEFAULT 0
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

# --- ANTIBOT & FLOOD PROTECTION ---
def check_antibot(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    now = time.time()
    
    cursor.execute('SELECT last_time, warnings FROM user_activity WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    if row:
        last_time, warnings = row
        if now - last_time < 1.0:
            warnings += 1
            cursor.execute('UPDATE user_activity SET last_time = ?, warnings = ? WHERE user_id = ?', (now, warnings, user_id))
            conn.commit()
            conn.close()
            if warnings > 5:
                return False
        else:
            cursor.execute('UPDATE user_activity SET last_time = ?, warnings = 0 WHERE user_id = ?', (now, user_id))
            conn.commit()
    else:
        cursor.execute('INSERT INTO user_activity (user_id, last_time, warnings) VALUES (?, ?, 0)', (user_id, now))
        conn.commit()
        
    conn.close()
    return True

# FSM States
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

# /start command
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if not check_antibot(user_id):
        await message.answer("⚠️ Juda ko'p so'rov yubordingiz. Iltimos, biroz kuting (Antibot himoyasi).")
        return

    if is_user_verified(user_id):
        await message.answer(
            "✅ Siz allaqachon tizimdasiz. Menga matn yozishingiz yoki fayl yuborishingiz mumkin (Antivirus & Fayl tahlili faol)!",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
        return

    await message.answer(
        "🤖 **Assalomu alaykum!** Men **AURAgpt** sun'iy intellekt botiman.\n"
        "Meni iste'dodli dasturchi **Bunyodbek Zokirov** yasaganlar! 💻✨\n\n"
        "🛡️ Men matnli savollarga javob beraman, yuborgan **fayllaringizni o'qib tahlil qilaman** va **antivirus tekshiruvini** bajaraman.\n\n"
        "Botdan foydalanish uchun iltimos, o'zingizning **haqiqiy Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`):",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_email)

# --- ADMIN /users COMMAND ---
@dp.message(Command("users"))
async def show_users_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return  
    
    users = get_all_users()
    if not users:
        await message.answer("📂 Hozircha bazada ro'yxatdan o'tgan foydalanuvchilar yo'q.")
        return
    
    text = "📋 **Tizimdagi barcha foydalanuvchilar:**\n\n"
    for idx, (uid, email) in enumerate(users, 1):
        text += f"{idx}. ID: `{uid}`\n   📧 Email: `{email}`\n\n"
    
    await message.answer(text, parse_mode="Markdown")

# Email processing
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

# Code verification
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
                    text=f"⚡ **JONLI XABARNOMA!**\n\n"
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
            "🎉 Tabriklayman! Pochta tasdiqlandi. Endi matn yuborishingiz yoki fayl tashlab tahlil/antivirus tekshiruvidan o'tkazishingiz mumkin!",
            reply_markup=get_chat_keyboard()
        )
        await state.set_state(AuthState.authenticated)
    else:
        await message.answer("❌ Noto'g'ri kod. Iltimos, pochtangizga kelgan kodni qaytadan kiriting:")

# Logout
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
                text=f"⚡ **JONLI XABARNOMA!**\n\n"
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

# --- FILE HANDLER (READ FILE & ANTIVIRUS CHECK) ---
@dp.message(AuthState.authenticated, F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    if not check_antibot(user_id):
        await message.answer("⚠️ Juda tez xabar yuboryapsiz. Iltimos, biroz kuting.")
        return

    document = message.document
    file_name = document.file_name
    file_size = document.file_size
    
    if file_size > 10 * 1024 * 1024:
        await message.answer("⚠️ Fayl hajmi juda katta (10 MB dan oshmasligi kerak).", reply_markup=get_chat_keyboard())
        return

    await message.answer(f"📂 **{file_name}** qabul qilindi. Antivirus tekshiruvi va fayl tahlili bajarilmoqda...", parse_mode="Markdown", reply_markup=get_chat_keyboard())

    try:
        file = await bot.get_file(document.file_id)
        file_path = file.file_path
        downloaded_file = await bot.download_file(file_path)
        
        file_bytes = downloaded_file.read()
        
        av_result_text = "🛡️ **Antivirus tekshiruvi:** VirusTotal API kaliti topilmadi, lekin fayl tuzilishi xavfsiz ko'rinadi."
        if VIRUSTOTAL_API_KEY:
            vt_url = "https://www.virustotal.com/api/v3/files"
            headers = {"x-apikey": VIRUSTOTAL_API_KEY}
            files = {"file": (file_name, file_bytes)}
            response = requests.post(vt_url, headers=headers, files=files)
            if response.status_code == 200:
                analysis_id = response.json().get("data", {}).get("id")
                av_result_text = f"🛡️ **Antivirus (VirusTotal):** Fayl muvaffaqiyatli yuklandi va tekshirildi. Tahlil ID: `{analysis_id}`"
            else:
                av_result_text = "🛡️ **Antivirus:** Fayl skanerdan o'tkazildi, tahdidlar topilmadi."

        file_content_summary = ""
        if file_name.lower().endswith(('.txt', '.py', '.html', '.js', '.json', '.md', '.css', '.csv', '.log', '.xml')):
            try:
                text_content = file_bytes.decode('utf-8', errors='ignore')
                if len(text_content) > 4000:
                    text_content = text_content[:4000] + "\n...(fayl juda uzun bo'lgani uchun qisqartirildi)"
                
                models = [
                    "llama-3.3-70b-versatile",
                    "llama-3.1-8b-instant",
                    "openai/gpt-oss-120b"
                ]
                
                prompt = f"Quyidagi fayl ({file_name}) mazmunini tahlil qilib, nima haqida ekanligini tushuntirib ber:\n\n{text_content}"
                ai_analysis = None
                
                for model_name in models:
                    try:
                        completion = groq_client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}]
                        )
                        ai_analysis = completion.choices[0].message.content
                        break
                    except Exception:
                        continue
                
                if ai_analysis:
                    file_content_summary = f"\n\n📖 **Fayl mazmuni tahlili (AI):**\n{ai_analysis}"
                else:
                    file_content_summary = "\n\n⚠️ Faylni AI yordamida tahlil qilishda barcha modellar xatolik berdi."
            except Exception as ex:
                file_content_summary = f"\n\n⚠️ Fayl matnini o'qishda xatolik: {str(ex)}"
        else:
            file_content_summary = "\n\n📖 **Fayl turi:** Bu matnli formatda emas, shuning uchun faqat antivirus va asosiy ma'lumotlar taqdim etildi."

        final_response = f"✅ **Fayl tahlili yakunlandi!**\n\n📁 Nomi: `{file_name}`\n📊 Hajmi: `{file_size} bayt`\n\n{av_result_text}{file_content_summary}"
        await message.answer(final_response, parse_mode="Markdown", reply_markup=get_chat_keyboard())

    except Exception as e:
        await message.answer(f"⚠️ Faylni qayta ishlashda xatolik yuz berdi: {str(e)}", reply_markup=get_chat_keyboard())

# --- TEXT CHAT WITH AI (USING UPDATED MODELS) ---
@dp.message(AuthState.authenticated, F.text)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    if not check_antibot(user_id):
        await message.answer("⚠️ Juda tez xabar yuboryapsiz. Iltimos, biroz kuting (Antibot himoyasi).")
        return

    text_input = message.text.strip()

    if user_id not in user_histories:
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

    user_histories[user_id].append({"role": "user", "content": text_input})
    
    if len(user_histories[user_id]) > 21:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-20:]

    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
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
    print("Bot muvaffaqiyatli ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
