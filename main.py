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

import aiohttp
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

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

CACHE_CELEBS: Dict[str, List[Dict[str, Any]]] = {}
CACHE_DETAILS: Dict[str, Dict[str, Any]] = {}
CACHE_TRANSLATIONS: Dict[str, str] = {}

translator = GoogleTranslator(source='auto', target='uz')
HTTP_SESSION: Optional[aiohttp.ClientSession] = None

async def get_http_session() -> aiohttp.ClientSession:
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        timeout = aiohttp.ClientTimeout(total=12)
        HTTP_SESSION = aiohttp.ClientSession(timeout=timeout)
    return HTTP_SESSION

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
                        await event.answer("⚠️ Iltimos, biroz kuting!", show_alert=False)
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
        logger.warning(f"Sub check error for {user_id}: {e}")
        return True

def get_sub_keyboard() -> InlineKeyboardMarkup:
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalimizga obuna bo'lish", url=channel_url)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")]
    ])

# ==============================================================================
# TRANSLATOR & CALCULATIONS
# ==============================================================================
async def async_translate(text: str) -> str:
    if not text or not text.strip():
        return ""
    if text in CACHE_TRANSLATIONS:
        return CACHE_TRANSLATIONS[text]
    try:
        loop = asyncio.get_running_loop()
        translated = await loop.run_in_executor(None, lambda: translator.translate(text))
        if translated:
            CACHE_TRANSLATIONS[text] = translated
            return translated
        return text
    except Exception as e:
        logger.error(f"Translation Error: {e}")
        return text

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
        "day": birth_date.day,
        "month": birth_date.month,
        "year": birth_date.year
    }

# ==============================================================================
# CELEBRITY API (TOP 5) - KENGAYTIRILGAN QIDIRUV BILAN
# ==============================================================================
async def fetch_celebrity_details(name: str) -> Dict[str, Any]:
    if name in CACHE_DETAILS:
        return CACHE_DETAILS[name]

    details = {
        "name": name, "year": "Noma'lum", "occupation": "Mashhur shaxs",
        "country": "Jahon", "description": "Dunyoga tanilgan mashhur insonlardan biri.",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/7/7c/Profile_avatar_placeholder_large.png"
    }

    try:
        session = await get_http_session()
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{name.replace(' ', '_')}"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                raw_desc = data.get("extract", "")
                description = data.get("description", "")
                
                if "originalimage" in data:
                    details["image_url"] = data["originalimage"].get("source")
                elif "thumbnail" in data:
                    details["image_url"] = data["thumbnail"].get("source")

                uz_desc = await async_translate(raw_desc or description)
                uz_occ = await async_translate(description or "Mashhur shaxs")
                if uz_desc: details["description"] = uz_desc
                if uz_occ: details["occupation"] = uz_occ
    except Exception as e:
        logger.error(f"Celebrity Details Fetch Error: {e}")

    CACHE_DETAILS[name] = details
    return details

