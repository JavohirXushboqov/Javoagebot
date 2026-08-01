import os
import io
import logging
import asyncio
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Callable

from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile, TelegramObject
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
BOT_USERNAME = "@JavoAgeBot"
DEVELOPER = "@XushboqovJavohir"
INSTAGRAM_CONTACT = "@xuushboqov"
INSTAGRAM_URL = "https://instagram.com/xuushboqov"
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
# CHIRSVOYLI VA ZAMONAVIY RASM GENERATORI
# ==============================================================================
def create_story_image(user_fullname: str, stats: Dict[str, Any]) -> io.BytesIO:
    width, height = 1080, 1920
    
    # Elegant va yumshoq fon rangi (Qaymoqrang / Krem)
    base = Image.new("RGBA", (width, height), (245, 240, 232, 255))
    draw = ImageDraw.Draw(base, "RGBA")

    # Orqa fondagi nafis bezak chiziqlari
    for line_y in range(280, height - 150, 60):
        draw.line([(80, line_y), (width - 80, line_y)], fill=(225, 215, 200, 150), width=2)

    # Chiroyli ramka
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
    font_sub = get_font(30)
    font_card_title = get_font(26)
    font_card_val = get_font(32)
    font_footer = get_font(24)

    # Header qismi
    header_box = [80, 80, width - 80, 240]
    draw.rounded_rectangle(header_box, radius=25, fill=(50, 38, 28, 240), outline=(212, 175, 55, 255), width=3)

    draw.text((120, 130), f"✨ {BOT_NAME} Statistikasi", font=font_title, fill=(255, 255, 255, 255), anchor="lm")
    draw.text((120, 185), f"Qadrli foydalanuvchi: {user_fullname}", font=font_sub, fill=(235, 205, 120, 255), anchor="lm")

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

    draw.line([(120, height - 85), (width - 120, height - 85)], fill=(140, 115, 95, 180), width=2)
    draw.text((width // 2, height - 50), f"🤖 {BOT_NAME} | Mehribon Dasturchi: {DEVELOPER}", font=font_footer, fill=(80, 60, 45, 255), anchor="mm")

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
            f"Assalomu alaykum va rohmatulloh, hurmatli <b>{message.from_user.full_name}</b>! 😊\n\n"
            f"Botimiz imkoniyatlaridan to'liq bahramand bo'lishingiz uchun iltimos, quyidagi kanalimizga obuna bo'lib qo'ying:\n"
            f"👉 <b>{REQUIRED_CHANNEL}</b>\n\n"
            f"Obuna bo'lganingizdan so'ng, pastdagi tugmani bosing:"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_sub_keyboard())
        return

    text = (
        f"Assalomu alaykum, qadrli va hurmatli <b>{message.from_user.full_name}</b>! ✨\n\n"
        f"<b>{BOT_NAME}</b> olamiga xush kelibsiz! Sizga yoshingiz va tug'ilgan kuningizga oid eng qiziqarli ma'lumotlarni sevgi bilan taqdim etishdan mamnunman. 🥰\n\n"
        f"📌 <b>Marhamat qilib, tug'ilgan sanangizni yuboring:</b>\n"
        f"<i>(Namuna: <code>17.05.2010</code> yoki <code>05.02.2002</code>)</i>"
    )
    await message.answer(text, parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_birthdate)

@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("✅ Rahmat, obunangiz muvaffaqiyatli tasdiqlandi!", show_alert=True)
        try: await callback.message.delete()
        except TelegramBadRequest: pass
        
        text = (
            f"🎉 <b>Juda ajoyib! Tabriklayman, obunangiz tasdiqlandi.</b>\n\n"
            f"📌 Endi o'zingizning qadrli tug'ilgan sanangizni kiriting:\n"
            f"<i>(Namuna: <code>17.05.2010</code>)</i>"
        )
        await callback.message.answer(text, parse_mode="HTML")
        await state.set_state(UserStates.waiting_for_birthdate)
    else:
        await callback.answer("❌ Kechirasiz, siz hali kanalimizga obuna bo'lmadingiz.", show_alert=True)

@router.message(F.text & ~F.text.startswith("/"))
async def process_birthdate(message: Message, state: FSMContext, bot: Bot):
    if not await check_channel_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Iltimos, avval kanalimizga obuna bo'ling!", reply_markup=get_sub_keyboard())
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
        await message.answer("❌ <b>Kechirasiz, sana formati biroz xato yozildi.</b>\nIltimos, ushbu ko'rinishda yuboring (Namuna: <code>17.05.2010</code>):", parse_mode="HTML")
        return

    if parsed_date > date.today() or parsed_date.year < 1900:
        await message.answer("❌ <b>Iltimos, o'zingizning haqiqiy va to'g'ri tug'ilgan sanangizni kiriting!</b>", parse_mode="HTML")
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
        f"Salom! Men o'z yoshim va tug'ilgan kunim statistikasini hisobladim:\n"
        f"📅 Tug'ilgan kun: {stats['birth_date_str']}\n"
        f"⏳ Yoshim: {stats['years']} yosh\n\n"
        f"🤖 Sen ham o'z yoshingni bilish uchun ushbu botga kirmaysanmi? 👇\n"
        f"{BOT_USERNAME}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Ma'lumotni rasm shaklida olish", callback_data="get_story_img")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida ma'lumot", callback_data="bot_info")],
        [InlineKeyboardButton(text="📤 Do'stlarga ulashish", switch_inline_query=share_text)]
    ])

    await message.answer(msg_text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "get_story_img")
