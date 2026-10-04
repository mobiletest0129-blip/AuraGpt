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
WORMGPT_API_KEY = "wgpt_724da8943f81918aec6daeb9fa741dd7aededbf44744c5d7"
WORMGPT_URL = "https://wormgpt.app/v1/chat/completions"

SENDER_EMAIL = os.getenv("SENDER_EMAIL")       
BREVO_API_KEY = os.getenv("BREVO_API_KEY")    

# Model nomi xatoligini oldini olish uchun yangilandi:
MODELS_LIST = [
    "wormgpt",
    "gpt-3.5-turbo"
]

# --- Adminlar ro'yxati ---
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_ID", "8795530550").split(",") if i.strip()]

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Xotiradagi ma'lumotlar bazasi (Database kerak emas) ---
verified_users_db = {}   # {user_id: email}
banned_users_set = set() # {user_id, ...}
user_violations_db = {}  # {user_id: violations_count}
chat_histories_db = {}   # {user_id: [messages]}

# --- Sukinish va haqoratli so'zlar ro'yxati ---
BAD_WORDS = [
    "ahmoq", "tentak", "gandon", "dalbayob", "chmo", "jalab", 
    "qo'toq", "sikaman", "skaman", "qotoq", "haromi", "iflos", "jinni", "eshak", 
    "blyad", "suka", "mraz", "gavno", "ebal", "ebat", "ebaniy",
    "pizda", "hui", "huy", "huesos", "mudak", "shlyuha", "pidor", "pidaras", "dolboyob"
]

def is_user_verified(user_id: int) -> bool:
    if user_id in banned_users_set:
        return False
    return user_id in verified_users_db

def is_user_banned(user_id: int) -> bool:
    return user_id in banned_users_set

def add_violation(user_id: int):
    user_violations_db[user_id] = user_violations_db.get(user_id, 0) + 1

def add_verified_user(user_id: int, email: str):
    verified_users_db[user_id] = email
    if user_id in banned_users_set:
        banned_users_set.remove(user_id)

