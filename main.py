import os
import io
import logging
import asyncio
import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, Any, Callable

from dateutil.relativedelta import relativedelta

from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile, TelegramObject
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

from PIL import Image, ImageDraw, ImageFont

# config.py faylidan yuklab olish
try:
    from config import DEVELOPER_ID
except ImportError:
    DEVELOPER_ID = 0

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("JavoAgeBot")

# ==============================================================================
# CONFIG & CONSTANTS
# ==============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REQUIRED_CHANNEL = "@xushboqovblog"
BOT_NAME = "JavoAgeBot"
BOT_USERNAME = "@JavoAgeBot"
DEVELOPER = "@XushboqovJavohir"
INSTAGRAM_CONTACT = "@xuushboqov"
INSTAGRAM_URL = "https://instagram.com/xuushboqov"

DB_FILE = "bot_stats.db"

# ==============================================================================
# DATABASE INITIALIZATION
# ==============================================================================
def init_db():
    try:
        with sqlite3.connect(DB_FILE, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    joined_date TEXT
                )
            """)
            conn.commit()
            logger.info("Baza muvaffaqiyatli ishga tushirildi.")
    except Exception as e:
        logger.error(f"Bazani yaratishda xatolik: {e}")

def track_user(user_id: int, username: str, full_name: str):
    try:
        with sqlite3.connect(DB_FILE, timeout=30.0) as conn:
            cursor = conn.cursor()
            today_str = date.today().strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, full_name, joined_date)
                VALUES (?, ?, ?, ?)
            """, (user_id, username or "", full_name or "", today_str))
            conn.commit()
    except Exception as e:
        logger.error(f"Bazaga foydalanuvchi qo'shishda xatolik: {e}")

def get_total_users_count() -> int:
    try:
        with sqlite3.connect(DB_FILE, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            res = cursor.fetchone()
            return res[0] if res else 0
    except Exception as e:
        logger.error(f"Statistikaning olishda xatolik: {e}")
        return 0

# ==============================================================================
# MIDDLEWARE
# ==============================================================================
class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.6):
        super().__init__()
        self.limit = limit
        self.user_timestamps: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            now = asyncio.get_running_loop().time()
            last_time = self.user_timestamps.get(user_id, 0.0)
            if now - last_time < self.limit:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("⚠️ Iltimos, biroz shoshmasdan turing!", show_alert=False)
                    except TelegramAPIError:
                        pass
                return
            self.user_timestamps[user_id] = now

        return await handler(event, data)

# ==============================================================================
# STATES
# ==============================================================================
class UserStates(StatesGroup):
    waiting_for_birthdate = State()

# ==============================================================================
# SUBSCRIPTION & KEYBOARDS
# ==============================================================================
async def check_channel_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in [
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER
        ]
    except Exception as e:
        logger.warning(f"Obunani tekshirishda xatolik ({user_id}): {e}")
        return False