async def cb_get_story_img(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Iltimos, avval kanalimizga obuna bo'ling!", show_alert=True)
        return

    await callback.answer("🎨 Siz uchun eng chiroyli dizaynli rasm tayyorlanmoqda...")
    data = await state.get_data()
    stats = data.get("stats")
    fullname = data.get("user_fullname", callback.from_user.full_name)

    if not stats:
        await callback.message.answer("❌ Kechirasiz, ma'lumot topilmadi. Sanani qaytadan yuborishingizni so'rayman.")
        return

    loop = asyncio.get_running_loop()
    img_buf = await loop.run_in_executor(None, create_story_image, fullname, stats)
    input_file = BufferedInputFile(img_buf.read(), filename="chiroyli_statistika.png")

    await callback.message.answer_photo(
        photo=input_file,
        caption=f"📸 <b>{fullname}</b> uchun maxsus va chiroyli tayyorlangan rasm!\n\n🤖 <b>{BOT_NAME}</b> | Mehribon Dasturchi: {DEVELOPER}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "bot_info")
async def cb_bot_info(callback: CallbackQuery, bot: Bot):
    if not await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Iltimos, avval kanalimizga obuna bo'ling!", show_alert=True)
        return

    await callback.answer("ℹ️ Bot haqida ma'lumot ochildi")
    
    info_text = (
        f"🤖 <b>Bot haqida samimiy ma'lumot:</b>\n\n"
        f"<b>{BOT_NAME}</b> — aziz foydalanuvchilarimizga o'zlarining tug'ilgan sanalariga ko'ra aniq yoshlarini yillar, oylar, kunlar va haftalar kesimida sevgi bilan hisoblab beruvchi, shuningdek qiziqarli astrologik ma'lumotlarni ulashuvchi qulay yordamchi bot.\n\n"
        f"👨‍💻 <b>Botning zahmatkash yaratuvchisi:</b> {DEVELOPER}\n\n"
        f"📢 <b>Reklama va hamkorlik uchun doimo ochiqmiz:</b>\n"
        f" ├ 📸 Instagram: <a href='{INSTAGRAM_URL}'><b>{INSTAGRAM_CONTACT}</b></a>\n"
        f" └ 📱 Telegram: <b>{TELEGRAM_CONTACT}</b>\n\n"
        f"<i>Bizni tanlaganingiz uchun sizga o'z minnatdorchiligimizni bildiramiz! ✨</i>"
    )
    await callback.message.answer(info_text, parse_mode="HTML", disable_web_page_preview=True)

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
    logger.info("JavoAgeBot muvaffaqiyatli ishga tushdi va xizmatingizga shay!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
