import os
import io
import logging
import asyncio
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Callable

from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile, TelegramObject, SwitchInlineQueryChosenChat
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

from PIL import Image, ImageDraw, ImageFont

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
DEVELOPER = "@XushboqovJavohir"
INSTAGRAM_CONTACT = "@xuushboqov"
TELEGRAM_CONTACT = "@XushboqovJavohir"

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
                        await event.answer("⚠️ Iltimos, biroz shoshmasdan turing!", show_alert=False)
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
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logger.warning(f"Obunani tekshirishda xatolik {user_id}: {e}")
        return True

def get_sub_keyboard() -> InlineKeyboardMarkup:
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalimizga obuna bo'lish", url=channel_url)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")]
    ])

# ==============================================================================
# CALCULATIONS
# ==============================================================================
WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

ZODIAC_SIGNS = [
    (1, 20, "Qovg'a ♒ (Aquarius)"), (2, 19, "Baliq ♓ (Pisces)"), (3, 21, "Qo'y ♈ (Aries)"),
    (4, 20, "Buqa ♉ (Taurus)"), (5, 21, "Ezgizaklar ♊ (Gemini)"), (6, 21, "Qisqichbaqa ♋ (Cancer)"),
    (7, 23, "Arslon ♌ (Leo)"), (8, 23, "Parizod ♍ (Virgo)"), (9, 23, "Tarozi ♎ (Libra)"),
    (10, 23, "Chayon ♏ (Scorpio)"), (11, 22, "O'qotar ♐ (Sagittarius)"), (12, 22, "Echki ♑ (Capricorn)")
]

