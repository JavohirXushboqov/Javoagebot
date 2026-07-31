import os
import io
import math
import logging
import asyncio
from datetime import datetime, date
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta
import qrcode

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ==============================================================================
# 1. ATROF-MUHIT VA LOGGING SOZLAMALARI
# ==============================================================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@xushboqovblog")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "https://instagram.com/xuushboqov")

if not BOT_TOKEN:
    raise ValueError(".env faylida BOT_TOKEN topilmadi!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("JavoAgeBot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==============================================================================
# 2. FSM (HOLATLAR)
# ==============================================================================
class AgeCalcStates(StatesGroup):
    waiting_for_date = State()

# ==============================================================================
# 3. YOSH HISOBI VA ASTROLOGIYA LOGIKASI
# ==============================================================================
WEEKDAYS_UZ = [
    "Dushanba", "Seshanba", "Chorshanba", 
    "Payshanba", "Juma", "Shanba", "Yakshanba"
]

ZODIAC_SIGNS = [
    (1, 20, "Tog' echkisi ♑"), (2, 19, "Qovg'a ♒"), (3, 21, "Baliq ♓"),
    (4, 20, "Qo'y ♈"), (5, 21, "Buzaq ♉"), (6, 21, "Egizaklar ♊"),
    (7, 23, "Qisqichbaqa ♋"), (8, 23, "Arslon ♌"), (9, 23, "Parizod ♍"),
    (10, 23, "Tarozi ♎"), (11, 22, "Chayon ♏"), (12, 22, "O'qotar ♐"),
    (12, 32, "Tog' echkisi ♑")
]

CHINESE_ZODIAC = [
    "Sichqon 🐀", "Buqa 🐂", "Yo'lbars 🐅", "Quyon 🐇", 
    "Ajdarho 🐉", "Ilan 🐍", "Ot 🐎", "Qoy 🐐", 
    "Maymun 🐒", "Xo'roz 🐓", "It 🐕", "To'ng'iz 🐖"
]

def get_zodiac_sign(day: int, month: int) -> str:
    for m, d, sign in ZODIAC_SIGNS:
        if month == m and day < d:
            return sign
        elif month == m - 1 and day >= d:
            return sign
    return "Tog' echkisi ♑"

def get_chinese_zodiac(year: int) -> str:
    return CHINESE_ZODIAC[(year - 4) % 12]

def calculate_age_details(birth_date: date) -> Dict[str, Any]:
    today = date.today()
    delta = relativedelta(today, birth_date)
    total_days = (today - birth_date).days
    total_weeks = total_days // 7
    total_months = delta.years * 12 + delta.months

    next_birthday = date(today.year, birth_date.month, birth_date.day)
    if next_birthday < today:
        next_birthday = date(today.year + 1, birth_date.month, birth_date.day)
    
    days_to_next_birthday = (next_birthday - today).days

    return {
        "birth_date_str": birth_date.strftime("%d.%m.%Y"),
        "years": delta.years,
        "months": delta.months,
        "days": delta.days,
        "total_days": total_days,
        "total_weeks": total_weeks,
        "total_months": total_months,
        "days_to_next_birthday": days_to_next_birthday,
        "zodiac": get_zodiac_sign(birth_date.day, birth_date.month),
        "muchal": get_chinese_zodiac(birth_date.year),
        "weekday": WEEKDAYS_UZ[birth_date.weekday()]
    }

# ==============================================================================
# 4. PILLOW ULTA-HD KARTA GENERATSIYASI
# ==============================================================================
def draw_stat_card(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, title: str, val: str):
    # Karta foni
    draw.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=(30, 41, 59, 200), outline=(51, 65, 85, 255), width=2)
    # Sarlavha
    try:
        font_s = ImageFont.truetype("arial.ttf", 20)
        font_b = ImageFont.truetype("arialbd.ttf", 32)
    except:
        font_s = ImageFont.load_default()
        font_b = ImageFont.load_default()

    draw.text((x + 20, y + 15), title, fill=(148, 163, 184), font=font_s)
    draw.text((x + 20, y + 45), val, fill=(241, 245, 249), font=font_b)

