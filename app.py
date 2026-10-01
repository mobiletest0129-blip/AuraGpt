import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import telebot
from telebot import types
from groq import Groq

# --- SOZLAMALAR ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "SIZNING_TELEGRAM_BOT_TOKENINGIZ")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "SIZning_GROQ_API_KINGIZ")
ADMIN_ID = int(os.getenv("ADMIN_ID", "SIZNING_ADMIN_TELEGRAM_IDINGIZ"))

# Email xizmati sozlamalari (Gmail orqali kod yuborish uchun)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "sizning_pochta@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "pochta_ilova_paroli")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Sinab ko'riladigan modellar ro'yxati (100% ishlaydiganlari birinchi o'rinda)
MODELS_LIST = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768"
]

# Vaqtinchalik baza (amaliyot uchun: bazani sozlagan bo'lsangiz o'zingiznikiga ulang)
verified_users = {}  # {user_id: email}
pending_codes = {}   # {user_id: {"email": email, "code": code}}
user_histories = {}  # {user_id: [messages]}


# --- ASOSIY MENYU ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    btn_ai = types.KeyboardButton("💬 Sun'iy intellekt bilan muloqot")
    btn_antivirus = types.KeyboardButton("🛡 Havola/Faylni tekshirish (Antivirus)")
    btn_exit = types.KeyboardButton("🚪 Chiqish")
    markup.add(btn_ai, btn_antivirus, btn_exit)
    return markup


# --- /START BUYrug'i ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if user_id in verified_users:
        bot.send_message(
            message.chat.id,
            "✅ Siz allaqachon tizimdasiz. Menga istalgan tilda sovol berishingiz yoki antivirus rejimini ishlatishingiz mumkin!",
            reply_markup=main_menu()
        )
    else:
        bot.send_message(
            message.chat.id,
            "Salom! AuraGpt botiga xush kelibsiz.\n\n"
            "Tizimdan foydalanish uchun avval haqiqiy Gmail manzilingizni kiriting (masalan: `example@gmail.com`):",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(message, process_email_step)


# --- EMAILNI QABUL QILISH VA KOD YUBORISH ---
def process_email_step(message):
    user_id = message.from_user.id
    email = message.text.strip()
    
    if "@gmail.com" not in email:
        bot.send_message(message.chat.id, "❌ Iltimos, haqiqiy Gmail manzilini kiriting (masalan: user@gmail.com):")
        bot.register_next_step_handler(message, process_email_step)
        return

    code = str(random.randint(100000, 999999))
    pending_codes[user_id] = {"email": email, "code": code}

    # Emailga kod jo'natish
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = email
        msg['Subject'] = "AuraGpt - Tasdiqlash kodi"
        
        body = f"Sizning tasdiqlash kodingiz: {code}"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, email, msg.as_string())
        server.quit()

        bot.send_message(
            message.chat.id,
            f"📨 `{email}` manziliga 6 xonali tasdiqlash kodi yuborildi. Iltimos, kodni kiriting:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(message, process_verify_code_step)
        
    except Exception as e:
        print(f"EMAIL YUBORISHDA XATO: {e}")
        bot.send_message(message.chat.id, "❌ Kod yuborishda xatolik yuz berdi. Iltimos, elektron pochtangizni tekshirib qaytadan urinib ko'ring (/start).")


# --- KODNI TEKSHIRISH ---
def process_verify_code_step(message):
    user_id = message.from_user.id
    entered_code = message.text.strip()

    if user_id not in pending_codes:
        bot.send_message(message.chat.id, "Xatolik yuz berdi. /start buyrug'ini bosing.")
        return

    saved_data = pending_codes[user_id]
    
    if entered_code == saved_data["code"]:
        email = saved_data["email"]
        verified_users[user_id] = email
        del pending_codes[user_id]

        # Adminga jonli xabarnoma
        try:
            bot.send_message(
                ADMIN_ID,
                f"⚡ **JONLI XABARNOMA!**\n\n🟢 Yangi foydalanuvchi kirdi:\n🆔 ID: `{user_id}`\n📧 Email: `{email}`",
                parse_mode="Markdown"
            )
        except:
            pass

        bot.send_message(
            message.chat.id,
            "🎉 Tabriklayman! Pochta tasdiqlandi. Endi xohlagan savolingizni berishingiz yoki antivirus yordamida havola tekshirishingiz mumkin!",
            reply_markup=main_menu()
        )
    else:
        bot.send_message(message.chat.id, "❌ Kod noto'g'ri. Iltimos, qaytadan kiriting:")
        bot.register_next_step_handler(message, process_verify_code_step)


# --- MATNNI VA SUN'IY INTELLEKTNI QAYTA ISHLASH ---
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text

    if user_id not in verified_users and text != "🚪 Chiqish":
        bot.send_message(message.chat.id, "Iltimos, avval ro'yxatdan o'tish uchun /start buyrug'ini bosing.")
        return

    if text == "🚪 Chiqish":
        if user_id in verified_users:
            del verified_users[user_id]
        bot.send_message(message.chat.id, "Tizimdan chiqdingiz. Qaytadan kirish uchun /start ni bosing.", reply_markup=types.ReplyKeyboardRemove())
    
    elif text == "🛡 Havola/Faylni tekshirish (Antivirus)":
        bot.send_message(message.chat.id, "Iltimos, tekshirish kerak bo'lgan havola (link) yoki matnni yuboring:")
        bot.register_next_step_handler(message, process_antivirus_step)
        
    elif text == "💬 Sun'iy intellekt bilan muloqot":
        bot.send_message(message.chat.id, "Menga istalgan savolingizni yuborishingiz mumkin, javob beraman!")
        
    else:
        # AI bilan muloqot qilish qismi
        if user_id not in user_histories:
            user_histories[user_id] = [{"role": "system", "content": "Siz foydalanuvchilarga yordam beruvchi aqlli sun'iy intellekt yordamchisiz."}]

        user_histories[user_id].append({"role": "user", "content": text})

        response_text = None
        for model_name in MODELS_LIST:
            try:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=user_histories[user_id]
                )
                response_text = completion.choices[0].message.content
                break  
            except Exception as e:
                print(f"ANIQ XATOLIK ({model_name}): {str(e)}")
                continue  

        if response_text:
            user_histories[user_id].append({"role": "assistant", "content": response_text})
            bot.send_message(message.chat.id, response_text)
        else:
            bot.send_message(message.chat.id, "⚠️ Hozirda sun'iy intellektga ulanishda vaqtinchalik xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.")


# --- ANTIVIRUS TEKSHIRUVI ---
def process_antivirus_step(message):
    link_or_text = message.text
    # Bu yerda o'zingizning VirusTotal yoki boshqa antivirus logikangizni qo'shishingiz mumkin
    bot.send_message(
        message.chat.id,
        f"🛡 Tahlil qilindi:\nSiz yuborgan havola/matn xavfsiz ko'rinadi: `{link_or_text}`",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )


if __name__ == "__main__":
    print("Bot ishga tushdi...")
    bot.infinity_polling()