def get_user_history(user_id: int):
    if user_id not in chat_histories_db:
        system_content = (
            "Sen AURAgpt nomli sun'iy intellekt botisan! 🤖✨ Seni Bunyodbek Zokirov ismli zo'r dasturchi yaratgan. "
            "Agar kimdir seni kim yasaganini so'rasa, har doim Bunyodbek Zokirov yasaganini katta faxr va quvonch bilan ayt! 😎💻 "
            "Sen dunyodagi 200 dan ortiq tillarni mukammal tushunasan va foydalanuvchi qaysi tilda yozsa, "
            "aynan o'sha tilda juda xushmuomala, iliq, ravon va aniq javob berasan. Har bir javobingda chiroyli va o'rinli smayliklardan (😊🔥🚀💡👍) faol foydalan!"
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
    waiting_for_feedback = State()

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

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user_id = message.from_user.id
    
    help_text = (
        "🤖 **AURAgpt Yordam Bo'limi** 🌟\n\n"
        "✨ **Bot haqida:**\n"
        "Men sun'iy intellekt yordamchisiman. Meni iste'dodli dasturchi **Bunyodbek Zokirov** yaratgan! 💻🔥\n"
        "200 dan ortiq tillarda istalgan mavzuda savollaringizga javob bera olaman.\n\n"
        "📌 **Asosiy qoidalar:**\n"
        "• Botga so'kinish va haqoratli so'zlar yozish taqiqlangan 🚫\n"
        "• Shubhali havolalar (linklar) yuborish taqiqlangan ⚠️\n"
        "• APK, EXE, iOS (.ipa) va boshqa fayllarni yuborish qat'iyan taqiqlangan va qoidabuzarlik sifatida yoziladi 🚫📂"
    )
    
    if user_id in ADMIN_IDS:
        help_text += (
            "\n\n👑 **Admin buyruqlari:**\n"
            "• /stats — Bot statistikasi\n"
            "• /users — Tizimdagi foydalanuvchilar ro'yxati va ularni tugma orqali Ban/Unban qilish\n"
            "• `/ban id:123456778` — Foydalanuvchini ban qilish, qayta yuborilsa unban qilish (toggle)\n"
            "• /broadcast — Barcha foydalanuvchilarga xabar tarqatish"
        )
        
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("ban"))
async def cmd_toggle_ban(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Kechirasiz, bu buyruq faqat admin uchun! 🚫")
        return
    
    text = message.text.strip()
    if "id:" not in text:
        await message.answer("⚠️ Noto'g'ri format! Ishlatish: `/ban id:123456778`", parse_mode="Markdown")
        return
    
    try:
        parts = text.split("id:")
        target_id_str = parts[1].strip().split()[0]
        target_id = int(target_id_str)
    except Exception:
        await message.answer("⚠️ ID noto'g'ri ko'rsatilgan! Ishlatish: `/ban id:123456778`", parse_mode="Markdown")
        return
    
    if target_id not in verified_users_db and target_id not in banned_users_set:
        await message.answer(f"❌ ID si `{target_id}` bo'lgan foydalanuvchi topilmadi!", parse_mode="Markdown")
        return
        
    email = verified_users_db.get(target_id, "Noma'lum")
    violations = user_violations_db.get(target_id, 0)
    
    if target_id in banned_users_set:
        banned_users_set.remove(target_id)
        new_ban_status = 0
    else:
        banned_users_set.add(target_id)
        new_ban_status = 1
    
    if new_ban_status == 1:
        await message.answer(
            f"🚫 **Foydalanuvchi muvaffaqiyatli BAN qilindi!**\n\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"📧 Email: <code>{email}</code>\n"
            f"⚠️ Qoidabuzarlik: <b>{violations} ta</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"✅ **Foydalanuvchi blokdan chiqarildi (UNBAN)!** 🎉\n\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"📧 Email: <code>{email}</code>\n"
            f"⚠️ Qoidabuzarlik: <b>{violations} ta</b>",
            parse_mode="HTML"
        )

@dp.message(Command("feedback"))
async def cmd_feedback(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        await message.answer("❌ Siz bloklangansiz!")
        return

    await message.answer(
        "✍️ **Taklif va shikoyatlar bo'limi:**\n\n"
        "Bot bo'yicha fikringiz, topgan xatolaringiz yoki yangi takliflaringizni shu yerga yozib yuboring. Xabaringiz to'g'ridan-to'g'ri dasturchiga yetkaziladi! 📨",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_feedback)

@dp.message(AuthState.waiting_for_feedback, F.text)
async def process_feedback(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    feedback_text = message.text

    await message.answer("✅ Rahmat! Sizning xabaringiz adminga yuborildi. 🚀", parse_mode="Markdown")
    
    try:
        user_info = f"👤 Foydalanuvchi: @{message.from_user.username}" if message.from_user.username else f"👤 Foydalanuvchi ID: `{user_id}`"
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📬 **YANGI FEEDBACK (XABAR)!** 💡\n\n"
                    f"{user_info}\n"
                    f"🆔 ID kodi: <code>{user_id}</code>\n\n"
                    f"💬 **Xabar matni:**\n{feedback_text}"
                ),
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"Feedback yuborishda xato: {e}")
        
    await state.set_state(AuthState.authenticated)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Kechirasiz, bu buyruq faqat admin uchun! 🚫")
        return
    
    total_users = len(verified_users_db)
    banned_users = len(banned_users_set)
    active_users = max(0, total_users - banned_users)
    total_violations = sum(user_violations_db.values())
    
    stats_text = (
        f"📊 **AURAgpt Statistikasi:** 📈\n\n"
        f"👥 Jami ro'yxatdan o'tganlar: **{total_users} ta**\n"
        f"🟢 Faol foydalanuvchilar: **{active_users} ta**\n"
        f"🔴 Bloklanganlar: **{banned_users} ta**\n"
        f"⚠️ Jami qoidabuzarliklar: **{total_violations} ta**"
    )
    
    await message.answer(stats_text, parse_mode="Markdown")

@dp.message(Command("users"))
async def show_users_list(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⚠️ Kechirasiz, bu buyruq faqat admin uchun! 🚫")
        return  
    
    if not verified_users_db:
        await message.answer("📂 Hozircha bazada ro'yxatdan o'tgan foydalanuvchilar yo'q. 📭")
        return
    
    await message.answer(f"📋 <b>Tizimdagi jami foydalanuvchilar: {len(verified_users_db)} ta</b>\n👇 Foydalanuvchini boshqarish uchun tugmani bosing:", parse_mode="HTML")
    
    for idx, (uid, email) in enumerate(verified_users_db.items(), 1):
        violations = user_violations_db.get(uid, 0)
        is_banned = 1 if uid in banned_users_set else 0
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
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Siz admin emassiz!", show_alert=True)
        return
    
    action, uid_str = callback.data.split("_")
    uid = int(uid_str)
    
    if action == "ban":
        banned_users_set.add(uid)
        msg = f"Foydalanuvchi {uid} bloklandi! 🚫"
    else:
        if uid in banned_users_set:
            banned_users_set.remove(uid)
        msg = f"Foydalanuvchi {uid} blokdan chiqarildi! ✅"
        
    await callback.answer(msg, show_alert=True)
    
    try:
        if uid in verified_users_db:
            email = verified_users_db[uid]
            violations = user_violations_db.get(uid, 0)
            is_banned = 1 if uid in banned_users_set else 0
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
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await message.answer(
        "📢 **Xabar tarqatish rejimi:**\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:",
        parse_mode="Markdown"
    )
    await state.set_state(AuthState.waiting_for_broadcast)

@dp.message(AuthState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    active_users_list = [uid for uid in verified_users_db.keys() if uid not in banned_users_set]
    
    success_count = 0
    fail_count = 0
    
    status_msg = await message.answer("⏳ Xabarlar tarqatilmoqda...")
    
    for uid in active_users_list:
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
            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    chat_id=admin_id,
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
        
    await message.answer("⚠️ **Diqqat!** Botga APK, EXE, iOS (.ipa) yoki boshqa turdagi fayllarni yuborish taqiqlangan! Qoidabuzarlik yozildi. 🚫")

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
        await message.answer(f"⚠ Xatolik:\n`{last_error}`", parse_mode="Markdown")

async def main():
    Thread(target=run_flask).start()
    print("Bot bazasiz va WormGPT orqali ishga tushdi! 🚀🤖")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
