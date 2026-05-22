"""
handlers/weather.py — Забота о погоде (прогноз и советы)
"""

import aiohttp
import logging
import urllib.parse
from aiogram import Router, types
from aiogram.filters import Command
import database

router = Router()
logger = logging.getLogger(__name__)

# Default coordinates (Krasnodar)
DEFAULT_LAT = 45.0448
DEFAULT_LON = 38.9760
DEFAULT_CITY = "Краснодар"

async def search_city_coords(city_name: str) -> tuple[float, float, str] | None:
    """Searches for city coordinates using Open-Meteo Geocoding API.
    Returns (latitude, longitude, formatted_name) or None.
    """
    safe_city = urllib.parse.quote(city_name.strip())
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_city}&count=1&language=ru"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results")
                    if results:
                        city_data = results[0]
                        lat = city_data.get("latitude")
                        lon = city_data.get("longitude")
                        name = city_data.get("name")
                        country = city_data.get("country", "")
                        admin1 = city_data.get("admin1", "")
                        
                        # Build a nice full name
                        full_name = name
                        details = [d for d in [admin1, country] if d]
                        if details:
                            full_name += f" ({', '.join(details)})"
                            
                        return float(lat), float(lon), full_name
    except Exception as e:
        logger.error(f"Failed to geocode city '{city_name}': {e}")
    return None

async def get_weather_forecast(lat: float, lon: float) -> dict:
    """Fetches current weather and daily forecast from Open-Meteo API."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone=auto"
    )
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch weather: {e}")
    return {}

def _get_weather_emoji(code: int) -> str:
    """Maps WMO weather codes to emojis."""
    if code in [0]: return "☀️" # Clear
    if code in [1, 2, 3]: return "⛅" # Partly cloudy
    if code in [45, 48]: return "🌫️" # Fog
    if code in [51, 53, 55, 56, 57]: return "🌧️" # Drizzle
    if code in [61, 63, 65, 66, 67]: return "🌧️" # Rain
    if code in [71, 73, 75, 77]: return "❄️" # Snow
    if code in [80, 81, 82]: return "🌦️" # Showers
    if code in [85, 86]: return "🌨️" # Snow showers
    if code in [95, 96, 99]: return "⛈️" # Thunderstorm
    return "☁️"

def format_weather_message(data: dict, city_name: str) -> str:
    """Formats weather data into a cute message with advice."""
    if not data or "current" not in data or "daily" not in data:
        return f"Ой, я не смог узнать погоду в городе {city_name}... Посмотри в окошко! 🪟"

    current_temp = data["current"]["temperature_2m"]
    weather_code = data["current"]["weather_code"]
    
    daily_max = data["daily"]["temperature_2m_max"][0]
    daily_min = data["daily"]["temperature_2m_min"][0]
    precip_prob = data["daily"]["precipitation_probability_max"][0]
    
    emoji = _get_weather_emoji(weather_code)
    
    text = f"🌤 **Погода на сегодня: {city_name}** {emoji}\n\n"
    text += f"🌡 Сейчас: **{current_temp}°C**\n"
    text += f"📉 Мин: {daily_min}°C | 📈 Макс: {daily_max}°C\n"
    text += f"💧 Вероятность осадков: {precip_prob}%\n\n"
    
    # Add advice based on conditions
    advice = "💡 **Совет от бота:** "
    if precip_prob > 40:
        advice += "Возможен дождь, обязательно захвати зонтик! ☔ "
    elif current_temp < 10:
        advice += "На улице довольно прохладно, одевайся потеплее и не забудь шапку! 🧣🧤 "
    elif current_temp > 25:
        advice += "На улице жарко, не забудь надеть солнечные очки и пей больше воды! 🕶️🥤 "
    else:
        advice += "Погода отличная, идеальный день для прогулки! 🌿 "
        
    text += advice
    return text

@router.message(Command("weather"))
async def cmd_weather(message: types.Message):
    """Sends current weather forecast manually."""
    sent = await message.answer("⏳ Смотрю на термометр...")
    user_id = message.from_user.id
    
    # Get user custom settings or fallback to defaults
    city = database.get_user_setting(user_id, "city") or DEFAULT_CITY
    lat = database.get_user_setting(user_id, "latitude")
    lon = database.get_user_setting(user_id, "longitude")
    
    if lat is None or lon is None:
        lat, lon = DEFAULT_LAT, DEFAULT_LON
        
    weather_data = await get_weather_forecast(lat, lon)
    msg = format_weather_message(weather_data, city)
    await sent.edit_text(msg, parse_mode="Markdown")

@router.message(Command("set_city"))
async def cmd_set_city(message: types.Message):
    """Searches for city and saves it to user settings."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Пожалуйста, укажи название города.\n\n*Пример:* `/set_city Москва`", parse_mode="Markdown")
        return
        
    city_query = args[1]
    sent = await message.answer(f"🔍 Ищу город «{city_query}»...")
    
    coords = await search_city_coords(city_query)
    if not coords:
        await sent.edit_text(f"😔 Не смог найти город «{city_query}». Проверь правильность написания.")
        return
        
    lat, lon, full_name = coords
    user_id = message.from_user.id
    
    database.set_user_setting(user_id, "city", full_name)
    database.set_user_setting(user_id, "latitude", lat)
    database.set_user_setting(user_id, "longitude", lon)
    
    await sent.edit_text(
        f"✅ **Город успешно изменен!**\n\nТеперь погода будет показываться для:\n📍 *{full_name}*",
        parse_mode="Markdown"
    )

@router.message(Command("weather_sub"))
async def cmd_weather_sub(message: types.Message):
    """Toggles daily morning weather subscription."""
    user_id = message.from_user.id
    current_time = database.get_user_setting(user_id, "weather_time")
    
    if current_time:
        database.set_user_setting(user_id, "weather_time", None)
        await message.answer("Утренняя сводка погоды отключена. 🔕")
    else:
        # Default to 08:00 AM
        database.set_user_setting(user_id, "weather_time", "08:00")
        await message.answer("🌤 **Отлично!** Теперь я буду присылать тебе прогноз погоды каждое утро в 08:00.")
