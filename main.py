"""
JavoAgeBot — Enterprise Production Architecture (Single File Engine)
Framework: Aiogram 3.13+
Python Version: 3.12+
Target Deployment: Render.com (Free Instance / Container Environments)
Developer / Maintainer: @XushboqovJavohir
"""

import asyncio
import io
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from aiogram import BaseMiddleware, Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

# ==============================================================================
# 1. ATROF-MUHIT VA SYSTEM CONSTANTS
# ==============================================================================

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else 0
REQUIRED_CHANNEL: str = os.getenv("REQUIRED_CHANNEL", "@xushboqovblog").strip()

# UI va Media o'lchamlari
IMAGE_WIDTH: int = 1200
IMAGE_HEIGHT: int = 800
MAX_TELEGRAM_CAPTION_LENGTH: int = 1000
RATE_LIMIT_SECONDS: float = 1.5
CACHE_TTL_SECONDS: int = 86400  # 24 soat

if not BOT_TOKEN:
    print("CRITICAL: BOT_TOKEN muhit o'zgaruvchilarida topilmadi!", file=sys.stderr)
    sys.exit(1)

# Logger Sozlamalari (Render stdout stream)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("JavoAgeBot")

# Cache xotirasi (API javoblarini saqlash uchun)
API_CACHE: Dict[Tuple[int, int], Tuple[float, List[Dict[str, Any]]]] = {}

# ==============================================================================
# 2. LOCAL FALLBACK DATABASE (OFFLINE ARCHIVE)
# ==============================================================================

LOCAL_FALLBACK_CELEBRITIES: Dict[Tuple[int, int], List[Dict[str, Any]]] = {
    (31, 1): [
        {
            "name": "Justin Timberlake",
            "birth_date": "31.01.1981",
            "year": 1981,
            "profession": "Qo'shiqchi va aktyor",
            "country": "AQSh",
            "description": "Pop-musiqa va R&B uslubidagi mashhur amerikalik xonanda va aktyor.",
            "is_uzbek": False,
            "source": "Local Fallback DB",
        },
        {
            "name": "Kenzaburō Ōe",
            "birth_date": "31.01.1935",
            "year": 1935,
            "profession": "Yozuvchi",
            "country": "Yaponiya",
            "description": "Nobel mukofoti sovrindori bo'lgan yaponiyalik taniqli adib.",
            "is_uzbek": False,
            "source": "Local Fallback DB",
        },
    ],
    (5, 2): [
        {
            "name": "Cristiano Ronaldo",
            "birth_date": "05.02.1985",
            "year": 1985,
            "profession": "Futbolchi",
            "country": "Portugaliya",
            "description": "Dunyodagi eng sovrindor va mashhur futbolchilaridan biri, ko'plab rekordlar egasi.",
            "is_uzbek": False,
            "source": "Local Fallback DB",
        },
        {
            "name": "Neymar Jr",
            "birth_date": "05.02.1992",
            "year": 1992,
            "profession": "Futbolchi",
            "country": "Braziliya",
            "description": "Braziliya terma jamoasi va Yevropa grand klublarining yetakchi hujumchisi.",
            "is_uzbek": False,
            "source": "Local Fallback DB",
        },
        {
            "name": "Gheorghe Hagi",
            "birth_date": "05.02.1965",
            "year": 1965,
            "profession": "Futbolchi va murabbiy",
            "country": "Ruminiya",
            "description": "Ruminiya futboli afsonasi va mashhur yarim himoyachi.",
            "is_uzbek": False,
            "source": "Local Fallback DB",
        },
    ],
    (24, 6): [
        {
            "name": "Lionel Messi",
            "birth_date": "24.06.1987",
            "year": 1987,
            "profession": "Futbolchi",
            "country": "Argentina",
            "description": "Jahon chempioni, ko'p karra 'Oltin to'p' sohibi va afsonaviy futbolchi.",
            "is_uzbek": False,
            "source": "Local Fallback DB",
        },
        {
            "name": "Mirzo Ulug'bek",
            "birth_date": "22.03.1394",
            "year": 1394,
            "profession": "Olim va hukmdor",
            "country": "O'zbekiston",
            "description": "Buyuk astronom, matematik va Temuriylar sulolasining taniqli davlat arbobi.",
            "is_uzbek": True,
            "source": "Local Fallback DB",
        },
    ],
}

