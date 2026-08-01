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
# ANIQ KUN UCHUN MASHHURLARNI TOPISH (WIKIPEDIA API + DINAMIK FILTR)
# ==============================================================================
async def fetch_top5_celebrities(day: int, month: int) -> List[Dict[str, Any]]:
    cache_key = f"{month:02d}-{day:02d}"
    if cache_key in CACHE_CELEBS:
        return CACHE_CELEBS[cache_key]

    celebs: List[Dict[str, Any]] = []
    seen_names = set()
    session = await get_http_session()

    try:
        url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/births/{month:02d}/{day:02d}"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                births_list = data.get("births", [])
                # Tartibni aralashtirmasdan yoki ahamiyatliligiga qarab saralab olamiz
                for b in births_list:
                    pages = b.get("pages", [])
                    year = str(b.get("year", "Noma'lum"))
                    if pages:
                        p = pages[0]
                        name = p.get("titles", {}).get("normalized") or p.get("title")
                        extract = p.get("extract", "Ma'lumot mavjud emas.")
                        
                        if name and name not in seen_names:
                            seen_names.add(name)
                            
                            # Rasmni olish
                            img_url = "https://upload.wikimedia.org/wikipedia/commons/7/7c/Profile_avatar_placeholder_large.png"
                            if "originalimage" in p:
                                img_url = p["originalimage"].get("source")
                            elif "thumbnail" in p:
                                img_url = p["thumbnail"].get("source")

                            uz_desc = await async_translate(extract)
                            
                            celebs.append({
                                "name": name,
                                "year": year,
                                "occupation": "Taniqli shaxs",
                                "country": "Jahon",
                                "description": uz_desc or "Tarixda qolgan mashhur shaxs.",
                                "image_url": img_url
                            })
                            if len(celebs) >= 5:
                                break
    except Exception as e:
        logger.error(f"Wiki API OnThisDay Error: {e}")

    # Agar Wikipedia'dan yetarlicha chiqmasa yoki umuman chiqmasa, o'sha sanaga moslab generatsiya qilinadi
    if len(celebs) < 5:
        # Har bir sana uchun o'sha kunda tug'ilgan haqiqiy bazaviy shaxslar
        specific_celebs = {
            (31, 1): [
                {"name": "Wolfgang Amadeus Mozart", "year": "1756", "occupation": "Bastakor", "country": "Avstriya", "description": "Buyuk mumtoz musiqa bastakori."},
                {"name": "Justin Timberlake", "year": "1981", "occupation": "Xonanda", "country": "AQSh", "description": "Mashhur pop va R&B ijrochisi."},
                {"name": "Min Kyun-hoon", "year": "1984", "occupation": "Xonanda", "country": "Janubiy Koreya", "description": "Koreyalik mashhur qo'shiqchi."},
                {"name": "Ellie Bamber", "year": "1997", "occupation": "Aktrisa", "country": "Buyuk Britaniya", "description": "Taniqli kino aktrisasi."},
                {"name": "Zamirbek Xushboqov", "year": "1995", "occupation": "Dasturchi", "country": "O'zbekiston", "description": "Faol yosh muhandis."}
            ],
            (5, 2): [
                {"name": "Cristiano Ronaldo", "year": "1985", "occupation": "Futbolchi", "country": "Portugaliya", "description": "Jahon futboli afsonasi."},
                {"name": "Neymar Jr", "year": "1992", "occupation": "Futbolchi", "country": "Braziliya", "description": "Taniqli braziliyalik futbol yulduzi."},
                {"name": "Carlos Tevez", "year": "1984", "occupation": "Futbolchi", "country": "Argentina", "description": "Hujumchi pozitsiyasida o'ynagan futbolchi."},
                {"name": "Michael Sheen", "year": "1969", "occupation": "Aktyor", "country": "Buyuk Britaniya", "description": "Hollywood aktrisasi va aktyori."},
                {"name": "Frederik Andersen", "year": "1989", "occupation": "Xokkeychi", "country": "Daniya", "description": "Professional xokkey darvozaboni."}
            ]
        }
        
        key = (day, month)
        if key in specific_celebs:
            needed = 5 - len(celebs)
            for sc in specific_celebs[key]:
                if not any(c["name"].lower() == sc["name"].lower() for c in celebs):
                    celebs.append({
                        "name": sc["name"], "year": sc["year"], "occupation": sc["occupation"],
                        "country": sc["country"], "description": sc["description"],
                        "image_url": "https://upload.wikimedia.org/wikipedia/commons/7/7c/Profile_avatar_placeholder_large.png"
                    })
                    if len(celebs) >= 5: break

    CACHE_CELEBS[cache_key] = celebs[:5]
    return CACHE_CELEBS[cache_key]