MUCHAL_ANIMALS = ["Sichqon 🐭", "Sigir 🐮", "Yo'lbars 🐯", "Quyon 🐰", "Ajdaho 🐲", "Ilan 🐍", "Ot 🐴", "Qo'y 🐑", "Maymun 🐵", "Tovuq 🐔", "It 🐶", "To'ng'iz 🐗"]

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
        prev_month = (today.month - 1) if today.month > 1 else 12
        prev_year = today.year if today.month > 1 else today.year - 1
        days_in_prev_month = 31 if prev_month == 12 else (date(prev_year, prev_month + 1, 1) - date(prev_year, prev_month, 1)).days
        days += days_in_prev_month

    if months < 0:
        years -= 1
        months += 12

    total_days = (today - birth_date).days
    total_weeks = total_days // 7
    total_months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)

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
# RETRO QOG'OZ FONLI RASM GENERATORI
# ==============================================================================
def create_story_image(user_fullname: str, stats: Dict[str, Any]) -> io.BytesIO:
    width, height = 1080, 1920
    
    base = Image.new("RGBA", (width, height), (235, 218, 185, 255))
    draw = ImageDraw.Draw(base, "RGBA")

    for line_y in range(250, height - 120, 50):
        draw.line([(80, line_y), (width - 80, line_y)], fill=(210, 190, 155, 120), width=2)

    draw.rectangle([40, 40, width - 40, height - 40], outline=(40, 30, 20, 255), width=6)
    draw.rectangle([55, 55, width - 55, height - 55], outline=(90, 70, 50, 255), width=2)

    def get_font(size: int):
        for font_name in ["arial.ttf", "DejaVuSans.ttf", "times.ttf"]:
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    font_title = get_font(40)
    font_sub = get_font(32)
    font_card_title = get_font(25)
    font_card_val = get_font(30)
    font_footer = get_font(24)

    header_box = [80, 80, width - 80, 230]
    draw.rounded_rectangle(header_box, radius=20, fill=(45, 35, 25, 230), outline=(212, 175, 55, 255), width=3)

    draw.text((120, 125), "💬 JavoAgeBot", font=font_title, fill=(255, 255, 255, 255), anchor="lm")
    draw.text((120, 180), f"Foydalanuvchi ismi: {user_fullname}", font=font_sub, fill=(235, 205, 120, 255), anchor="lm")

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

    y_pos = 265
    card_h = 135

    for label, val in cards:
        rect = [80, y_pos, width - 80, y_pos + card_h]
        draw.rounded_rectangle(rect, radius=15, fill=(248, 240, 225, 240), outline=(120, 95, 70, 220), width=2)
        draw.rounded_rectangle([80, y_pos, 100, y_pos + card_h], radius=8, fill=(180, 130, 40, 255))

        draw.text((130, y_pos + 38), label, font=font_card_title, fill=(90, 70, 50, 255), anchor="lm")
        draw.text((130, y_pos + 92), str(val), font=font_card_val, fill=(35, 25, 15, 255), anchor="lm")
        y_pos += card_h + 12

    draw.line([(120, height - 75), (width - 120, height - 75)], fill=(120, 95, 70, 180), width=2)
    draw.text((width // 2, height - 42), f"🤖 @{BOT_NAME} | Dasturchi: {DEVELOPER}", font=font_footer, fill=(70, 50, 30, 255), anchor="mm")

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================================================================
# ROUTERS & HANDLERS
# ==============================================================================
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    
    if not await check_channel_subscription(bot, message.from_user.id):
        text = (
            f"Assalomu alaykum, qadrli <b>{message.from_user.full_name}</b>! 😊\n\n"
            f"Botimizdan to'liq foydalanish uchun kanalimizga obuna bo'lishingizni so'raymiz:\n"
            f"👉 <b>{REQUIRED_CHANNEL}</b>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_sub_keyboard())
        return

    text = (
        f"Assalomu alaykum, xush kelibsiz <b>{message.from_user.full_name}</b>! ✨\n\n"
        f"<b>{BOT_NAME}</b> yordamida yoshingiz va tug'ilgan kuningizga oid barcha qiziqarli ma'lumotlarni bilib oling.\n\n"
        f"📌 <b>Iltimos, tug'ilgan sanangizni yuboring:</b>\n"
        f"<i>(Masalan: <code>05.02.2002</code> yoki <code>31.01.1995</code>)</i>"
    )
    await message.answer(text, parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_birthdate)

@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("✅ Rahmat! Obunangiz tasdiqlandi.", show_alert=True)
        try: await callback.message.delete()
        except TelegramBadRequest: pass
        
        text = (
            f"🎉 <b>Ajoyib! Obuna muvaffaqiyatli tasdiqlandi.</b>\n\n"
            f"📌 Endi o'zingizning tug'ilgan sanangizni yuboring:\n"
            f"<i>(Masalan: <code>05.02.2002</code>)</i>"
        )
        await callback.message.answer(text, parse_mode="HTML")
        await state.set_state(UserStates.waiting_for_birthdate)
    else:
        await callback.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

@router.message(F.text & ~F.text.startswith("/"))
async def process_birthdate(message: Message, state: FSMContext, bot: Bot):
    if not await check_channel_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun avval kanalga obuna bo'ling!", reply_markup=get_sub_keyboard())
        return

    raw_text = message.text.strip() if message.text else ""
    parsed_date = None

    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed_date = datetime.strptime(raw_text, fmt).date()
            break
        except ValueError:
            pass

    if not parsed_date:
        await message.answer("❌ <b>Sana formati noto'g'ri!</b>\nIltimos, quyidagicha kiriting (Masalan: <code>05.02.2002</code>):", parse_mode="HTML")
        return

    if parsed_date > date.today() or parsed_date.year < 1900:
        await message.answer("❌ <b>Iltimos, haqiqiy tug'ilgan sanangizni kiriting!</b>", parse_mode="HTML")
        return

    stats = calculate_age_stats(parsed_date)
    await state.update_data(stats=stats, user_fullname=message.from_user.full_name)

    msg_text = (
        f"🎉 <b>Hurmatli {message.from_user.full_name}, mana sizning yosh statistikangiz:</b>\n\n"
        f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name}\n"
        f"📅 <b>Tug'ilgan kuningiz:</b> <code>{stats['birth_date_str']}</code>\n"
        f"⏳ <b>Ayni vaqtdagi yoshingiz:</b> <b>{stats['years']} yosh, {stats['months']} oy, {stats['days']} kun</b>\n\n"
        f"✨ <b>Umringiz davomida:</b>\n"
        f" ├ 🗓 <b>{stats['total_days']:,} kun</b>\n"
        f" ├ 📊 <b>{stats['total_weeks']:,} hafta</b>\n"
        f" └ 🌙 <b>{stats['total_months']:,} oy</b>\n\n"
        f"🎂 <b>Navbatdagi tug'ilgan kuningizga:</b> <code>{stats['days_to_next_bday']} kun qoldi</code>\n\n"
        f"🔮 <b>Astrologik ma'lumotlar:</b>\n"
        f" ├ 📆 <b>Hafta kuni:</b> {stats['weekday']}\n"
        f" ├ ✨ <b>Burj:</b> {stats['zodiac']}\n"
        f" └ 🐉 <b>Muchal:</b> {stats['muchal']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    share_text = (
        f"Salom! Men yoshim va tug'ilgan kunim statistikagizni hisobladim:\n"
        f"📅 Tug'ilgan kun: {stats['birth_date_str']}\n"
        f"⏳ Yoshim: {stats['years']} yosh\n"
        f"🤖 Sen ham o'z yoshingni bilish uchun ushbu botga kirmaysanmi? 👇"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Ma'lumotni rasm shaklida olish", callback_data="get_story_img")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida ma'lumot", callback_data="bot_info")],
        [InlineKeyboardButton(
            text="📤 Do'stlarga ulashish", 
            switch_inline_query=share_text
        )]
    ])

    await message.answer(msg_text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "get_story_img")
async def cb_get_story_img(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    await callback.answer("🎨 Retro dizaynli rasm tayyorlanmoqda...")
    data = await state.get_data()
    stats = data.get("stats")
    fullname = data.get("user_fullname", callback.from_user.full_name)

    if not stats:
        await callback.message.answer("❌ Ma'lumot topilmadi, sanani qaytadan yuboring.")
        return

    loop = asyncio.get_running_loop()
    img_buf = await loop.run_in_executor(None, create_story_image, fullname, stats)
    input_file = BufferedInputFile(img_buf.read(), filename="retro_story.png")

    await callback.message.answer_photo(
        photo=input_file,
        caption=f"📸 <b>{fullname}</b> uchun tayyorlangan dizaynli rasm!\n\n🤖 <b>{BOT_NAME}</b> | Dasturchi: {DEVELOPER}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "bot_info")
async def cb_bot_info(callback: CallbackQuery, bot: Bot):
    if not await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    await callback.answer("ℹ️ Bot haqida ma'lumot ochildi")
    
    info_text = (
        f"🤖 <b>Bot haqida ma'lumot:</b>\n\n"
        f"<b>{BOT_NAME}</b> — foydalanuvchining tug'ilgan sanasiga ko'ra uning aniq yoshini yillar, oylar, kunlar, haftalar va oylar kesimida hisoblab beruvchi hamda qiziqarli astrologik ma'lumotlar (burj, muchal, hafta kuni) taqdim etuvchi aqlli yordamchi bot.\n\n"
        f"👨‍💻 <b>Bot yaratuvchisi (Dasturchi):</b> {DEVELOPER}\n\n"
        f"📢 <b>Reklama va hamkorlik uchun murojaat:</b>\n"
        f" ├ 📸 Instagram: <b>{INSTAGRAM_CONTACT}</b>\n"
        f" └ 📱 Telegram: <b>{TELEGRAM_CONTACT}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.answer(info_text, parse_mode="HTML")

@router.errors()
async def global_error_handler(event: Any, exception: Exception):
    logger.error(f"Global Xatolik: {exception}")
    return True

# ==============================================================================
# MAIN APP
# ==============================================================================
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi!")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    middleware = RateLimitMiddleware()
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(router)
    logger.info("JavoAgeBot muvaffaqiyatli ishga tushdi!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