GENERIC_UZBEK_CELEBRITIES: List[Dict[str, Any]] = [
    {
        "name": "Amir Temur",
        "birth_date": "09.04.1336",
        "year": 1336,
        "profession": "Sarkarda va hukmdor",
        "country": "O'zbekiston",
        "description": "Markaziy Osiyoda qudratli Temuriylar davlatiga asos solgan buyuk jahongir.",
        "is_uzbek": True,
        "source": "Local Archive",
    },
    {
        "name": "Alisher Navoiy",
        "birth_date": "09.02.1441",
        "year": 1441,
        "profession": "Shoir va mutafakkir",
        "country": "O'zbekiston",
        "description": "O'zbek adabiyoti va turkiy tillar rivojiga bebaho hissa qo'shgan buyuk shoir va davlat arbobi.",
        "is_uzbek": True,
        "source": "Local Archive",
    },
    {
        "name": "Zahiriddin Muhammad Bobur",
        "birth_date": "14.02.1483",
        "year": 1483,
        "profession": "Shoir va shoh",
        "country": "O'zbekiston",
        "description": "Boburiylar imperiyasi asoschisi, 'Boburnoma' shahasarining muallifi.",
        "is_uzbek": True,
        "source": "Local Archive",
    },
]

# ==============================================================================
# 3. SINGLETON HTTP SESSION MANAGER
# ==============================================================================

class AioHttpSessionManager:
    """Aiohttp ClientSession uchun connection pooling va keep-alive boshqaruvi."""

    _session: Optional[aiohttp.ClientSession] = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """Qaytadan foydalaniluvchi aiohttp ClientSession obyektini qaytaradi yoki yaratadi."""
        if cls._session is None or cls._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
                force_close=False,
            )
            timeout = aiohttp.ClientTimeout(total=8.0, connect=3.0)
            cls._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": "JavoAgeBot/6.0 (Enterprise Architecture; +https://t.me/XushboqovJavohir)"
                },
            )
            logger.info("Yangi singleton aiohttp.ClientSession yaratildi.")
        return cls._session

    @classmethod
    async def close_session(cls) -> None:
        """Ochiq turgan aiohttp ClientSession va ulagichlarni xavfsiz yopadi."""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None
            logger.info("Singleton aiohttp.ClientSession yopildi.")

# ==============================================================================
# 4. FSM STATES & UTILS
# ==============================================================================

class AgeCalcStates(StatesGroup):
    """FSM holatlarini belgilash klassi."""
    waiting_for_date = State()

WEEKDAYS_UZ: List[str] = [
    "Dushanba", "Seshanba", "Chorshanba",
    "Payshanba", "Juma", "Shanba", "Yakshanba"
]

MONTHS_UZ: List[str] = [
    "", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"
]

ZODIAC_SIGNS: List[Tuple[int, int, str]] = [
    (1, 20, "Tog' echkisi ♑"), (2, 19, "Qovg'a ♒"), (3, 21, "Baliq ♓"),
    (4, 20, "Qo'y ♈"), (5, 21, "Buzaq ♉"), (6, 21, "Egizaklar ♊"),
    (7, 23, "Qisqichbaqa ♋"), (8, 23, "Arslon ♌"), (9, 23, "Parizod ♍"),
    (10, 23, "Tarozi ♎"), (11, 22, "Chayon ♏"), (12, 22, "O'qotar ♐"),
    (12, 32, "Tog' echkisi ♑")
]

CHINESE_ZODIAC: List[str] = [
    "Sichqon 🐀", "Buqa 🐂", "Yo'lbars 🐅", "Quyon 🐇",
    "Ajdarho 🐉", "Ilan 🐍", "Ot 🐎", "Qo'y 🐐",
    "Maymun 🐒", "Xo'roz 🐓", "It 🐕", "To'ng'iz 🐖"
]

UZBEK_KEYWORDS: List[str] = [
    "Uzbekistan", "Uzbek", "Tashkent", "Samarkand", "Bukhara", "Khiva",
    "Fergana", "Andijan", "Namangan", "Timurid", "Transoxiana", "Khwarazm",
    "O'zbekiston", "O'zbek", "Toshkent", "Samarqand", "Buxoro", "Amir Temur",
    "Babur", "Navoiy", "Ulugbek", "Avicenna", "Al-Khwarizmi", "Mirzo", "Shavkat"
]

def escape_markdown_v2(text: str) -> str:
    """MarkdownV2 maxsus belgilardan toza matn hosil qiladi."""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