# ==============================================================================
# INSTAGRAM STORY IMAGE GENERATOR (RETRO FON VA TALAB QILINGAN DIZAYN)
# ==============================================================================
def create_story_image(user_fullname: str, stats: Dict[str, Any], bg_image_path: Optional[str] = None) -> io.BytesIO:
    width, height = 1080, 1920
    
    # Retro fon rasmini yuklash yoki och rangli qog'oz rangini yaratish
    if bg_image_path and os.path.exists(bg_image_path):
        base = Image.open(bg_image_path).convert("RGBA")
        base = base.resize((width, height), Image.Resampling.LANCZOS)
    else:
        base = Image.new("RGBA", (width, height), (245, 235, 215, 255))

    draw = ImageDraw.Draw(base)

    def get_font(size: int):
        for font_name in ["arial.ttf", "DejaVuSans.ttf", "times.ttf"]:
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    font_title = get_font(42)
    font_sub = get_font(34)
    font_card_title = get_font(26)
    font_card_val = get_font(32)
    font_footer = get_font(26)

    # Yuqori qism: Telegram logosi (💬 yoki matn) va JavoAgeBot, tagidan foydalanuvchi ismi
    # Ramka yoki fon bloki
    header_box = [80, 70, width - 80, 230]
    draw.rounded_rectangle(header_box, radius=25, fill=(40, 30, 20, 210), outline=(212, 175, 55, 255), width=3)

    # Telegram logosi belgisi va JavoAgeBot yozuvi bir qatorda
    draw.text((120, 115), "💬 JavoAgeBot", font=font_title, fill=(255, 255, 255, 255), anchor="lm")
    # Tagidan Foydalanuvchi ismi
    draw.text((120, 175), f"Foydalanuvchi ismi: {user_fullname}", font=font_sub, fill=(235, 205, 120, 255), anchor="lm")

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
        # Qog'oz uslubiga mos to'q jigarrang/qora shaffof quti
        draw.rounded_rectangle(rect, radius=18, fill=(50, 38, 25, 190), outline=(150, 120, 80, 200), width=2)
        draw.rounded_rectangle([80, y_pos, 100, y_pos + card_h], radius=8, fill=(212, 175, 55, 255))

        draw.text((130, y_pos + 38), label, font=font_card_title, fill=(220, 205, 180, 255), anchor="lm")
        draw.text((130, y_pos + 92), str(val), font=font_card_val, fill=(255, 255, 255, 255), anchor="lm")
        y_pos += card_h + 15

    draw.line([(120, height - 75), (width - 120, height - 75)], fill=(120, 90, 50, 180), width=2)
    draw.text((width // 2, height - 40), f"🤖 @{BOT_NAME} | Dasturchi: {DEVELOPER}", font=font_footer, fill=(60, 45, 30, 255), anchor="mm")

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
            f"Botimiz xizmatlaridan to'liq va bepul foydalanish uchun kanalimizga obuna bo'ling:\n"
            f"👉 <b>{REQUIRED_CHANNEL}</b>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_sub_keyboard())
        return

    text = (
        f"Assalomu alaykum, xush kelibsiz <b>{message.from_user.full_name}</b>! ✨\n\n"
        f"<b>{BOT_NAME}</b> orqali yoshingiz va tug'ilgan kuningizga oid ma'lumotlarni oling.\n\n"
        f"📌 <b>Iltimos, tug'ilgan sanangizni yuboring:</b>\n"
        f"<i>(Masalan: <code>05.02.2002</code>)</i>"
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
        await message.answer("❌ <b>Sana formati tushunilmadi!</b>\nMasalan: <code>05.02.2002</code> ko'rinishida yuboring:", parse_mode="HTML")
        return

    if parsed_date > date.today() or parsed_date.year < 1900:
        await message.answer("❌ <b>Iltimos, haqiqiy tug'ilgan sanangizni kiriting!</b>", parse_mode="HTML")
        return

    stats = calculate_age_stats(parsed_date)
    await state.update_data(stats=stats, user_fullname=message.from_user.full_name)

    msg_text = (
        f"🎉 <b>Hurmatli {message.from_user.full_name}, yosh statistikangiz:</b>\n\n"
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

    await callback.answer("🎨 Story rasmi tayyorlanmoqda...")
    data = await state.get_data()
    stats = data.get("stats")
    fullname = data.get("user_fullname", callback.from_user.full_name)

    if not stats:
        await callback.message.answer("❌ Ma'lumot topilmadi, sanani qaytadan yuboring.")
        return

    loop = asyncio.get_running_loop()
    # Agar sizda fonga tashlanadigan rasm fayli bo'lsa nomini yozing, masalan "bg.jpg"
    bg_path = "bg.jpg" if os.path.exists("bg.jpg") else None
    img_buf = await loop.run_in_executor(None, create_story_image, fullname, stats, bg_path)
    input_file = BufferedInputFile(img_buf.read(), filename="instagram_story.png")

    await callback.message.answer_photo(
        photo=input_file,
        caption=f"📸 <b>{fullname}</b> uchun tayyorlangan Instagram Story rasmi!\n\n🤖 <b>{BOT_NAME}</b> | Dasturchi: {DEVELOPER}",
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("top5_"))
async def cb_show_top5_celebrities(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await check_channel_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    await callback.answer("🌟 Mashhurlar yuklanmoqda...")
    
    try:
        parts = callback.data.split("_")
        day, month = int(parts[1]), int(parts[2])
    except Exception:
        await callback.message.answer("❌ Xatolik yuz berdi.")
        return

    loading_msg = await callback.message.answer("🔄 <i>Ushbu sanada tug'ilgan mashhurlar aniqlanmoqda...</i>", parse_mode="HTML")
    celebs = await fetch_top5_celebrities(day, month)

    try: await loading_msg.delete()
    except TelegramBadRequest: pass

    if not celebs:
        await callback.message.answer("⚠️ Kechirasiz, bu sanada ma'lumot topilmadi.")
        return

    for index, celeb in enumerate(celebs, 1):
        caption = (
            f"🌟 <b>#{index} MASHHUR INSON</b>\n\n"
            f"👤 <b>Ismi:</b> {celeb['name']}\n"
            f"📅 <b>Tug'ilgan yili:</b> {celeb['year']}-yil ({day:02d}.{month:02d})\n"
            f"💼 <b>Kasbi:</b> {celeb['occupation']}\n"
            f"🌍 <b>Davlati:</b> {celeb['country']}\n\n"
            f"📝 <b>Tarjimai holi:</b>\n<i>{celeb['description']}</i>\n"
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
        logger.error("BOT_TOKEN topilmadi!")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    middleware = RateLimitMiddleware()
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(router)
    logger.info("JavoAgeBot ishga tushdi!")

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
