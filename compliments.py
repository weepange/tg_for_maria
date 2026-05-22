import random
import aiohttp
import re
import logging
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

COMPLIMENTS = [
    "Ты делаешь этот мир намного ярче и теплее! ☀️",
    "Твоя улыбка способна растопить любой лед! 😊",
    "Каждый день с тобой — это настоящий подарок. Спасибо, что ты есть! ❤️",
    "Ты невероятно замечательный и ценный человек! 🌟",
    "Ты вдохновляешь своей добротой и внутренней силой! ✨",
    "Твой смех — один из лучших звуков на свете! 🎶",
    "Посылаю тебе лучики нежности и поддержки на весь день! ☀️🌸",
    "Ты заслуживаешь самого прекрасного дня сегодня! 🍀",
    "Твои глаза светятся теплом и добротой. ✨",
    "Ты умеешь находить прекрасное в мелочах — это удивительный дар! 🌸",
    "С тобой очень тепло и уютно. Ты — настоящее солнышко! ☀️",
    "Ты прекрасна изнутри и снаружи! 💕",
    "У тебя потрясающее чувство юмора и чудесный характер! 😊",
    "Я верю в тебя и точно знаю, что у тебя всё получится! 🚀",
    "Твое присутствие превращает обычный день в особенный! 💖",
    "Ты умеешь дарить радость и душевное тепло окружающим! 😊",
    "Ты — невероятная умница! 🧠✨",
    "Просто хочу напомнить тебе, какая ты особенная и неповторимая! ⭐",
    "Твоя нежность и забота согревают даже в самый пасмурный день. ☕",
    "Ты — человек с невероятно красивой душой! 💎",
    "Ты делаешь мир лучше просто тем, что ты в нем есть! 🌍❤️",
    "Пусть сегодня у тебя всё сложится легко, приятно и успешно! 🌟",
    "Ты — настоящее чудо, помни об этом! 🦄✨",
    "Твоя доброта делает этот мир мягче и уютнее. 💕",
    "Ты заслуживаешь всего самого светлого и радостного в жизни! ✨",
    "Ты умеешь создавать невероятную гармонию вокруг себя. 🏡❤️",
    "Каждая минута общения с тобой наполняет радостью! 🥰",
    "Ты восхитительна во всём, за что берёшься! 🎨",
    "Твоя искренность делает тебя невероятно притягательной! ✨",
    "Пусть твоя улыбка сияет сегодня как можно чаще! 🌸🌻",
    "Ты приносишь в мою жизнь столько света и позитива! 🌈",
    "Твоя поддержка для меня очень много значит. Ты — настоящее сокровище! 💎",
    "С тобой можно говорить обо всём на свете, ты лучший собеседник! 🗣️💖",
    "Твоя энергетика просто волшебна, рядом с тобой хочется улыбаться! ✨",
    "Ты всегда находишь правильные слова, чтобы поддержать! 🫂",
    "Твой взгляд такой искренний и глубокий! 👁️✨",
    "Ты делаешь этот мир чуточку добрее каждый день! 🕊️",
    "Твоя целеустремленность восхищает и мотивирует! 🏔️",
    "В тебе столько очарования и шарма, что невозможно не восхищаться! 🌺",
    "Ты даришь людям веру в чудо! 🪄",
    "Твое сердце такое большое и доброе! ❤️",
    "Ты умеешь делать самые обычные вещи особенными! 🪄",
    "Твой внутренний свет невозможно не заметить! 💡",
    "Ты — воплощение нежности и грации! 🦢",
    "С тобой мир кажется уютнее и безопаснее. 🏕️",
    "Ты вдохновляешь быть лучше! 🌱",
    "Ты самая милая и очаровательная! 🎀",
    "Твой оптимизм заразителен! 😃",
    "Ты умеешь слушать и понимать как никто другой. 👂❤️",
    "Рядом с тобой всегда легко и радостно! 🎈",
    "Ты просто невероятно милая! 🐰💖",
    "Желаю, чтобы сегодня каждый момент приносил тебе радость! 🌟",
    "Ты как чашечка горячего какао в дождливый день — согреваешь и радуешь! ☕",
    "Мир без тебя был бы намного скучнее. Спасибо, что украшаешь его! 🌺",
    "Твои идеи всегда такие креативные и интересные! 💡",
    "Ты обладаешь уникальным талантом поднимать настроение! 🎈",
    "Твоя забота о других — это что-то невероятное и прекрасное. 👐",
    "Ты сильная, смелая и очень красивая! 💪💖",
    "Пусть твой день будет таким же чудесным, как и ты сама! 🍀",
    "Ты заставляешь мое сердце улыбаться! 💓",
    "Твоя искренняя радость — это лучшее, что можно увидеть! 🎉",
    "С тобой любое приключение становится незабываемым! 🗺️",
    "Ты прекрасна даже когда просто молчишь. 🤫✨",
    "Твой голос звучит как самая любимая песня. 🎵",
    "Ты достойна миллиона роз и бесконечного счастья! 🌹",
    "Ты умеешь превращать серые будни в праздник! 🎊",
    "Твоя нежность сравнима лишь с лепестками сакуры. 🌸",
    "Ты как весенний ветерок — свежая, легкая и приносящая радость! 🍃",
    "Ты озаряешь всё вокруг своей красотой и светом! 💫"
]