def is_fuzzy_duplicate(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """Ikki ism bir-biriga yuqori o'xshashligini Fuzzy SequenceMatcher orqali aniqlaydi."""
    ratio = SequenceMatcher(None, name1.lower().strip(), name2.lower().strip()).ratio()
    return ratio >= threshold

def is_uzbek_entity(text: str) -> bool:
    """Matn tarkibida O'zbekistonga xos geografik yoki tarixiy tushunchalar mavjudligini aniqlaydi."""
    pattern = r"\b(" + "|".join(re.escape(kw) for kw in UZBEK_KEYWORDS) + r")\b"
    return bool(re.search(pattern, text, re.IGNORECASE))

def format_year_string(day: int, month: int, year: int) -> str:
    """Miloddan avvalgi (BC) va oddiy yillarni xatosiz formatlaydi."""
    if year < 0:
        return f"{day:02d}.{month:02d}.{abs(year)} BC"
    return f"{day:02d}.{month:02d}.{year:04d}"

def get_zodiac_sign(day: int, month: int) -> str:
    """Tug'ilgan kun va oy bo'yicha astrologik burjni qaytaradi."""
    for m, d, sign in ZODIAC_SIGNS:
        if month == m and day < d:
            return sign
        if month == m - 1 and day >= d:
            return sign
    return "Tog' echkisi ♑"

def get_chinese_zodiac(year: int) -> str:
    """Tug'ilgan yil bo'yicha Sharq muchal yilini hisoblaydi."""
    return CHINESE_ZODIAC[(year - 4) % 12]

def calculate_age_details(birth_date: date) -> Dict[str, Any]:
    """Kiritilgan sana bo'yicha yosh, oylar, kunlar va statistikani hisoblaydi."""
    today = datetime.now(timezone.utc).date()
    delta = relativedelta(today, birth_date)
    total_days = (today - birth_date).days
    total_weeks = total_days // 7
    total_months = delta.years * 12 + delta.months

    try:
        next_birthday = date(today.year, birth_date.month, birth_date.day)
    except ValueError:
        next_birthday = date(today.year, 2, 28)

    if next_birthday < today:
        try:
            next_birthday = date(today.year + 1, birth_date.month, birth_date.day)
        except ValueError:
            next_birthday = date(today.year + 1, 2, 28)

    days_to_next_birthday = (next_birthday - today).days

    return {
        "day": birth_date.day,
        "month": birth_date.month,
        "year": birth_date.year,
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
        "weekday": WEEKDAYS_UZ[birth_date.weekday()],
    }

# ==============================================================================
# 5. RATE LIMITER MIDDLEWARE
# ==============================================================================

class RateLimitMiddleware(BaseMiddleware):
    """Foydalanuvchi so'rovlarini cheklovchi Rate Limiter Middlewaresi."""

    def __init__(self, limit: float = RATE_LIMIT_SECONDS) -> None:
        super().__init__()
        self.limit = limit
        self.user_timestamps: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Any,
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            now = time.time()
            last_time = self.user_timestamps.get(user_id, 0.0)
            if now - last_time < self.limit:
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Iltimos, bir oz kutib qaytadan bosing!", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("⚠️ Sobir bo'ling! So'rovlar oralig'ida biroz kutishingiz kerak.")
                return None
            self.user_timestamps[user_id] = now

        return await handler(event, data)

# ==============================================================================
# 6. API FETCHERS (WITH EXPONENTIAL BACKOFF & MULTI-FALLBACK)
# ==============================================================================

async def execute_http_request_with_retry(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
) -> Optional[Dict[str, Any]]:
    """HTTP So'rovlarni Exponential Backoff algoritmi bilan amalga oshiradi."""
    session = await AioHttpSessionManager.get_session()
    delay = 0.5

    for attempt in range(1, max_retries + 1):
        try:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                logger.warning(f"HTTP {response.status} | URL: {url} | Urinish: {attempt}/{max_retries}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            logger.warning(f"Network error: {err} | URL: {url} | Urinish: {attempt}/{max_retries}")

        if attempt < max_retries:
            await asyncio.sleep(delay)
            delay *= 2
    return None

async def fetch_wikipedia_rest_api(day: int, month: int) -> List[Dict[str, Any]]:
    """Primary API: Wikipedia REST API (On This Day / Births)."""
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/births/{month}/{day}"
    data = await execute_http_request_with_retry(url)

    if not data or "births" not in data:
        return []

    results = []
    for item in data.get("births", []):
        year = item.get("year")
        pages = item.get("pages", [])
        if year is None or not pages:
            continue
        person = pages[0]
        name = person.get("titles", {}).get("normalized", person.get("title", ""))
        desc = person.get("description", "Mashhur shaxs")
        extract = person.get("extract", desc)

        full_context = f"{name} {desc} {extract}"
        is_uzb = is_uzbek_entity(full_context)

        parts = [p.strip() for p in desc.split(",")]
        prof = parts[0].capitalize() if parts else "Mashhur shaxs"
        country = "O'zbekiston" if is_uzb else (parts[1] if len(parts) > 1 else "Xalqaro")

        short_desc = extract.split(". ")[0] if extract else desc
        if len(short_desc) > 100:
            short_desc = short_desc[:97] + "..."
        if not short_desc.endswith("."):
            short_desc += "."

        results.append({
            "name": name,
            "birth_date": format_year_string(day, month, year),
            "year": year,
            "profession": prof,
            "country": country,
            "description": short_desc,
            "is_uzbek": is_uzb,
            "source": "Wikipedia REST API",
        })
    return results

async def fetch_wikidata_sparql_api(day: int, month: int) -> List[Dict[str, Any]]:
    """Secondary API: Wikidata SPARQL Direct Query."""
    query = f"""
    SELECT ?human ?humanLabel ?birthdate ?citizenshipLabel ?occupationLabel WHERE {{
      ?human wdt:P31 wd:Q5;
             wdt:P569 ?birthdate.
      FILTER(MONTH(?birthdate) = {month} && DAY(?birthdate) = {day})
      OPTIONAL {{ ?human wdt:P27 ?citizenship. }}
      OPTIONAL {{ ?human wdt:P106 ?occupation. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 30
    """
    url = "https://query.wikidata.org/sparql"
    headers = {"Accept": "application/sparql-results+json"}

    data = await execute_http_request_with_retry(url, params={"query": query}, headers=headers)
    if not data:
        return []

    bindings = data.get("results", {}).get("bindings", [])
    results = []
    for b in bindings:
        name = b.get("humanLabel", {}).get("value", "")
        if not name or name.startswith("Q"):
            continue

        bdate_str = b.get("birthdate", {}).get("value", "")
        match = re.search(r"(-?\d+)-(\d{2})-(\d{2})", bdate_str)
        if not match:
            continue

        parsed_year = int(match.group(1))
        country = b.get("citizenshipLabel", {}).get("value", "Xalqaro")
        occupation = b.get("occupationLabel", {}).get("value", "Mashhur shaxs")

        is_uzb = is_uzbek_entity(f"{name} {country}")

        results.append({
            "name": name,
            "birth_date": format_year_string(day, month, parsed_year),
            "year": parsed_year,
            "profession": occupation.capitalize(),
            "country": "O'zbekiston" if is_uzb else country,
            "description": f"{name} — o'z sohasida yuqori natijalarga erishgan mashhur shaxs.",
            "is_uzbek": is_uzb,
            "source": "Wikidata SPARQL",
        })
    return results

async def fetch_wikipedia_action_api(day: int, month: int) -> List[Dict[str, Any]]:
    """Tertiary API: Wikipedia Action MediaWiki Query."""
    month_name = MONTHS_UZ[month].capitalize()
    page_title = f"{month_name}_{day}"
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "format": "json",
    }

    data = await execute_http_request_with_retry(url, params=params)
    if not data or "parse" not in data:
        return []

    wikitext = data["parse"].get("wikitext", {}).get("*", "")
    results = []

    birth_lines = re.findall(r"\*\s*(\d{1,4})\s*–\s*([^,\n]+),?\s*([^\n]+)?", wikitext)
    for match in birth_lines[:15]:
        parsed_year = int(match[0])
        name = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", match[1]).strip()
        details = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", match[2]).strip() if len(match) > 2 else "Mashhur shaxs"

        is_uzb = is_uzbek_entity(f"{name} {details}")

        results.append({
            "name": name,
            "birth_date": format_year_string(day, month, parsed_year),
            "year": parsed_year,
            "profession": "Mashhur shaxs",
            "country": "O'zbekiston" if is_uzb else "Xalqaro",
            "description": details[:90] + "." if details else f"{name} haqida ma'lumot.",
            "is_uzbek": is_uzb,
            "source": "Wikipedia Action API",
        })
    return results

async def get_celebrities_with_fallbacks(day: int, month: int) -> List[Dict[str, Any]]:
    """Barcha API manbalarini boshqaruvchi markaziy kaskadli (Fallback) va keshlovchi algoritm."""
    cache_key = (day, month)
    now = time.time()

    # Keshni tekshirish
    if cache_key in API_CACHE:
        timestamp, cached_data = API_CACHE[cache_key]
        if now - timestamp < CACHE_TTL_SECONDS:
            logger.info(f"Keshdan ma'lumot qaytarildi ({day}.{month}).")
            return cached_data

    wiki_rest_task = fetch_wikipedia_rest_api(day, month)
    wikidata_task = fetch_wikidata_sparql_api(day, month)

    res_rest, res_wikidata = await asyncio.gather(wiki_rest_task, wikidata_task, return_exceptions=True)

    combined: List[Dict[str, Any]] = []
    if isinstance(res_rest, list):
        combined.extend(res_rest)
    if isinstance(res_wikidata, list):
        combined.extend(res_wikidata)

    if len(combined) < 5:
        action_res = await fetch_wikipedia_action_api(day, month)
        if isinstance(action_res, list):
            combined.extend(action_res)

    if not combined:
        logger.warning(f"Barcha tashqi API-lar muvaffaqiyatsiz tugadi. Local DB ishlatilmoqda ({day}.{month}).")
        local_data = LOCAL_FALLBACK_CELEBRITIES.get((day, month), [])
        combined.extend(local_data)

    unique_celebrities: List[Dict[str, Any]] = []
    for candidate in combined:
        is_dup = False
        for existing in unique_celebrities:
            if is_fuzzy_duplicate(candidate["name"], existing["name"]):
                is_dup = True
                break
        if not is_dup:
            unique_celebrities.append(candidate)

    uzbeks = [c for c in unique_celebrities if c["is_uzbek"]]
    others = [c for c in unique_celebrities if not c["is_uzbek"]]

    final_result: List[Dict[str, Any]] = []
    final_result.extend(uzbeks)

    needed = 5 - len(final_result)
    if needed > 0:
        final_result.extend(others[:needed])

    if len(final_result) < 5:
        for extra in GENERIC_UZBEK_CELEBRITIES:
            if len(final_result) >= 5:
                break
            if not any(is_fuzzy_duplicate(extra["name"], x["name"]) for x in final_result):
                final_result.append(extra)

    res = final_result[:5]
    API_CACHE[cache_key] = (now, res)
    return res

# ==============================================================================
# 7. GLASSMORPHISM ENGINE (MEMORY OPTIMIZED PILLOW)
# ==============================================================================

def create_glassmorphic_panel(
    base_img: Image.Image,
    x: int, y: int, w: int, h: int,
    radius: int = 20,
    blur_radius: int = 12,
    bg_alpha: int = 35,
    border_alpha: int = 70,
) -> None:
    """RAM sarfini optimallashtirgan holda shisha idish effekti (Glassmorphism) chizadi."""
    crop_box = (x, y, x + w, y + h)
    cropped = base_img.crop(crop_box)
    blurred = cropped.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    base_img.paste(blurred, crop_box)

    overlay = Image.new("RGBA", (w, h), (255, 255, 255, bg_alpha))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        [0, 0, w, h],
        radius=radius,
        outline=(255, 255, 255, border_alpha),
        width=2,
    )
    base_img.alpha_composite(overlay, (x, y))