def generate_age_card(data: Dict[str, Any], username: str) -> io.BytesIO:
    W, H = 1200, 800
    img = Image.new("RGBA", (W, H), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    # Gradient va orqa fon bezaklari
    for i in range(H):
        r = int(15 + (i / H) * 10)
        g = int(23 + (i / H) * 15)
        b = int(42 + (i / H) * 20)
        draw.line([(0, i), (W, i)], fill=(r, g, b, 255))

    # Yorituvchi doiralar (Glow effect)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-100, -100, 400, 400), fill=(99, 102, 241, 40))
    glow_draw.ellipse((900, 500, 1300, 900), fill=(168, 85, 247, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(80))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # Shriftlar
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 52)
        subtitle_font = ImageFont.truetype("arial.ttf", 26)
        main_font = ImageFont.truetype("arialbd.ttf", 72)
        sub_main_font = ImageFont.truetype("arialbd.ttf", 36)
        text_font = ImageFont.truetype("arial.ttf", 22)
    except:
        title_font = subtitle_font = main_font = sub_main_font = text_font = ImageFont.load_default()

    # Sarlavha paneli
    draw.text((60, 50), "JAVOAGE STATISTICS", fill=(99, 102, 241), font=title_font)
    draw.text((60, 115), f"Foydalanuvchi: @{username} | Sana: {data['birth_date_str']}", fill=(148, 163, 184), font=subtitle_font)
    draw.line([(60, 160), (W - 60, 160)], fill=(51, 65, 85), width=2)

    # Asosiy Yosh Blok (Katta)
    draw.rounded_rectangle([60, 190, 720, 360], radius=20, fill=(30, 41, 59, 230), outline=(99, 102, 241), width=3)
    draw.text((85, 210), "YOSHINGIZ:", fill=(148, 163, 184), font=subtitle_font)
    age_text = f"{data['years']} yosh, {data['months']} oy, {data['days']} kun"
    draw.text((85, 255), age_text, fill=(255, 255, 255), font=sub_main_font)

    # Mini Stat Kartalari (2x2 Grid)
    draw_stat_card(draw, 60, 380, 315, 110, "JAMI KUN", f"{data['total_days']:,} kun")
    draw_stat_card(draw, 395, 380, 325, 110, "JAMI HAFTA", f"{data['total_weeks']:,} hafta")
    draw_stat_card(draw, 60, 510, 315, 110, "JAMI OY", f"{data['total_months']:,} oy")
    draw_stat_card(draw, 395, 510, 325, 110, "KEYINGI TUG'ILGAN KUN", f"{data['days_to_next_birthday']} kun qoldi")

    # Astrologiya Bloki (O'ng tomon)
    draw.rounded_rectangle([750, 190, 1140, 620], radius=20, fill=(30, 41, 59, 230), outline=(168, 85, 247), width=3)
    draw.text((775, 215), "ASTROLOGIYA", fill=(168, 85, 247), font=sub_main_font)
    
    astro_items = [
        ("Tug'ilgan kun:", data['weekday']),
        ("Burjingiz:", data['zodiac']),
        ("Muchalingiz:", data['muchal'])
    ]
    ay = 290
    for label, val in astro_items:
        draw.text((775, ay), label, fill=(148, 163, 184), font=text_font)
        draw.text((775, ay + 30), val, fill=(241, 245, 249), font=subtitle_font)
        ay += 100

    # QR-Kod
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(INSTAGRAM_URL)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="white", back_color="transparent").convert("RGBA")
    qr_img = qr_img.resize((120, 120))
    img.paste(qr_img, (60, 645), qr_img)

    # Footer Text
    draw.text((200, 670), "JavoAgeBot — Professional Yosh Kalkulyatori", fill=(241, 245, 249), font=subtitle_font)
    draw.text((200, 710), f"Dasturchi: xuushboqov | Instagram: {INSTAGRAM_URL}", fill=(148, 163, 184), font=text_font)

    # Buferga saqlash
    bio = io.BytesIO()
    bio.name = "javoage_result.png"
    img.convert("RGB").save(bio, "PNG")
    bio.seek(0)
    return bio

# ==============================================================================
# 5. MAJBURIY OBUNA TEKSHIRISH MIDDLEWARE / FUNKSIYA
# ==============================================================================
async def check_subscription(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logger.warning(f"Kanal obunasini tekshirishda xato: {e}")
        return True

def get_sub_keyboard() -> InlineKeyboardMarkup:
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=channel_url)],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
        ]
    )

def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Yoshni hisoblash", callback_data="calc_age")],
            [InlineKeyboardButton(text="📱 Instagram", url=INSTAGRAM_URL)]
        ]
    )

