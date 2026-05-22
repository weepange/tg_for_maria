"""
handlers/mood.py — Трекер настроения
"""

import logging
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database
import compliments
import config

router = Router()
logger = logging.getLogger(__name__)

MOODS = {
    "1": "😢 Плохо",
    "2": "🙁 Грустно",
    "3": "😐 Нормально",
    "4": "🙂 Хорошо",
    "5": "🥰 Отлично!"
}

MOOD_EMOJIS = {
    1: "😢",
    2: "🙁",
    3: "😐",
    4: "🙂",
    5: "🥰"
}

def get_mood_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for score, text in MOODS.items():
        builder.button(text=text, callback_data=f"mood_{score}")
    builder.adjust(1)
    return builder.as_markup()

@router.message(Command("mood"))
async def cmd_mood(message: types.Message):
    """Manually trigger mood tracker."""
    await message.answer(
        "Как твое настроение сегодня? Поделись со мной:",
        reply_markup=get_mood_keyboard()
    )

@router.message(Command("mood_sub"))
async def cmd_mood_sub(message: types.Message):
    """Toggles daily evening mood tracking prompt."""
    user_id = message.from_user.id
    current_time = database.get_user_setting(user_id, "mood_time")
    
    if current_time:
        database.set_user_setting(user_id, "mood_time", None)
        await message.answer("Вечерний опрос про настроение отключен. 🔕")
    else:
        # Default to 21:00 (9 PM)
        database.set_user_setting(user_id, "mood_time", "21:00")
        await message.answer("💖 **Записал!** Теперь каждый вечер в 21:00 я буду спрашивать, как прошел твой день.")

@router.message(Command("mood_history"))
async def cmd_mood_history(message: types.Message):
    """Shows the user's mood logs for the last 7 entries."""
    user_id = message.from_user.id
    logs = database.get_mood_logs(user_id, limit=7)
    
    if not logs:
        await message.answer("История настроения пока пуста! Запиши его с помощью команды `/mood`.")
        return
        
    text = "📅 **История твоего настроения за последние дни:**\n\n"
    # logs are ordered DESC (newest first), reverse to show chronological order
    for log in reversed(logs):
        date_str = log['date']
        score = log['score']
        emoji = MOOD_EMOJIS.get(score, "❓")
        status = MOODS.get(str(score), "Неизвестно").split(maxsplit=1)[1]
        text += f"• `{date_str}`: {emoji} {status}\n"
        
    await message.answer(text, parse_mode="Markdown")

@router.callback_query(F.data.startswith("mood_"))
async def cb_mood_selected(callback: types.CallbackQuery):
    await callback.answer()
    
    score_str = callback.data.split("_")[1]
    score = int(score_str)
    user_id = callback.from_user.id
    
    # Log mood using BOT_TZ
    today_str = datetime.now(config.BOT_TZ).strftime("%Y-%m-%d")
    database.log_mood(user_id, today_str, score)
    
    # Remove buttons
    await callback.message.edit_text(f"Твой выбор: {MOODS[score_str]}")
    
    # Respond based on score
    if score in [1, 2]:
        text = "Мне очень жаль, что тебе сегодня грустно. 🫂\nПомни, что ты со всем справишься, а плохие дни случаются у всех. Главное — хорошенько отдохнуть!\n\nЛови немного милоты для настроения:"
        
        # Try to send photo with caption
        photo = await compliments.get_pinterest_image()
        if photo:
            try:
                await callback.message.answer_photo(photo, caption=text)
            except Exception as e:
                logger.error(f"Failed to send mood cheer-up photo: {e}")
                await callback.message.answer(text)
        else:
            await callback.message.answer(text)
            
    elif score == 3:
        await callback.message.answer("Обычный день — это тоже хорошо! Завари вкусный чай и отдохни вечером. ☕")
    elif score in [4, 5]:
        await callback.message.answer("Я так рад, что у тебя хорошее настроение! Пусть таких дней будет как можно больше! 🎉✨")