# Curated list of high-quality aesthetic/cute drawings as a safe fallback
FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1501820488136-72669a482d14?w=600",  # cozy warm flowers
    "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?w=600"   # cozy night stars
]

def get_random_compliment(name: str) -> str:
    compliment = random.choice(COMPLIMENTS)
    prefix = f"🌸 <b>{name}, лови комплимент дня!</b> ✨\n\n"
    return f"{prefix}<blockquote>{compliment}</blockquote>"

async def get_pinterest_image() -> BufferedInputFile | None:
    """Fetches a random cute reaction meme (милую пикчу) from public Telegram channels (like luuvpikchi, lovepikchy).
    Falls back to a curated list of high-quality aesthetic drawings if parsing fails or returns no images.
    """
    channels = ["luuvpikchi", "lovepikchy", "pikchilib"]
    random.shuffle(channels)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    photo_url = None
    
    for channel in channels:
        url = f"https://t.me/s/{channel}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=6) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Extract background-image urls
                        matches = re.findall(r"url\('([^']+)'\)", html)
                        # Filter to only get post photos (which contain 'file/data')
                        post_photos = [m for m in matches if "file/data" in m]
                        if post_photos:
                            photo_url = random.choice(post_photos)
                            logger.info(f"Successfully scraped cute reaction image from channel @{channel}: {photo_url}")
                            break
        except Exception as e:
            logger.warning(f"Failed to scrape from channel @{channel}: {e}")
            continue

    # Fallback to Waifu Cuddle/Hug API (beautiful drawings) if Telegram scraping fails
    if not photo_url:
        logger.warning("Telegram channel scraping returned no images, trying Waifu.pics cuddle API...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.waifu.pics/sfw/cuddle", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        photo_url = data.get("url")
        except Exception as e:
            logger.warning(f"Failed to fetch from Waifu Cuddle API: {e}")
            
    # Absolute fallback
    if not photo_url:
        photo_url = random.choice(FALLBACK_IMAGES)
        logger.info(f"Using fallback aesthetic image URL: {photo_url}")
        
    # Download the image bytes to upload directly to Telegram
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url, headers=headers, timeout=10) as img_resp:
                if img_resp.status == 200:
                    img_bytes = await img_resp.read()
                    logger.info(f"Successfully downloaded image bytes from {photo_url}")
                    return BufferedInputFile(img_bytes, filename="compliment.jpg")
                else:
                    logger.warning(f"Failed to download image from {photo_url}, status {img_resp.status}")
    except Exception as e:
        logger.error(f"Error downloading image bytes: {e}", exc_info=True)
        
    return None