def get_sub_keyboard() -> InlineKeyboardMarkup:
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalimizga obuna bo'lish", url=channel_url)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")]
    ])

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📅 Yoshni hisoblash")],
        [KeyboardButton(text="ℹ️ Bot haqida"), KeyboardButton(text="👨‍💻 Dasturchi")]
    ]
    if user_id == DEVELOPER_ID:
        buttons.append([KeyboardButton(text="📊 Statistika")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ==============================================================================
# CALCULATIONS
# ==============================================================================
WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

ZODIAC_SIGNS = [
    (1, 20, "Qovg'a ♒ (Aquarius)"), (2, 19, "Baliq ♓ (Pisces)"), (3, 21, "Qo'y ♈ (Aries)"),
    (4, 20, "Buqa ♉ (Taurus)"), (5, 21, "Egizaklar ♊ (Gemini)"), (6, 21, "Qisqichbaqa ♋ (Cancer)"),
    (7, 23, "Arslon ♌ (Leo)"), (8, 23, "Parizod ♍ (Virgo)"), (9, 23, "Tarozi ♎ (Libra)"),
    (10, 23, "Chayon ♏ (Scorpio)"), (11, 22, "O'qotar ♐ (Sagittarius)"), (12, 22, "Echki ♑ (Capricorn)")
]

MUCHAL_ANIMALS = [
    "Sichqon 🐭", "Sigir 🐮", "Yo'lbars 🐯", "Quyon 🐰", "Ajdaho 🐲", "Ilon 🐍",
    "Ot 🐴", "Qo'y 🐑", "Maymun 🐵", "Tovuq 🐔", "It 🐶", "To'ng'iz 🐗"
]

def get_zodiac(day: int, month: int) -> str:
    if (month == 1 and day <= 19) or (month == 12 and day >= 22):
        return "Echki ♑ (Capricorn)"
    for m, d, name in ZODIAC_SIGNS:
        if month == m and day < d:
            prev_m = 12 if m == 1 else m - 1
            for pm, pd, pname in ZODIAC_SIGNS:
                if pm == prev_m:
                    return pname
        elif month == m and day >= d:
            return name
    return "Noma'lum"

def get_muchal(year: int) -> str:
    return MUCHAL_ANIMALS[(year - 1900) % 12]

def calculate_age_stats(birth_date: date) -> Dict[str, Any]:
    today = date.today()
    
    # Aniq yosh, oy va kunlar
    diff = relativedelta(today, birth_date)
    years = diff.years
    months = diff.months
    days = diff.days

    total_days = (today - birth_date).days
    total_weeks = total_days // 7
    total_months = years * 12 + months

    # Keyingi tug'ilgan kun
    try:
        next_bday = date(today.year, birth_date.month, birth_date.day)
    except ValueError:
        next_bday = date(today.year, 2, 28)

    if next_bday < today:
        try:
            next_bday = date(today.year + 1, birth_date.month, birth_date.day)
        except ValueError:
            next_bday = date(today.year + 1, 2, 28)

    days_to_next_bday = (next_bday - today).days

    return {
        "birth_date_str": birth_date.strftime("%d.%m.%Y"),
        "years": years,
        "months": months,
        "days": days,
        "total_days": total_days,
        "total_weeks": total_weeks,
        "total_months": total_months,
        "days_to_next_bday": days_to_next_bday,
        "weekday": WEEKDAYS_UZ[birth_date.weekday()],
        "zodiac": get_zodiac(birth_date.day, birth_date.month),
        "muchal": get_muchal(birth_date.year),
    }

# ==============================================================================
# RASM GENERATORI (Instagram Story Format 1080x1920)
# ==============================================================================
def create_story_image(user_display_name: str, stats: Dict[str, Any]) -> io.BytesIO:
    width, height = 1080, 1920
    
    base = Image.new("RGBA", (width, height), (245, 240, 232, 255))
    draw = ImageDraw.Draw(base, "RGBA")

    for line_y in range(280, height - 150, 60):
        draw.line([(80, line_y), (width - 80, line_y)], fill=(225, 215, 200, 150), width=2)

    draw.rectangle([50, 50, width - 50, height - 50], outline=(60, 45, 35, 255), width=5)
    draw.rectangle([65, 65, width - 65, height - 65], outline=(140, 115, 95, 255), width=2)

    def get_font(size: int):
        for font_name in ["arial.ttf", "DejaVuSans.ttf", "times.ttf"]:
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    font_title = get_font(42)
    font_card_title = get_font(26)
    font_card_val = get_font(32)
    font_footer = get_font(24)

    sub_font_size = 30
    max_text_width = width - 240
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    
    sub_text = f"Foydalanuvchi: {user_display_name}"
    while sub_font_size > 14:
        font_sub = get_font(sub_font_size)
        bbox = temp_draw.textbbox((0, 0), sub_text, font=font_sub)
        if (bbox[2] - bbox[0]) <= max_text_width:
            break
        sub_font_size -= 2

    header_box = [80, 80, width - 80, 240]
    draw.rounded_rectangle(header_box, radius=25, fill=(50, 38, 28, 240), outline=(212, 175, 55, 255), width=3)

    draw.text((120, 130), f"✨ {BOT_NAME} Statistikasi", font=font_title, fill=(255, 255, 255, 255), anchor="lm")
    draw.text((120, 185), sub_text, font=font_sub, fill=(235, 205, 120, 255), anchor="lm")

    cards = [
        ("📅  Tug'ilgan sana", stats['birth_date_str']),
        ("⏳  Hozirgi yosh", f"{stats['years']} yosh, {stats['months']} oy, {stats['days']} kun"),
        ("🗓  Umringiz kunlari", f"{stats['total_days']:,} kun".replace(",", " ")),
        ("📊  O'tgan haftalar", f"{stats['total_weeks']:,} hafta".replace(",", " ")),
        ("🌙  Yashalgan oylar", f"{stats['total_months']:,} oy".replace(",", " ")),
        ("🎂  Keyingi tug'ilgan kun", f"{stats['days_to_next_bday']} kun qoldi"),
        ("📆  Tug'ilgan hafta kuni", stats['weekday']),
        ("✨  Burj (Zodiak)", stats['zodiac']),
        ("🐉  Muchal yili", stats['muchal'])
    ]

    y_pos = 280
    card_h = 130

    for label, val in cards:
        rect = [80, y_pos, width - 80, y_pos + card_h]
        draw.rounded_rectangle(rect, radius=18, fill=(255, 252, 248, 250), outline=(160, 135, 110, 200), width=2)
        draw.rounded_rectangle([80, y_pos, 105, y_pos + card_h], radius=10, fill=(195, 140, 45, 255))

        draw.text((135, y_pos + 38), label, font=font_card_title, fill=(100, 75, 55, 255), anchor="lm")
        draw.text((135, y_pos + 90), str(val), font=font_card_val, fill=(35, 25, 18, 255), anchor="lm")
        y_pos += card_h + 10

    draw.line([(120, height - 110), (width - 120, height - 110)], fill=(140, 115, 95, 180), width=2)
    draw.text((width // 2, height - 65), f"JavoAgeBot | Dasturchi: {DEVELOPER}", font=font_footer, fill=(80, 60, 45, 255), anchor="mm")

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================================================================
# ROUTER & HANDLERS
# ==============================================================================
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    user = message.from_user
    track_user(user.id, user.username, user.full_name)

    is_subbed = await check_channel_subscription(bot, user.id)
    if not is_subbed:
        await message.answer(
            f"Assalomu alaykum, <b>{user.full_name}</b>!\n\n"
            f"Botdan foydalanish uchun rasmiy kanalimizga obuna bo'ling:",
            reply_markup=get_sub_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    await message.answer(
        f"Assalomu alaykum, <b>{user.full_name}</b>!\n\n"
        f"<b>{BOT_NAME}</b> boti orqali yoshingiz haqidagi barcha qiziqarli va aniq ma'lumotlarni bilib olishingiz mumkin.\n\n"
        f"Hisoblashni boshlash uchun pastdagi <b>📅 Yoshni hisoblash</b> tugmasini bosing.",
        reply_markup=get_main_keyboard(user.id),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    is_subbed = await check_channel_subscription(bot, user_id)
    if is_subbed:
        await call.message.delete()
        await call.message.answer(
            "✅ Obuna tasdiqlandi! Menyudan kerakli bo'limni tanlang:",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        await call.answer("⚠️ Hali kanalga obuna bo'lmadingiz. Iltimos obuna bo'ling!", show_alert=True)

@router.message(F.text == "📅 Yoshni hisoblash")
async def process_calc_btn(message: Message, bot: Bot, state: FSMContext):
    if not await check_channel_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Davom etish uchun kanalimizga obuna bo'ling:", reply_markup=get_sub_keyboard())
        return

    await state.set_state(UserStates.waiting_for_birthdate)
    await message.answer(
        "Iltimos, tug'ilgan sanangizni <b>DD.MM.YYYY</b> formatida kiriting.\n\n"
        "<i>Masalan: 15.08.2000</i>",
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "ℹ️ Bot haqida")
async def cmd_about(message: Message):
    about_text = (
        f"<b>🤖 {BOT_NAME} boti haqida:</b>\n\n"
        f"Ushbu bot sizning tug'ilgan sanangiz asosida yoshingiz, yashagan kunlaringiz, "
        f"haftalaringiz, burjingiz va muchalingizni aniq hisoblab beradi hamda chiroyli "
        f"Instagram Story rasmini tayyorlaydi.\n\n"
        f"📢 Rasmiy kanal: {REQUIRED_CHANNEL}\n"
        f"📸 Instagram: {INSTAGRAM_CONTACT}"
    )
    await message.answer(about_text, parse_mode=ParseMode.HTML)

@router.message(F.text == "👨‍💻 Dasturchi")
async def cmd_developer(message: Message):
    dev_text = (
        f"<b>👨‍💻 Dasturchi:</b> {DEVELOPER}\n"
        f"<b>📸 Instagram:</b> <a href='{INSTAGRAM_URL}'>{INSTAGRAM_CONTACT}</a>\n"
        f"<b>📢 Telegram kanal:</b> {REQUIRED_CHANNEL}"
    )
    await message.answer(dev_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@router.message(F.text == "📊 Statistika")
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != DEVELOPER_ID:
        return
    count = get_total_users_count()
    await message.answer(f"📊 <b>Bot foydalanuvchilari soni:</b> {count} ta", parse_mode=ParseMode.HTML)

@router.message(UserStates.waiting_for_birthdate)
async def process_birthdate_input(message: Message, state: FSMContext):
    date_text = message.text.strip()
    
    try:
        birth_date = datetime.strptime(date_text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "❌ <b>Noto'g'ri sana formati yoki mavjud bo'lmagan sana!</b>\n\n"
            "Iltimos, sanani <b>DD.MM.YYYY</b> formatida qayta kiriting.\n"
            "<i>Masalan: 05.12.1998</i>",
            parse_mode=ParseMode.HTML
        )
        return

    today = date.today()
    if birth_date > today:
        await message.answer("❌ Tug'ilgan sana kelajakdagi sana bo'lishi mumkin emas. Qayta kiriting:")
        return

    if birth_date.year < 1900:
        await message.answer("❌ Yil 1900-yildan kichik bo'lmasligi kerak. Qayta kiriting:")
        return

    await state.clear()
    
    wait_msg = await message.answer("🔄 Ma'lumotlar hisoblanmoqda va rasm tayyorlanmoqda...")

    stats = calculate_age_stats(birth_date)
    user_display = message.from_user.full_name

    # Rasm tayyorlash
    loop = asyncio.get_running_loop()
    buf = await loop.run_in_executor(None, create_story_image, user_display, stats)
    
    photo = BufferedInputFile(buf.getvalue(), filename="javoage_story.png")

    caption = (
        f"✨ <b>{user_display} ning yosh statistikasi:</b>\n\n"
        f"📅 <b>Tug'ilgan sana:</b> {stats['birth_date_str']}\n"
        f"⏳ <b>Yoshi:</b> {stats['years']} yosh, {stats['months']} oy, {stats['days']} kun\n"
        f"🗓 <b>Jami yashalgan kunlar:</b> {stats['total_days']:,}\n".replace(",", " ") +
        f"📊 <b>Jami haftalar:</b> {stats['total_weeks']:,}\n".replace(",", " ") +
        f"🌙 <b>Jami oylar:</b> {stats['total_months']:,}\n".replace(",", " ") +
        f"🎂 <b>Keyingi tug'ilgan kungacha:</b> {stats['days_to_next_bday']} kun qoldi\n"
        f"📆 <b>Tug'ilgan kuni:</b> {stats['weekday']}\n"
        f"✨ <b>Burji:</b> {stats['zodiac']}\n"
        f"🐉 <b>Muchali:</b> {stats['muchal']}\n\n"
        f"🤖 Bot: {BOT_USERNAME}"
    )

    try:
        await wait_msg.delete()
    except Exception:
        pass

    await message.answer_photo(photo=photo, caption=caption, parse_mode=ParseMode.HTML)

# Xatoliklarni ushlash
@router.error()
async def error_handler(event: TelegramObject):
    logger.error(f"Xatolik yuz berdi: {event}")

# ==============================================================================
# MAIN FUNCTION
# ==============================================================================
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env fayl yoki Environment Variable'ni tekshiring.")
        return

    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware ulash
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())

    # Router ulash
    dp.include_router(router)

    logger.info("Bot muvaffaqiyatli ishga tushirildi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
