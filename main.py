import os
import io
import logging
import asyncio
import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, Any, Callable

from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile, TelegramObject
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from aiogram.types.error_event import ErrorEvent

from PIL import Image, ImageDraw, ImageFont

from config import DEVELOPER_ID

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
TELEGRAM_CONTACT = "@XushboqovJavohir"

DB_FILE = "bot_stats.db"

# ==============================================================================
# DATABASE INITIALIZATION (Thread-safe & Safe connection handling)
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
            """, (user_id, username, full_name, today_str))
            conn.commit()
    except Exception as e:
        logger.error(f"Bazaga foydalanuvchi qo'shishda xatolik: {e}")

# ==============================================================================
# MIDDLEWARE
# ==============================================================================
class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.5):
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
                        await event.answer("⚠️ Iltimos, biroz shoshmasdan turing azizim!", show_alert=False)
                    except TelegramAPIError:
                        pass
                return
            self.user_timestamps[user_id] = now

        return await handler(event, data)

class UserStates(StatesGroup):
    waiting_for_birthdate = State()

# ==============================================================================
# CHANNEL SUBSCRIPTION CHECKER
# ==============================================================================
async def check_channel_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        from aiogram.enums import ChatMemberStatus
        return member.status in [
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER
        ]
    except Exception as e:
        logger.warning(f"Obunani tekshirishda xatolik {user_id}: {e}")
        return False

def get_sub_keyboard() -> InlineKeyboardMarkup:
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalimizga obuna bo'lish", url=channel_url)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")]
    ])

# ==============================================================================
# CALCULATIONS (Mathematical precise age stats)
# ==============================================================================
WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

ZODIAC_SIGNS = [
    (1, 20, "Qovg'a ♒ (Aquarius)"), (2, 19, "Baliq ♓ (Pisces)"), (3, 21, "Qo'y ♈ (Aries)"),
    (4, 20, "Buqa ♉ (Taurus)"), (5, 21, "Egizaklar ♊ (Gemini)"), (6, 21, "Qisqichbaqa ♋ (Cancer)"),
    (7, 23, "Arslon ♌ (Leo)"), (8, 23, "Parizod ♍ (Virgo)"), (9, 23, "Tarozi ♎ (Libra)"),
    (10, 23, "Chayon ♏ (Scorpio)"), (11, 22, "O'qotar ♐ (Sagittarius)"), (12, 22, "Echki ♑ (Capricorn)")
]

MUCHAL_ANIMALS = ["Sichqon 🐭", "Sigir 🐮", "Yo'lbars 🐯", "Quyon 🐰", "Ajdaho 🐲", "Ilon 🐍", "Ot 🐴", "Qo'y 🐑", "Maymun 🐵", "Tovuq 🐔", "It 🐶", "To'ng'iz 🐗"]

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
    
    years = today.year - birth_date.year
    months = today.month - birth_date.month
    days = today.day - birth_date.day

    if days < 0:
        months -= 1
        prev_month_date = today.replace(day=1) - timedelta(days=1)
        days += prev_month_date.day

    if months < 0:
        years -= 1
        months += 12

    total_days = (today - birth_date).days
    total_weeks = total_days // 7
    total_months = years * 12 + months

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
# RASM GENERATORI (Enhanced text scaling and safe rendering)
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
    
    sub_text = f"Qadrli foydalanuvchi: {user_display_name}"
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
        ("📅  Tug'ilgan sanangiz", stats['birth_date_str']),
        ("⏳  Ayni vaqtdagi yoshingiz", f"{stats['years']} yosh, {stats['months']} oy, {stats['days']} kun"),
        ("🗓  Muborak umringiz kunlari", f"{stats['total_days']:,} kun".replace(",", " ")),
        ("📊  O'tgan mazmunli haftalar", f"{stats['total_weeks']:,} hafta".replace(",", " ")),
        ("🌙  Yashalgan go'zal oylar", f"{stats['total_months']:,} oy".replace(",", " ")),
        ("🎂  Keyingi tug'ilgan kuningizga", f"{stats['days_to_next_bday']} kun qoldi"),
        ("📆  Tug'ilgan hafta kuningiz", stats['weekday']),
        ("✨  Burjingiz (Zodiak)", stats['zodiac']),
        ("🐉  Muchal yilingiz", stats['muchal'])
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
    draw.text((width // 2, height - 65), f"JavoAgeBot | dasturchi: {DEVELOPER}", font=font_footer, fill=(80, 60, 45, 255), anchor="mm")

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf
