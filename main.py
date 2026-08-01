import os
import io
import math
import logging
import asyncio
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any, Callable

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
BOT_NAME = "JavoAgeBot"
DEVELOPER = "@XushboqovJavohir"

# Storage Cache & Translations Caching
CACHE_CELEBS: Dict[str, List[Dict[str, Any]]] = {}
CACHE_DETAILS: Dict[str, Dict[str, Any]] = {}
CACHE_TRANSLATIONS: Dict[str, str] = {}

translator = GoogleTranslator(source='auto', target='uz')

# Global shared Aiohttp session for performance optimization
HTTP_SESSION: Optional[aiohttp.ClientSession] = None

async def get_http_session() -> aiohttp.ClientSession:
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        timeout = aiohttp.ClientTimeout(total=8)
        HTTP_SESSION = aiohttp.ClientSession(timeout=timeout)
    return HTTP_SESSION

# ==============================================================================
# MIDDLEWARE & RATE LIMITING
# ==============================================================================
class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.7):
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
                        await event.answer("⚠️ Iltimos, biroz kutib harakat qiling!", show_alert=False)
                    except TelegramAPIError:
                        pass
                return
            self.user_timestamps[user_id] = now

        return await handler(event, data)

# ==============================================================================
# FSM STATES
# ==============================================================================
class UserStates(StatesGroup):
    waiting_for_birthdate = State()

# ==============================================================================
# TRANSLATION HELPER
# ==============================================================================
async def async_translate(text: str) -> str:
    if not text or not text.strip():
        return ""
    if text in CACHE_TRANSLATIONS:
        return CACHE_TRANSLATIONS[text]
    try:
        loop = asyncio.get_running_loop()
        translated = await loop.run_in_executor(
            None, lambda: translator.translate(text)
        )
        if translated:
            CACHE_TRANSLATIONS[text] = translated
            return translated
        return text
    except Exception as e:
        logger.error(f"Tarjima xatosi: {e}")
        return text

# ==============================================================================
# DATE & ASTROLOGY CALCULATIONS
# ==============================================================================
WEEKDAYS_UZ = [
    "Dushanba", "SeShanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"
]

ZODIAC_SIGNS = [
    (1, 20, "Qovg'a (Aquarius)"),
    (2, 19, "Baliq (Pisces)"),
    (3, 21, "Qo'y (Aries)"),
    (4, 20, "Buqa (Taurus)"),
    (5, 21, "Ezgizaklar (Gemini)"),
    (6, 21, "Qisqichbaqa (Cancer)"),
    (7, 23, "Arslon (Leo)"),
    (8, 23, "Parizod (Virgo)"),
    (9, 23, "Tarozi (Libra)"),
    (10, 23, "Chayon (Scorpio)"),
    (11, 22, "O'qotar (Sagittarius)"),
    (12, 22, "Echki (Capricorn)")
]

MUCHAL_ANIMALS = [
    "Sichqon", "Sigir", "Yo'lbars", "Quyon", "Ajdaho", "Ilan",
    "Ot", "Qoy", "Maymun", "Tovuq", "It", "To'ng'iz"
]

def get_zodiac(day: int, month: int) -> str:
    if (month == 1 and day <= 19) or (month == 12 and day >= 22):
        return "Echki (Capricorn)"
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
    index = (year - 1900) % 12
    return MUCHAL_ANIMALS[index]

def calculate_age_stats(birth_date: date) -> Dict[str, Any]:
    today = date.today()
    
    years = today.year - birth_date.year
    months = today.month - birth_date.month
    days = today.day - birth_date.day

    if days < 0:
        months -= 1
        prev_month = (today.month - 1) if today.month > 1 else 12
        prev_year = today.year if today.month > 1 else today.year - 1
        
        if prev_month == 12:
            days_in_prev_month = 31
        else:
            days_in_prev_month = (date(prev_year, prev_month + 1, 1) - date(prev_year, prev_month, 1)).days
            
        days += days_in_prev_month

    if months < 0:
        years -= 1
        months += 12

    total_days = (today - birth_date).days
    total_weeks = total_days // 7
    total_months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)

    # Next birthday leap-year safe logic (Feb 29)
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

    weekday_uz = WEEKDAYS_UZ[birth_date.weekday()]
    zodiac = get_zodiac(birth_date.day, birth_date.month)
    muchal = get_muchal(birth_date.year)

    return {
        "birth_date_str": birth_date.strftime("%d.%m.%Y"),
        "years": years,
        "months": months,
        "days": days,
        "total_days": total_days,
        "total_weeks": total_weeks,
        "total_months": total_months,
        "days_to_next_bday": days_to_next_bday,
        "weekday": weekday_uz,
        "zodiac": zodiac,
        "muchal": muchal,
        "day": birth_date.day,
        "month": birth_date.month,
        "year": birth_date.year
    }

# ==============================================================================
# CELEBRITY API SERVICES (WIKIPEDIA / WIKIDATA)
# ==============================================================================
FALLBACK_CELEBS: Dict[str, List[Dict[str, Any]]] = {
    "01-01": [{"name": "Cristiano Ronaldo", "id": "Q26876"}, {"name": "Jirō Horikoshi", "id": "Q1320401"}],
    "02-05": [{"name": "Cristiano Ronaldo", "id": "Q26876"}, {"name": "Neymar Jr", "id": "Q142733"}],
    "01-31": [{"name": "Justin Timberlake", "id": "Q43432"}, {"name": "Jackie Robinson", "id": "Q221008"}]
}

async def fetch_celebrities_by_date(day: int, month: int) -> List[Dict[str, Any]]:
    cache_key = f"{month:02d}-{day:02d}"
    if cache_key in CACHE_CELEBS:
        return CACHE_CELEBS[cache_key]

    celebs: List[Dict[str, Any]] = []
    seen_names = set()
    session = await get_http_session()

    # 1. Wikipedia REST API
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/births/{month:02d}/{day:02d}"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                births = data.get("births", [])
                for b in births:
                    pages = b.get("pages", [])
                    if pages:
                        name = pages[0].get("titles", {}).get("normalized") or pages[0].get("title")
                        page_id = str(pages[0].get("pageid", ""))
                        if name and name not in seen_names:
                            seen_names.add(name)
                            celebs.append({"name": name, "id": page_id, "source": "wiki"})
    except Exception as e:
        logger.error(f"Wiki REST API Error: {e}")

    # 2. Wikidata Query API
    if len(celebs) < 5:
        try:
            sparql_query = f"""
            SELECT ?item ?itemLabel WHERE {{
              ?item wdt:P31 wdt:Q5;
                    wdt:P569 ?birthDate.
              FILTER(MONTH(?birthDate) = {month} && DAY(?birthDate) = {day})
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
            }} LIMIT 15
            """
            url = "https://query.wikidata.org/sparql"
            headers = {"User-Agent": "JavoAgeBot/1.0 (https://t.me/JavoAgeBot)"}
            async with session.get(url, params={"query": sparql_query, "format": "json"}, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", {}).get("bindings", [])
                    for item in results:
                        name = item.get("itemLabel", {}).get("value")
                        q_id = item.get("item", {}).get("value", "").split("/")[-1]
                        if name and not name.startswith("Q") and name not in seen_names:
                            seen_names.add(name)
                            celebs.append({"name": name, "id": q_id, "source": "wikidata"})
        except Exception as e:
            logger.error(f"Wikidata API Error: {e}")

    # 3. Fallback Database
    if not celebs and cache_key in FALLBACK_CELEBS:
        for f_celeb in FALLBACK_CELEBS[cache_key]:
            if f_celeb["name"] not in seen_names:
                seen_names.add(f_celeb["name"])
                celebs.append(f_celeb)

    celebs = celebs[:15]
    CACHE_CELEBS[cache_key] = celebs
    return celebs

async def fetch_celebrity_details(name: str) -> Dict[str, Any]:
    if name in CACHE_DETAILS:
        return CACHE_DETAILS[name]

    details = {
        "name": name,
        "occupation": "Noma'lum",
        "country": "Noma'lum",
        "description": "Ma'lumot topilmadi.",
        "image_url": None
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
                
                details["description"] = uz_desc if uz_desc else "Ma'lumot topilmadi."
                details["occupation"] = uz_occ if uz_occ else "Mashhur shaxs"
                
                if "born in" in raw_desc.lower():
                    try:
                        parts = raw_desc.lower().split("born in")[1].split(".")[0].split(",")
                        if len(parts) > 1:
                            raw_country = parts[-1].strip().title()
                            details["country"] = await async_translate(raw_country)
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"Celebrity Details Fetch Error: {e}")

    CACHE_DETAILS[name] = details
    return details

# ==============================================================================
# PERCHMENT IMAGE GENERATOR
# ==============================================================================
def create_parchment_texture(width: int, height: int) -> Image.Image:
    base = Image.new("RGBA", (width, height), (235, 215, 175, 255))
    
    import random
    noise = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ndraw = ImageDraw.Draw(noise)
    for _ in range(3000):
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(1, 3)
        alpha = random.randint(10, 40)
        ndraw.ellipse([x, y, x + r, y + r], fill=(120, 80, 40, alpha))
    
    base = Image.alpha_composite(base, noise)

    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    
    margin = 30
    for i in range(margin, 0, -1):
        alpha = int((1 - i / margin) ** 2 * 220)
        vdraw.rectangle([margin - i, margin - i, width - margin + i, height - margin + i], outline=(60, 30, 10, alpha), width=2)

    vdraw.rectangle([margin, margin, width - margin, height - margin], outline=(100, 60, 20, 200), width=3)
    vdraw.rectangle([margin + 6, margin + 6, width - margin - 6, height - margin - 6], outline=(140, 90, 40, 150), width=1)

    nail_color = (80, 75, 70, 255)
    nail_highlight = (180, 175, 170, 255)
    corners = [
        (margin + 18, margin + 18),
        (width - margin - 18, margin + 18),
        (margin + 18, height - margin - 18),
        (width - margin - 18, height - margin - 18)
    ]
    for cx, cy in corners:
        vdraw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(30, 20, 10, 180))
        vdraw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=nail_color)
        vdraw.ellipse([cx - 4, cy - 4, cx, cy], fill=nail_highlight)

    return Image.alpha_composite(base, vignette)

def generate_parchment_image(user_fullname: str, stats: Dict[str, Any]) -> io.BytesIO:
    width, height = 900, 1150
    img = create_parchment_texture(width, height)
    draw = ImageDraw.Draw(img)

    def load_font(size: int):
        try:
            return ImageFont.truetype("times.ttf", size)
        except IOError:
            try:
                return ImageFont.truetype("DejaVuSerif.ttf", size)
            except IOError:
                return ImageFont.load_default()

    font_header = load_font(42)
    font_title = load_font(30)
    font_body = load_font(24)
    font_footer = load_font(20)

    color_header = (80, 30, 10, 255)
    color_text = (40, 25, 15, 255)
    color_accent = (140, 40, 20, 255)

    draw.text((width // 2, 70), BOT_NAME.upper(), font=font_header, fill=color_header, anchor="mm")
    draw.line([(150, 105), (width - 150, 105)], fill=color_accent, width=2)
    draw.text((width // 2, 125), f"Taqdim etadi: {user_fullname}", font=font_title, fill=color_accent, anchor="mm")

    y_start = 180
    line_height = 42

    items = [
        ("📅 Tug'ilgan sana:", stats['birth_date_str']),
        ("⏳ Aniq yoshingiz:", f"{stats['years']} yosh, {stats['months']} oy, {stats['days']} kun"),
        ("🗓 O'tgan kunlar:", f"{stats['total_days']:,} kun".replace(",", " ")),
        ("📊 O'tgan haftalar:", f"{stats['total_weeks']:,} hafta".replace(",", " ")),
        ("🌙 O'tgan oylar:", f"{stats['total_months']:,} oy".replace(",", " ")),
        ("🎂 Keyingi tug'ilgan kun:", f"{stats['days_to_next_bday']} kundan so'ng"),
        ("📆 Tug'ilgan hafta kuni:", stats['weekday']),
        ("✨ Burj (Zodiac):", stats['zodiac']),
        ("🐉 Muchal yili:", stats['muchal'])
    ]

    for label, val in items:
        draw.text((82, y_start + 1), label, font=font_body, fill=(200, 180, 150, 150))
        draw.text((80, y_start), label, font=font_body, fill=color_text)
        
        draw.text((width - 80, y_start), val, font=font_body, fill=color_accent, anchor="rm")
        
        draw.line([(380, y_start + 18), (width - 320, y_start + 18)], fill=(160, 130, 90, 100), width=1)
        y_start += line_height + 15

    draw.line([(100, y_start + 20), (width - 100, y_start + 20)], fill=color_header, width=2)
    draw.text((width // 2, height - 70), f"Developer: {DEVELOPER}", font=font_footer, fill=color_header, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ==============================================================================
# ROUTERS & HANDLERS
# ==============================================================================
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        f"👋 Salom, <b>{message.from_user.full_name}</b>!\n"
        f"🤖 <b>{BOT_NAME}</b> ga xush kelibsiz.\n\n"
        f"Tug'ilgan kuningizni yuboring (Masalan: <code>05.02.2002</code> yoki <code>2002-02-05</code>):"
    )
    await message.answer(text, parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_birthdate)

@router.message(UserStates.waiting_for_birthdate)
async def process_birthdate(message: Message, state: FSMContext):
    raw_text = message.text.strip() if message.text else ""
    parsed_date = None

    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed_date = datetime.strptime(raw_text, fmt).date()
            break
        except ValueError:
            pass

    if not parsed_date:
        await message.answer("❌ Noto'g'ri sana formati! Iltimos, masalan: <code>05.02.2002</code> ko'rinishida kiriting.", parse_mode="HTML")
        return

    if parsed_date > date.today() or parsed_date.year < 1900:
        await message.answer("❌ Iltimos, haqiqiy tug'ilgan sanangizni kiriting!", parse_mode="HTML")
        return

    stats = calculate_age_stats(parsed_date)
    await state.update_data(stats=stats, user_fullname=message.from_user.full_name)

    msg_text = (
        f"🎉 <b>YOSH STATISTIKASI</b> 🎉\n\n"
        f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name}\n"
        f"📅 <b>Tug'ilgan sana:</b> {stats['birth_date_str']}\n"
        f"⏳ <b>Yoshingiz:</b> {stats['years']} yosh, {stats['months']} oy, {stats['days']} kun\n\n"
        f"🗓 <b>O'tgan kunlar:</b> {stats['total_days']:,}\n"
        f"📊 <b>O'tgan haftalar:</b> {stats['total_weeks']:,}\n"
        f"🌙 <b>O'tgan oylar:</b> {stats['total_months']:,}\n"
        f"🎂 <b>Keyingi tug'ilgan kun:</b> {stats['days_to_next_bday']} kundan so'ng\n\n"
        f"📆 <b>Hafta kuni:</b> {stats['weekday']}\n"
        f"✨ <b>Burj:</b> {stats['zodiac']}\n"
        f"🐉 <b>Muchal yili:</b> {stats['muchal']}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Ma'lumotni rasm shaklida olish", callback_data="get_parchment_img")],
        [InlineKeyboardButton(text="🌟 Shu sanada tug'ilgan mashhurlar", callback_data=f"celebs_{stats['day']}_{stats['month']}")]
    ])

    await message.answer(msg_text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "get_parchment_img")
async def cb_get_parchment_img(callback: CallbackQuery, state: FSMContext):
    await callback.answer("🖼 Rasm tayyorlanmoqda...")
    data = await state.get_data()
    stats = data.get("stats")
    fullname = data.get("user_fullname", callback.from_user.full_name)

    if not stats:
        await callback.message.answer("❌ Ma'lumot topilmadi, qaytadan sanani kiriting.")
        return

    loop = asyncio.get_running_loop()
    img_buf = await loop.run_in_executor(None, generate_parchment_image, fullname, stats)
    input_file = BufferedInputFile(img_buf.read(), filename="age_stats.png")

    await callback.message.answer_photo(
        photo=input_file,
        caption=f"📜 <b>{fullname}</b> uchun tayyorlangan pergament ma'lumoti.\n🤖 {BOT_NAME} | {DEVELOPER}",
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("celebs_"))
async def cb_show_celebrities(callback: CallbackQuery, state: FSMContext):
    await callback.answer("🌟 Mashhurlar ro'yxati yuklanmoqda...")
    parts = callback.data.split("_")
    day = int(parts[1])
    month = int(parts[2])

    celebs = await fetch_celebrities_by_date(day, month)

    if not celebs:
        await callback.message.answer("❌ Ushbu sanada tug'ilgan mashhurlar topilmadi.")
        return

    # Cache celebrity map in FSM state to preserve strict <= 64 byte CallbackData rule
    celeb_map = {}
    buttons = []
    for idx, c in enumerate(celebs):
        c_name = c["name"]
        celeb_map[str(idx)] = c_name
        buttons.append([InlineKeyboardButton(text=f"👤 {c_name}", callback_data=f"c_i:{idx}")])

    await state.update_data(celeb_map=celeb_map)

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(f"🌟 <b>{day:02d}.{month:02d}</b> sanasida tug'ilgan mashhurlar:", parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("c_i:"))
async def cb_show_single_celebrity(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    idx = callback.data.split("c_i:")[1]
    
    data = await state.get_data()
    celeb_map = data.get("celeb_map", {})
    c_name = celeb_map.get(idx)

    if not c_name:
        await callback.message.answer("❌ Ma'lumot topilmadi. Qaytadan urinib ko'ring.")
        return

    details = await fetch_celebrity_details(c_name)

    text = (
        f"👤 <b>{details['name']}</b>\n\n"
        f"💼 <b>Kasbi:</b> {details['occupation']}\n"
        f"🌍 <b>Davlat:</b> {details['country']}\n\n"
        f"📝 <b>Qisqa tavsif:</b> {details['description']}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🖼 Rasmini ko'rish", callback_data=f"c_p:{idx}"),
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="delete_current_msg")
        ]
    ])

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("c_p:"))
async def cb_show_celebrity_image(callback: CallbackQuery, state: FSMContext):
    idx = callback.data.split("c_p:")[1]
    
    data = await state.get_data()
    celeb_map = data.get("celeb_map", {})
    c_name = celeb_map.get(idx)

    if not c_name:
        await callback.answer("❌ Ma'lumot topilmadi.", show_alert=True)
        return

    details = await fetch_celebrity_details(c_name)
    image_url = details.get("image_url")

    if not image_url:
        await callback.answer("❌ Rasm topilmadi", show_alert=True)
        return

    await callback.answer("🖼 Rasm yuklanmoqda...")
    try:
        await callback.message.answer_photo(
            photo=image_url,
            caption=f"👤 <b>{details['name']}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        await callback.message.answer("❌ Rasm topilmadi yoki yuklashda xatolik yuz berdi.")

@router.callback_query(F.data == "delete_current_msg")
async def cb_delete_msg(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

@router.errors()
async def global_error_handler(event: Any, exception: Exception):
    logger.error(f"Global Error Handled: {exception}")
    return True

# ==============================================================================
# MAIN APPLICATION INITIALIZATION
# ==============================================================================
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN aniqlanmadi! Environment Variable ga BOT_TOKEN qo'shing.")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    rate_limit_middleware = RateLimitMiddleware()
    dp.message.middleware(rate_limit_middleware)
    dp.callback_query.middleware(rate_limit_middleware)

    dp.include_router(router)

    logger.info("Bot muvaffaqiyatli ishga tushdi!")
    
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
