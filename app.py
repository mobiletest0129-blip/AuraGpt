import asyncio
import random
import os
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
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
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SENDER_EMAIL = os.getenv("SENDER_EMAIL")       
BREVO_API_KEY = os.getenv("BREVO_API_KEY")    

MODELS = [
    "openai/gpt-oss-120b",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768"
]

# Admin ID raqamlari endi Render Environment Variables orqali o'qiladi (vergul bilan ajratib yoziladi)
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_ID", "").split(",") if i.strip()]

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
            "Sen 200 dan ortiq tillarni mukammal tushunasan va foydalanuvchi qaysi tilda yozsa, aynan o'sha tilda javob berasan. "
            "Har bir javobingni chiroyli smayliklar (emojilar) bilan bezatib, juda qiziqarli va jonli tarzda yubor! 🔥🚀"
        )
        chat_histories_db[user_id] = [{"role": "system", "content": system_content}]
    return chat_histories_db[user_id]

def save_message_to_db(user_id: int, role: str, content: str):
    history = get_user_history(user_id)
    history.append({"role": role, "content": content})

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
        await message.answer("❌ Kechirasiz, siz botdan bloklangansiz! 🚫")
        return

    if is_user_verified(user_id):
        await message.answer(
            "✅ Siz allaqachon tizimdasiz! Menga istalgan savolingizni yuborishingiz mumkin! 🚀🔥",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(AuthState.authenticated)
        return

    await message.answer(
        "🤖 **Assalomu alaykum!** Men tezkor **AURAgpt** botiman! 🌟✨\n"
        "Meni buyuk dasturchi **Bunyodbek Zokirov** yaratgan! 💻😎🔥\n\n"
        "Botdan foydalanish uchun iltimos, o'zingizning **Gmail manzilingizni** kiriting (masalan: `ismingiz@gmail.com`): 📧👇",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AuthState.waiting_for_email)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🤖 **AURAgpt Yordam Bo'limi** 💡\n\n"
        "Bu bot iste'dodli dasturchi **Bunyodbek Zokirov** tomonidan yaratilgan! 🚀🔥\n\n"
        "📌 **Asosiy buyruqlar:**\n"
        "• /start - Botni qayta ishga tushirish va ro'yxatdan o'tish 🌟\n"
        "• /help - Yordam olish ℹ️\n\n"
        "🛠 **Admin buyruqlari:**\n"
        "• /stats - Bot statistikasi 📊\n"
        "• /ban [user_id] - Foydalanuvchini bloklash 🔴\n"
        "• /unban [user_id] - Blokdan chiqarish 🟢\n"
        "• /broadcast - Barcha foydalanuvchilarga xabar yuborish 📢",
        parse_mode="Markdown"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    total_users = len(verified_users_db)
    banned_users = len(banned_users_set)
    await message.answer(f"📊 **Statistika:**\n\n👥 Jami foydalanuvchilar: {total_users} ta 🌐\n🔴 Bloklanganlar: {banned_users} ta ⚠️", parse_mode="Markdown")

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Foydalanish: `/ban [user_id]`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        banned_users_set.add(target_id)
        if target_id in verified_users_db:
            del verified_users_db[target_id]
        await message.answer(f"✅ `{target_id}` ID raqamli foydalanuvchi bloklandi! 🔴", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Noto'g'ri ID format!")

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Foydalanish: `/unban [user_id]`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        if target_id in banned_users_set:
            banned_users_set.remove(target_id)
            await message.answer(f"✅ `{target_id}` ID raqamli foydalanuvchi blokdan chiqarildi! 🟢", parse_mode="Markdown")
        else:
            await message.answer("⚠️️ Bu foydalanuvchi bloklanganlar ro'yxatida yo'q.")
    except ValueError:
        await message.answer("❌ Noto'g'ri ID format!")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:")
    await state.set_state(AuthState.waiting_for_broadcast)

@dp.message(AuthState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    broadcast_text = message.text or message.caption or "[Media xabar]"
    success = 0
    fail = 0

    for user_id in verified_users_db.keys():
        try:
            await bot.send_message(user_id, f"📢 **E'lon / Xabar:**\n\n{broadcast_text}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1

    await message.answer(f"✅ Xabar tarqatildi!\n\n📤 Muvaffaqiyatli: {success} ta\n❌ Xatoliklar: {fail} ta")
    await state.set_state(AuthState.authenticated)

@dp.message(AuthState.waiting_for_email, F.text)
async def process_email(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    email = message.text.strip()
    
    if not email.endswith("@gmail.com"):
        await message.answer("⚠️ Iltimos, haqiqiy va to'g'ri Gmail manzilini kiriting! 📧🔄")
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
            await message.answer(f"📩 **{email}** manziliga tasdiqlash kodi yuborildi! 🚀 Kodni kiriting: 🔢👇", parse_mode="Markdown")
            await state.set_state(AuthState.waiting_for_code)
        else:
            await message.answer(f"⚠️ Xatolik yuz berdi: {response.text} ❌")
    except Exception as e:
        await message.answer(f"⚠️ Tarmoq xatoligi: {str(e)} 🔌")

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
            "🎉 Tabriklayman, muvaffaqiyatli tasdiqlandi! ✅✨ Endi bemalol xohlagan savolingizni yuborishingiz mumkin! 🚀🔥",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(AuthState.authenticated)
    else:
        await message.answer("❌ Noto'g'ri kod kiritdingiz! 🔄 Qaytadan urinib ko'ring. 🤔")

@dp.message(AuthState.authenticated)
async def chat_with_ai(message: types.Message):
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        await message.answer("❌ Kechirasiz, siz bloklangansiz! 🚫")
        return
    
    user_text = message.text or message.caption or "[Fayl yoki rasm yuborildi] 📁🖼️"
    
    save_message_to_db(user_id, "user", user_text)
    current_history = get_user_history(user_id)

    response_text = None
    last_error = ""
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    for model_name in MODELS:
        try:
            payload = {
                "model": model_name,
                "messages": current_history[-1000000:]
            }
            response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=60)
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
        await message.answer(f"⚠️ Xatolik yuz berdi:\n`{last_error}` ❌", parse_mode="Markdown")

async def main():
    Thread(target=run_flask).start()
    print("Bot xavfsiz holatda ishga tushdi! 🚀🤖✨")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