async def fetch_top5_celebrities(day: int, month: int) -> List[Dict[str, Any]]:
    cache_key = f"{month:02d}-{day:02d}"
    if cache_key in CACHE_CELEBS:
        return CACHE_CELEBS[cache_key]

    celebs: List[Dict[str, Any]] = []
    seen_names = set()
    session = await get_http_session()

    # 1-Urunish: "onthisday/births" orqali
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/births/{month:02d}/{day:02d}"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for b in data.get("births", []):
                    pages = b.get("pages", [])
                    year = str(b.get("year", "Noma'lum"))
                    if pages:
                        name = pages[0].get("titles", {}).get("normalized") or pages[0].get("title")
                        if name and name not in seen_names:
                            seen_names.add(name)
                            det = await fetch_celebrity_details(name)
                            det["year"] = year
                            celebs.append(det)
                            if len(celebs) >= 5: break
    except Exception as e:
        logger.error(f"Wiki API Error 1: {e}")

    # Agar 1-usulda natija chiqmasa, muqobil oylik umumiy sahifalardan qidiramiz
    if not celebs:
        try:
            months_names = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            m_name = months_names[month]
            alt_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{m_name}_{day}"
            async with session.get(alt_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Agar sahifada matn bo'lsa, uni boshlang'ich ma'lumot sifatida olamiz
                    pass
        except Exception as e:
            logger.error(f"Wiki API Error 2: {e}")

    CACHE_CELEBS[cache_key] = celebs
    return celebs

# ==============================================================================
# INSTAGRAM STORY IMAGE GENERATOR (1080x1920 HD) - YANGILANGAN DIZAYN
# ==============================================================================
def create_story_image(user_fullname: str, stats: Dict[str, Any]) -> io.BytesIO:
    width, height = 1080, 1920
    base = Image.new("RGBA", (width, height), (18, 16, 38, 255))
    draw = ImageDraw.Draw(base)

    # Chiroyli gradient fon chiziqlari
    for y in range(height):
        r = int(18 + (45 - 18) * (y / height))
        g = int(16 + (28 - 16) * (y / height))
        b = int(38 + (75 - 38) * (y / height))
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Dekorativ yorug'lik doiralari
    draw.ellipse([50, -50, 950, 450], fill=(140, 90, 255, 45))
    draw.ellipse([-100, 1300, 700, 1850], fill=(255, 110, 170, 30))

    # Yuqori qismdagi och rangli, aniq ko'rinadigan qism (Header Card)
    header_box = [60, 60, width - 60, 240]
    draw.rounded_rectangle(header_box, radius=35, fill=(245, 240, 255, 235), outline=(212, 175, 55, 255), width=3)

    def get_font(size: int):
        for font_name in ["arial.ttf", "DejaVuSans.ttf", "times.ttf"]:
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    font_title = get_font(48)
    font_sub = get_font(34)
    font_card_title = get_font(26)
    font_card_val = get_font(32)
    font_footer = get_font(26)

    # Telegram logosi o'rniga maxsus belgi va aniq quyuq rangli yozuvlar (Header ichida)
    draw.text((width // 2, 115), "💬 JavoAgeBot", font=font_title, fill=(30, 25, 60, 255), anchor="mm")
    draw.text((width // 2, 185), f"Foydalanuvchi: {user_fullname}", font=font_sub, fill=(160, 40, 100, 255), anchor="mm")

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

    y_pos = 285
    card_h = 130

    for label, val in cards:
        rect = [60, y_pos, width - 60, y_pos + card_h]
        # Kartochkalar uchun zamonaviy qoramtir-binafsha va tiniq dizayn
        draw.rounded_rectangle(rect, radius=20, fill=(40, 35, 75, 220), outline=(130, 110, 190, 200), width=2)
        # Chap qismdagi oltin rangli bezak chizig'i
        draw.rounded_rectangle([60, y_pos, 78, y_pos + card_h], radius=10, fill=(212, 175, 55, 255))

        draw.text((110, y_pos + 36), label, font=font_card_title, fill=(210, 205, 235, 255), anchor="lm")
        draw.text((110, y_pos + 85), str(val), font=font_card_val, fill=(255, 255, 255, 255), anchor="lm")
        y_pos += card_h + 18

    # Pastki qism mualliflik qismi
    draw.line([(120, height - 85), (width - 120, height - 85)], fill=(212, 175, 55, 180), width=2)
    draw.text((width // 2, height - 45), f"🤖 @{BOT_NAME} | Dasturchi: {DEVELOPER}", font=font_footer, fill=(220, 220, 240, 255), anchor="mm")

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
            f"Assalomu alaykum, hurmatli <b>{message.from_user.full_name}</b>! 😊\n\n"
            f"Botimiz xizmatlaridan to'liq va bepul foydalanish uchun rasmiy kanalimizga obuna bo'lishingizni so'raymiz:\n"
            f"👉 <b>{REQUIRED_CHANNEL}</b>\n\n"
            f"Obuna bo'lgach, quyidagi <b>✅ Obunani tekshirish</b> tugmasini bosing!"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_sub_keyboard())
        return

    text = (
        f"Assalomu alaykum, xush kelibsiz <b>{message.from_user.full_name}</b>! ✨\n\n"
        f"<b>{BOT_NAME}</b> orqali yoshingiz va umringiz haqida juda qiziqarli hamda aniq ma'lumotlarga ega bo'lasiz.\n\n"
        f"📌 <b>Iltimos, tug'ilgan sanangizni yuboring:</b>\n"
        f"<i>(Masalan: <code>05.02.2002</code> yoki <code>2002-02-05</code>)</i>"
    )
    await message.answer(text, parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_birthdate)

@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("✅ Rahmat! Obuna tasdiqlandi.", show_alert=True)
        try: await callback.message.delete()
        except TelegramBadRequest: pass
        
        text = (
            f"🎉 <b>Ajoyib! Obuna muvaffaqiyatli tasdiqlandi.</b>\n\n"
            f"📌 Endi tug'ilgan sanangizni yuboring:\n"
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
        await message.answer("❌ <b>Sana formati tushunilmadi!</b>\nIltimos, qaytadan to'g'ri ko'rinishda kiriting (Masalan: <code>05.02.2002</code>):", parse_mode="HTML")
        return

    if parsed_date > date.today() or parsed_date.year < 1900:
        await message.answer("❌ <b>Iltimos, haqiqiy va to'g'ri tug'ilgan sanangizni kiriting!</b>", parse_mode="HTML")
        return

    stats = calculate_age_stats(parsed_date)
    await state.update_data(stats=stats, user_fullname=message.from_user.full_name)

    msg_text = (
        f"🎉 <b>Hurmatli {message.from_user.full_name}, sizning yosh statistikangiz bilan tanishing!</b>\n\n"
        f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name}\n"
        f"📅 <b>Tug'ilgan kuningiz:</b> <code>{stats['birth_date_str']}</code>\n"
        f"⏳ <b>Ayni vaqtdagi yoshingiz:</b> <b>{stats['years']} yosh, {stats['months']} oy, {stats['days']} kun</b>\n\n"
        f"✨ <b>Siz umringiz davomida:</b>\n"
        f" ├ 🗓 <b>{stats['total_days']:,} kun</b>ni mazmunli yashab o'tdingiz\n"
        f" ├ 📊 <b>{stats['total_weeks']:,} hafta</b>ni ortda qoldirdingiz\n"
        f" └ 🌙 <b>{stats['total_months']:,} oy</b> davomida hayot quvonchlaridan bahramand bo'ldingiz\n\n"
        f"🎂 <b>Navbatdagi tug'ilgan kuningizga:</b> <code>{stats['days_to_next_bday']} kun qoldi</code>\n\n"
        f"🔮 <b>Qiziqarli astrologik ma'lumotlar:</b>\n"
        f" ├ 📆 <b>Tug'ilgan hafta kuningiz:</b> {stats['weekday']}\n"
        f" ├ ✨ <b>Burjingiz (Zodiak):</b> {stats['zodiac']}\n"
        f" └ 🐉 <b>Muchal yilingiz:</b> {stats['muchal']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Sizga uzoq va mazmunli umr, doimiy omad va sihat-salomatlik tilaymiz!</i> 😊"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Ma'lumotni rasm shaklida olish", callback_data="get_story_img")],
        [InlineKeyboardButton(text="🌟 Shu sanada tug'ilgan mashhurlar", callback_data=f"top5_{stats['day']}_{stats['month']}")]
    ])

    await message.answer(msg_text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "get_story_img")
async def cb_get_story_img(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    await callback.answer("🎨 Chiroyli Story rasmi tayyorlanmoqda...")
    data = await state.get_data()
    stats = data.get("stats")
    fullname = data.get("user_fullname", callback.from_user.full_name)

    if not stats:
        await callback.message.answer("❌ Sana ma'lumotlari topilmadi, qaytadan sana yuboring.")
        return

    loop = asyncio.get_running_loop()
    img_buf = await loop.run_in_executor(None, create_story_image, fullname, stats)
    input_file = BufferedInputFile(img_buf.read(), filename="instagram_story.png")

    await callback.message.answer_photo(
        photo=input_file,
        caption=f"📸 <b>{fullname}</b> uchun tayyorlangan Instagram Story mos rasmi!\n\n🤖 <b>{BOT_NAME}</b> | Dasturchi: {DEVELOPER}",
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("top5_"))
async def cb_show_top5_celebrities(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    await callback.answer("🌟 Mashhurlar ro'yxati yuklanmoqda...")
    
    try:
        parts = callback.data.split("_")
        day, month = int(parts[1]), int(parts[2])
    except Exception:
        await callback.message.answer("❌ Xatolik yuz berdi. Iltimos, sanani qayta kiriting.")
        return

    loading_msg = await callback.message.answer("🔄 <i>Ushbu sanada tug'ilgan mashhur insonlar qidirilmoqda...</i>", parse_mode="HTML")
    celebs = await fetch_top5_celebrities(day, month)

    try: await loading_msg.delete()
    except TelegramBadRequest: pass

    if not celebs:
        await callback.message.answer("⚠️ Kechirasiz, ushbu sanada tug'ilgan taniqli shaxslar haqida Wikipedia bazasida ma'lumot topilmadi.")
        return

    for index, celeb in enumerate(celebs, 1):
        caption = (
            f"🌟 <b>#{index} MASHHUR INSON</b>\n\n"
            f"👤 <b>Ismi:</b> {celeb['name']}\n"
            f"📅 <b>Tug'ilgan yili:</b> {celeb['year']}-yil ({day:02d}.{month:02d})\n"
            f"💼 <b>Kasbi:</b> {celeb['occupation']}\n"
            f"🌍 <b>Davlati:</b> {celeb['country']}\n\n"
            f"📝 <b>Qisqacha tarjimai holi:</b>\n<i>{celeb['description']}</i>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        try:
            await callback.message.answer_photo(photo=celeb['image_url'], caption=caption, parse_mode="HTML")
        except Exception:
            await callback.message.answer(caption, parse_mode="HTML")

        await asyncio.sleep(0.3)

@router.errors()
async def global_error_handler(event: Any, exception: Exception):
    logger.error(f"Global Error: {exception}")
    return True

# ==============================================================================
# MAIN APP
# ==============================================================================
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN mavjud emas!")
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
        global HTTP_SESSION
        if HTTP_SESSION and not HTTP_SESSION.closed:
            await HTTP_SESSION.close()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