# ==============================================================================
# 6. HANDLERLAR
# ==============================================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    is_subbed = await check_subscription(message.from_user.id)
    if not is_subbed:
        await message.answer(
            f"⚠️ **Botdan foydalanish uchun rasmiy kanalimizga obuna bo'lishingiz kerak:**\n{REQUIRED_CHANNEL}",
            reply_markup=get_sub_keyboard(),
            parse_mode="Markdown"
        )
        return

    text = (
        f"👋 **Salom, {message.from_user.full_name}!**\n\n"
        "**JavoAgeBot** ga xush kelibsiz. Men sizning aniq yoshingiz, yashagan kunlaringiz, "
        "burj va muchalingizni hisoblab, chiroyli natija kartasini tayyorlab beraman.\n\n"
        "Boshlash uchun pastdagi **'📅 Yoshni hisoblash'** tugmasini bosing."
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery):
    is_subbed = await check_subscription(call.from_user.id)
    if is_subbed:
        await call.message.delete()
        await call.message.answer(
            "✅ Obuna tasdiqlandi! Yoshni hisoblash tugmasini bosing:",
            reply_markup=get_main_keyboard()
        )
    else:
        await call.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

@dp.callback_query(F.data == "calc_age")
async def cb_start_calc(call: CallbackQuery, state: FSMContext):
    is_subbed = await check_subscription(call.from_user.id)
    if not is_subbed:
        await call.message.answer(
            "⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:",
            reply_markup=get_sub_keyboard()
        )
        await call.answer()
        return

    await state.set_state(AgeCalcStates.waiting_for_date)
    await call.message.answer(
        "📥 **Tug'ilgan sanangizni kiriting:**\n"
        "Format: `DD.MM.YYYY` (Masalan: `15.08.2005` yoki `01.01.2000`)",
        parse_mode="Markdown"
    )
    await call.answer()

@dp.message(AgeCalcStates.waiting_for_date)
async def process_date_input(message: types.Message, state: FSMContext):
    date_text = message.text.strip()
    try:
        birth_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        if birth_date > date.today():
            await message.answer("❌ Tug'ilgan sana kelajakda bo'lishi mumkin emas! Qayta kiriting:")
            return
        if birth_date.year < 1900:
            await message.answer("❌ Juda qadimiy sana. Iltimos, to'g'ri sana kiriting (1900-yildan keyin):")
            return
    except ValueError:
        await message.answer("❌ Noto'g'ri sana formati! Iltimos, `DD.MM.YYYY` formatida kiriting (Masalan: `24.12.2008`):", parse_mode="Markdown")
        return

    msg = await message.answer("🔄 **Hisoblanmoqda va Ultra-HD karta render qilinmoqda...**", parse_mode="Markdown")

    data = calculate_age_details(birth_date)
    username = message.from_user.username or message.from_user.first_name

    # Card render
    image_bytes = generate_age_card(data, username)
    photo = BufferedInputFile(image_bytes.read(), filename="javoage_result.png")

    caption = (
        f"📊 **JavoAge — HISOBOT NATIJASI**\n\n"
        f"👤 **Foydalanuvchi:** {message.from_user.full_name}\n"
        f"🎂 **Tug'ilgan sana:** `{data['birth_date_str']}` ({data['weekday']})\n\n"
        f"⏳ **Sizning yoshingiz:** {data['years']} yosh, {data['months']} oy, {data['days']} kun\n"
        f"🗓 **Jami yashagan kuningiz:** `{data['total_days']:,}` kun\n"
        f"📌 **Jami hafta:** `{data['total_weeks']:,}` | **Jami oy:** `{data['total_months']:,}`\n"
        f"🎁 **Keyingi tug'ilgan kunga:** `{data['days_to_next_birthday']}` kun qoldi\n\n"
        f"✨ **Burj:** {data['zodiac']}\n"
        f"🐉 **Muchal:** {data['muchal']}\n\n"
        f"Dasturchi: @xuushboqov"
    )

    await msg.delete()
    await message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    await state.clear()

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"⚙️ **Admin Panel**\n\nAdmin ID: `{ADMIN_ID}`\nBot holati: 🟢 Faol", parse_mode="Markdown")

# ==============================================================================
# 7. MAIN ISHGA TUSHRISH FUNKSIYASI
# ==============================================================================
async def main():
    logger.info("JavoAgeBot ishga tushmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi!")