def generate_glassmorphic_card(data: Dict[str, Any], username: str) -> io.BytesIO:
    """Ultra-HD sifatli yosh ko'rsatkichlari kartasini xotirada generatsiya qiladi."""
    W, H = IMAGE_WIDTH, IMAGE_HEIGHT
    base = Image.new("RGBA", (W, H), (12, 18, 32, 255))
    draw = ImageDraw.Draw(base)

    for i in range(H):
        r = int(14 + (i / H) * 18)
        g = int(20 + (i / H) * 28)
        b = int(45 + (i / H) * 45)
        draw.line([(0, i), (W, i)], fill=(r, g, b, 255))

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-100, -100, 400, 400), fill=(99, 102, 241, 60))
    glow_draw.ellipse((850, 450, 1300, 900), fill=(168, 85, 247, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(80))
    base = Image.alpha_composite(base, glow)

    create_glassmorphic_panel(base, 60, 40, 1080, 110, radius=20, bg_alpha=40)
    create_glassmorphic_panel(base, 60, 170, 680, 180, radius=24, bg_alpha=50)
    create_glassmorphic_panel(base, 60, 370, 325, 115, radius=18)
    create_glassmorphic_panel(base, 415, 370, 325, 115, radius=18)
    create_glassmorphic_panel(base, 60, 505, 325, 115, radius=18)
    create_glassmorphic_panel(base, 415, 505, 325, 115, radius=18)
    create_glassmorphic_panel(base, 760, 170, 380, 450, radius=24, bg_alpha=50)
    create_glassmorphic_panel(base, 60, 640, 1080, 110, radius=20)

    draw_final = ImageDraw.Draw(base)

    # Cross-platform / Linux Font Loader Fallback
    font_large = font_sub = font_big_num = font_title = font_val = None
    possible_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    
    font_path = None
    for p in possible_fonts:
        if os.path.exists(p):
            font_path = p
            break

    try:
        if font_path:
            font_large = ImageFont.truetype(font_path, 42)
            font_sub = ImageFont.truetype(font_path, 22)
            font_big_num = ImageFont.truetype(font_path, 58)
            font_title = ImageFont.truetype(font_path, 19)
            font_val = ImageFont.truetype(font_path, 32)
        else:
            font_large = font_sub = font_big_num = font_title = font_val = ImageFont.load_default()
    except Exception as e:
        logger.warning(f"Font yuklashda xatolik: {e}, standart font ishlatiladi.")
        font_large = font_sub = font_big_num = font_title = font_val = ImageFont.load_default()

    draw_final.text((90, 60), "JAVOAGE STATISTICS", fill=(129, 140, 248), font=font_large)
    draw_final.text((90, 112), f"Foydalanuvchi: @{username} • Tug'ilgan sana: {data['birth_date_str']}", fill=(203, 213, 225), font=font_sub)

    draw_final.text((90, 195), "🎂 YOSHINGIZ:", fill=(148, 163, 184), font=font_sub)
    age_str = f"{data['years']} yosh, {data['months']} oy, {data['days']} kun"
    draw_final.text((90, 240), age_str, fill=(255, 255, 255), font=font_big_num)

    draw_final.text((80, 385), "🗓 JAMI KUN", fill=(148, 163, 184), font=font_title)
    draw_final.text((80, 420), f"{data['total_days']:,} kun", fill=(241, 245, 249), font=font_val)

    draw_final.text((435, 385), "📊 JAMI HAFTA", fill=(148, 163, 184), font=font_title)
    draw_final.text((435, 420), f"{data['total_weeks']:,} hafta", fill=(241, 245, 249), font=font_val)

    draw_final.text((80, 520), "🌙 JAMI OY", fill=(148, 163, 184), font=font_title)
    draw_final.text((80, 555), f"{data['total_months']:,} oy", fill=(241, 245, 249), font=font_val)

    draw_final.text((435, 520), "🎁 KEYINGI TUG'ILGAN KUN", fill=(148, 163, 184), font=font_title)
    draw_final.text((435, 555), f"{data['days_to_next_birthday']} kun qoldi", fill=(241, 245, 249), font=font_val)

    draw_final.text((790, 200), "✨ ASTROLOGIYA", fill=(192, 132, 252), font=font_large)
    astro_items = [
        ("📆 Tug'ilgan kun:", data["weekday"]),
        ("🔮 Burjingiz:", data["zodiac"]),
        ("🐉 Muchalingiz:", data["muchal"]),
    ]
    ay = 275
    for title, val in astro_items:
        draw_final.text((790, ay), title, fill=(148, 163, 184), font=font_sub)
        draw_final.text((790, ay + 30), val, fill=(241, 245, 249), font=font_val)
        ay += 105

    draw_final.text((90, 660), "JavoAgeBot — Professional Yosh Kalkulyatori", fill=(241, 245, 249), font=font_sub)
    draw_final.text((90, 700), "👨‍💻 Dasturchi: @XushboqovJavohir", fill=(148, 163, 184), font=font_sub)

    bio = io.BytesIO()
    bio.name = "javoage_card.png"
    base.convert("RGB").save(bio, "PNG", optimize=True)
    bio.seek(0)
    return bio

# ==============================================================================
# 8. TELEGRAM BOT CORE & MIDDLEWARE SETUP
# ==============================================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.update.middleware(RateLimitMiddleware())

async def check_channel_subscription(user_id: int) -> bool:
    """Foydalanuvchining rasmiy kanalga obuna bo'lganligini tekshiradi."""
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except TelegramAPIError as err:
        logger.warning(f"Subscription check Telegram API error: {err}")
        return True
    except Exception as err:
        logger.error(f"Subscription check unexpected error: {err}")
        return True

def get_sub_keyboard() -> InlineKeyboardMarkup:
    """Kanalga obuna bo'lish tugmasini yaratadi."""
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=channel_url)],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")],
        ]
    )

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Asosiy menyu tugmalarini yaratadi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧮 Yoshni hisoblash", callback_data="calc_start")],
            [InlineKeyboardButton(text="ℹ️ Bot haqida", callback_data="about_bot")],
        ]
    )

# ==============================================================================
# 9. GLOBAL ERROR HANDLER
# ==============================================================================

@dp.error()
async def global_error_handler(event: ErrorEvent) -> bool:
    """Kutilmagan barcha xatoliklarni ushlab qoluvchi global error handler."""
    logger.error(f"Global Error Captured: {event.exception}", exc_info=True)

    if isinstance(event.exception, TelegramRetryAfter):
        await asyncio.sleep(event.exception.retry_after)
        return True

    if isinstance(event.exception, TelegramBadRequest):
        logger.warning(f"Bad Request Error: {event.exception}")
        return True

    if isinstance(event.exception, TelegramNetworkError):
        logger.error(f"Network Connection Error: {event.exception}")
        return True

    try:
        if event.update.message:
            await event.update.message.answer("⚠️ Tizimda kutilmagan xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.")
        elif event.update.callback_query:
            await event.update.callback_query.answer("⚠️ Tizimda xatolik yuz berdi!", show_alert=True)
    except Exception:
        pass

    return True

# ==============================================================================
# 10. HANDLERS & DIALOG FLOW
# ==============================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """/start buyrug'i uchun ishlovchi handler."""
    await state.clear()
    is_sub = await check_channel_subscription(message.from_user.id)
    if not is_sub:
        await message.answer(
            f"⚠️ **Diqqat!** Botdan foydalanish uchun rasmiy kanalimizga obuna bo'ling: {REQUIRED_CHANNEL}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_sub_keyboard(),
        )
        return

    text = (
        f"👋 **Salom, {message.from_user.full_name}!**\n\n"
        f"🌟 **JavoAgeBot** — Sizning aniq yoshingiz, yashagan statistikangiz va "
        f"siz bilan bir kunda tug'ilgan mashhur shaxslar ma'lumotlarini taqdim etuvchi professional bot.\n\n"
        f"Tug'ilgan kuningizni bilish uchun quyidagi tugmani bosing!"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery) -> None:
    """Obunani tekshirish tugmasi ishlovchisi."""
    is_sub = await check_channel_subscription(callback.from_user.id)
    if is_sub:
        await callback.message.edit_text(
            "✅ **Rahmat! Obunangiz tasdiqlandi.**\n\nQuyidagi tugma orqali davom etishingiz mumkin:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(),
        )
    else:
        await callback.answer("❌ Hali obuna bo'lmadingiz! Iltimos, avval kanalga obuna bo'ling.", show_alert=True)

@dp.callback_query(F.data == "about_bot")
async def cb_about_bot(callback: CallbackQuery) -> None:
    """Bot haqidagi bo'lim callback handler."""
    text = (
        "ℹ️ **JavoAgeBot haqida:**\n\n"
        "• **Versiya:** 6.0 Enterprise Architecture\n"
        "• **Dasturchi:** @XushboqovJavohir\n"
        "• **Texnologiyalar:** Python 3.12+, Aiogram 3.13, Pillow Glassmorphism Engine, Wikipedia & Wikidata REST APIs\n\n"
        "Bot xatolarsiz va ultra-tezkor ishlash uchun Render cloud container muhitiga moslashtirilgan."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main")]]
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

@dp.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext) -> None:
    """Asosiy menyuga qaytish callback handler."""
    await state.clear()
    await callback.message.edit_text(
        "Bosh sahifadasiz. Kerakli bo'limni tanlang:",
        reply_markup=get_main_keyboard(),
    )

@dp.callback_query(F.data == "calc_start")
async def cb_calc_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Yoshni hisoblash jarayonini boshlovchi callback handler."""
    is_sub = await check_channel_subscription(callback.from_user.id)
    if not is_sub:
        await callback.answer("⚠️ Avval kanalga obuna bo'ling!", show_alert=True)
        return

    await state.set_state(AgeCalcStates.waiting_for_date)
    text = (
        "📅 **Tug'ilgan sanangizni kiriting:**\n\n"
        "Format: `KK.OO.YYYY` (Misol uchun: `05.02.1998` yoki `24.06.1987`)"
    )
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)

@dp.message(AgeCalcStates.waiting_for_date)
async def process_date_input(message: Message, state: FSMContext) -> None:
    """Foydalanuvchi kiritgan sanani qabul qiluvchi va tahlil qiluvchi handler."""
    raw_text = message.text.strip() if message.text else ""
    match = re.match(r"^(\d{1,2})[\.\/\-\s](\d{1,2})[\.\/\-\s](\d{4})$", raw_text)

    if not match:
        await message.answer(
            "❌ **Xato sana formati!**\n\nIltimos sanani `KK.OO.YYYY` ko'rinishida kiriting (Masalan: `15.08.2001`).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    day, month, year = map(int, match.groups())

    try:
        birth_date = date(year, month, day)
    except ValueError:
        await message.answer("❌ **Mavjud bo'lmagan sana!** Iltimos, kalendardagi to'g'ri sanani kiriting.")
        return

    today = datetime.now(timezone.utc).date()
    if birth_date > today:
        await message.answer("❌ **Xato!** Tug'ilgan sana kelajakda bo'lishi mumkin emas.")
        return

    if year < 1900:
        await message.answer("❌ Iltimos, 1900-yildan keyingi sanani kiriting.")
        return

    await state.clear()
    status_msg = await message.answer("🔄 *Ma'lumotlar hisoblanmoqda va qidirilmoqda...*", parse_mode=ParseMode.MARKDOWN)

    # Statistikalarni hisoblash
    age_data = calculate_age_details(birth_date)
    username = message.from_user.username or message.from_user.first_name

    # API so'rovlari va Image generatsiyasini parallel ishga tushirish
    celeb_task = get_celebrities_with_fallbacks(day, month)
    loop = asyncio.get_running_loop()
    card_task = loop.run_in_executor(None, generate_glassmorphic_card, age_data, username)

    celebrities, card_bytes = await asyncio.gather(celeb_task, card_task)

    # Telegram Matn Uzunligi Chekloviga Qat'iy Rioya Etish
    caption = (
        f"🎉 *{escape_markdown_v2(message.from_user.full_name)} uchun yosh statistikasi*\n\n"
        f"📅 *Tug'ilgan sana:* `{escape_markdown_v2(age_data['birth_date_str'])}`\n"
        f"🎂 *Yosh:* `{escape_markdown_v2(str(age_data['years']))} yosh, {escape_markdown_v2(str(age_data['months']))} oy, {escape_markdown_v2(str(age_data['days']))} kun`\n"
        f"🗓 *Jami kun:* `{escape_markdown_v2(f'{age_data['total_days']:,}')}` kun\n"
        f"📊 *Jami hafta:* `{escape_markdown_v2(f'{age_data['total_weeks']:,}')}` hafta\n"
        f"🌙 *Jami oy:* `{escape_markdown_v2(f'{age_data['total_months']:,}')}` oy\n"
        f"🎁 *Keyingi tug'ilgan kun:* `{escape_markdown_v2(str(age_data['days_to_next_birthday']))}` kundan so'ng\n"
        f"🔮 *Burj / Muchal:* `{escape_markdown_v2(age_data['zodiac'])}` / `{escape_markdown_v2(age_data['muchal'])}`\n"
        f"📆 *Tug'ilgan kun:* `{escape_markdown_v2(age_data['weekday'])}`\n\n"
        f"🌟 *Siz bilan bir kunda \({day}\-{escape_markdown_v2(MONTHS_UZ[month])}\) tug'ilganlar:*\n"
    )

    for idx, c in enumerate(celebrities, 1):
        flag = "🇺🇿" if c["is_uzbek"] else "🌐"
        item_text = (
            f"\n{idx}\. {flag} *{escape_markdown_v2(c['name'])}* \({c['year']}\)\n"
            f"   • *Kasbi:* {escape_markdown_v2(c['profession'])}\n"
            f"   • *Ma'lumot:* {escape_markdown_v2(c['description'])}\n"
        )
        if len(caption + item_text) + 50 > MAX_TELEGRAM_CAPTION_LENGTH:
            break
        caption += item_text

    caption += "\n🤖 *JavoAgeBot — @XushboqovJavohir*"

    try:
        await status_msg.delete()
    except Exception:
        pass

    input_file = BufferedInputFile(card_bytes.getvalue(), filename="javoage_card.png")
    await message.answer_photo(
        photo=input_file,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_main_keyboard(),
    )

# ==============================================================================
# 11. LIFECYCLE HOOKS & APPLICATION ENTRYPOINT
# ==============================================================================

async def on_startup(bot: Bot) -> None:
    """Bot ishga tushganda bajariluvchi dastlabki sozlamalar."""
    logger.info("JavoAgeBot muvaffaqiyatli ishga tushdi.")
    await AioHttpSessionManager.get_session()

async def on_shutdown(bot: Bot) -> None:
    """Bot to'xtaganda barcha resurslarni xavfsiz yopish."""
    logger.info("JavoAgeBot to'xtatilmoqda...")
    await AioHttpSessionManager.close_session()

async def main() -> None:
    """Dasturning asosiy ishga tushish nuqtasi (Entrypoint)."""
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot qo'lda to'xtatildi.")
