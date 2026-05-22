import re
import time
from datetime import datetime, timedelta, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database

router = Router()

# Timezone for display: Configured timezone (falls back to local system timezone)
from config import BOT_TZ
MSK_TZ = BOT_TZ

WEEKDAYS_RU = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
WEEKDAYS_PLURAL = ["понедельникам", "вторникам", "средам", "четвергам", "пятницам", "субботам", "воскресеньям"]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

RU_WEEKDAYS_MAP = {
    "понедельник": 0, "пн": 0,
    "вторник": 1, "вт": 1,
    "среду": 2, "среда": 2, "ср": 2,
    "четверг": 3, "чт": 3,
    "пятницу": 4, "пятница": 4, "пт": 4,
    "субботу": 5, "суббота": 5, "сб": 5,
    "воскресенье": 6, "вс": 6
}

class ReminderStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_period = State()
    waiting_for_weekday = State()
    waiting_for_time_abs = State()
    waiting_for_time_rel = State()

# --- Time calculation helpers ---

def format_timestamp(ts: int) -> str:
    """Formats a UNIX timestamp into a readable Moscow Time string."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(MSK_TZ)
    return dt.strftime("%d.%m.%Y в %H:%M")

def get_time_string_from_ts(ts: int) -> str:
    """Extracts only the HH:MM from a timestamp in MSK."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(MSK_TZ)
    return dt.strftime("%H:%M")

def get_next_daily_timestamp(time_str: str) -> int | None:
    """Calculates the next occurrence of a time HH:MM (MSK)."""
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        now = datetime.now(MSK_TZ)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return int(target.timestamp())
    except Exception:
        return None

def get_next_weekly_timestamp(day_of_week: int, time_str: str) -> int | None:
    """Calculates the next occurrence of a weekday (0-6) at HH:MM (MSK)."""
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            return None
        now = datetime.now(MSK_TZ)
        days_ahead = day_of_week - now.weekday()
        if days_ahead <= 0:  # Target day is today or earlier this week
            if days_ahead == 0:
                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target_time <= now:
                    days_ahead = 7
            else:
                days_ahead += 7
        target = now + timedelta(days=days_ahead)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return int(target.timestamp())
    except Exception:
        return None

def parse_time_offset(time_str: str) -> int | None:
    """Parses relative offset strings like '5м', '2ч', '1д' and returns seconds."""
    time_str = time_str.strip().lower()
    match = re.match(r"^(\d+)\s*([мmчhcдd])$", time_str)
    if not match:
        return None
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    if unit in ('м', 'm'):
        return amount * 60
    elif unit in ('ч', 'h', 'c', 'ч'):
        return amount * 3600
    elif unit in ('д', 'd'):
        return amount * 86400
    return None

def parse_absolute_time(text: str) -> str | None:
    """Tries to extract HH:MM from various user inputs like '19:30', '19.30', '19 30', 'в 19:30'."""
    text = text.strip().lower()
    if text.startswith("в "):
        text = text[2:].strip()
    
    # Try to find two numbers separated by :, ., - or space
    match = re.match(r"^(\d{1,2})[:.\-\s](\d{2})$", text)
    if match:
        h, m = match.groups()
        if 0 <= int(h) < 24 and 0 <= int(m) < 60:
            return f"{int(h):02d}:{int(m):02d}"
        
    # Also support just 3-4 digits without separator like '1930' or '830'
    match = re.match(r"^(\d{1,2})(\d{2})$", text)
    if match:
        h, m = match.groups()
        if 0 <= int(h) < 24 and 0 <= int(m) < 60:
            return f"{int(h):02d}:{int(m):02d}"
        
    return None

# --- Fast Command Parser ---

def parse_fast_command(message_text: str):
    """Parses commands like:
    - /remind Купить хлеб в 19:30
    - /remind Пить воду каждый день в 08:00
    - /remind Полить цветы каждую пятницу в 18:00
    - /remind Позвонить маме 15м
    - /remind 10м Выключить плиту
    """
    text = message_text.replace("/remind", "", 1).strip()
    if not text:
        return None

    # 1. Weekly: <text> каждый/каждую/в <day_of_week> [в] <time>
    weekly_pattern = r"^(.+?)\s+(?:каждый|каждую|каждую\s+пятницу|каждый\s+понедельник|в|во)?\s*(понедельник|вторник|среду|среда|четверг|пятницу|пятница|субботу|суббота|воскресенье)\s+(?:в\s+)?(\d{1,2}:\d{2})$"
    match = re.match(weekly_pattern, text, re.IGNORECASE)
    if match:
        reminder_text = match.group(1).strip()
        weekday_str = match.group(2).lower()
        time_str = match.group(3)
        weekday = RU_WEEKDAYS_MAP.get(weekday_str)
        if weekday is not None:
            ts = get_next_weekly_timestamp(weekday, time_str)
            if ts:
                return {"text": reminder_text, "interval": "weekly", "remind_at": ts}

    # 2. Daily: <text> каждый день [в] <time>
    daily_pattern = r"^(.+?)\s+каждый\s+день\s+(?:в\s+)?(\d{1,2}:\d{2})$"
    match = re.match(daily_pattern, text, re.IGNORECASE)
    if match:
        reminder_text = match.group(1).strip()
        time_str = match.group(2)
        ts = get_next_daily_timestamp(time_str)
        if ts:
            return {"text": reminder_text, "interval": "daily", "remind_at": ts}

    # 3. Once with absolute time at start: <time> <text>
    # e.g., "19:30 Купить молоко" or "в 19:30 Купить молоко"
    once_start_pattern = r"^(?:в\s+)?(\d{1,2}:\d{2})\s+(.+)$"
    match = re.match(once_start_pattern, text, re.IGNORECASE)
    if match:
        time_str = match.group(1)
        reminder_text = match.group(2).strip()
        ts = get_next_daily_timestamp(time_str)
        if ts:
            return {"text": reminder_text, "interval": "once", "remind_at": ts}

    # 4. Once with absolute time at end: <text> [сегодня] [в] <time>
    # e.g., "Купить молоко в 19:30" or "Купить молоко сегодня 19:30" or "Купить молоко 19:30"
    once_time_pattern = r"^(.+?)\s+(?:сегодня\s+)?(?:в\s+)?(\d{1,2}:\d{2})$"
    match = re.match(once_time_pattern, text, re.IGNORECASE)
    if match:
        reminder_text = match.group(1).strip()
        time_str = match.group(2)
        ts = get_next_daily_timestamp(time_str)
        if ts:
            return {"text": reminder_text, "interval": "once", "remind_at": ts}

    # 5. Once with relative offset at start: <offset> <text>
    offset_start_pattern = r"^(\d+)\s*([мmчhcдd])\s+(.+)$"
    match = re.match(offset_start_pattern, text, re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        reminder_text = match.group(3).strip()
        offset = parse_time_offset(f"{amount}{unit}")
        if offset:
            return {"text": reminder_text, "interval": "once", "remind_at": int(time.time() + offset)}

    # 6. Once with relative offset at end: <text> <offset>
    offset_end_pattern = r"^(.+?)\s+(\d+)\s*([мmчhcдd])$"
    match = re.match(offset_end_pattern, text, re.IGNORECASE)
    if match:
        reminder_text = match.group(1).strip()
        amount = int(match.group(2))
        unit = match.group(3)
        offset = parse_time_offset(f"{amount}{unit}")
        if offset:
            return {"text": reminder_text, "interval": "once", "remind_at": int(time.time() + offset)}

    return None

# --- Keyboards ---

def get_period_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 Один раз", callback_data="period:once")
    builder.button(text="🔄 Каждый день", callback_data="period:daily")
    builder.button(text="📅 Раз в неделю", callback_data="period:weekly")
    builder.button(text="❌ Отмена", callback_data="remind_cancel")
    builder.adjust(1, 2, 1)
    return builder.as_markup()

def get_time_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏱️ 5 минут", callback_data="remind_time:5m")
    builder.button(text="⏱️ 15 минут", callback_data="remind_time:15m")
    builder.button(text="⏱️ 30 минут", callback_data="remind_time:30m")
    builder.button(text="⏱️ 1 час", callback_data="remind_time:1h")
    builder.button(text="⏱️ 3 часа", callback_data="remind_time:3h")
    builder.button(text="📅 1 день", callback_data="remind_time:1d")
    builder.button(text="❌ Отмена", callback_data="remind_cancel")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_weekdays_keyboard():
    builder = InlineKeyboardBuilder()
    for idx, day in enumerate(WEEKDAYS_SHORT):
        builder.button(text=day, callback_data=f"weekday:{idx}")
    builder.button(text="❌ Отмена", callback_data="remind_cancel")
    builder.adjust(4, 3, 1)
    return builder.as_markup()


# --- Command /remind entry point ---
@router.message(Command("remind"))
async def cmd_remind(message: types.Message, state: FSMContext):
    # Try parsing fast command
    parsed = parse_fast_command(message.text)
    
    if parsed:
        reminder_id = database.add_reminder(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            text=parsed['text'],
            remind_at=parsed['remind_at'],
            interval=parsed['interval'],
            user_first_name=message.from_user.first_name
        )
        
        readable_time = format_timestamp(parsed['remind_at'])
        
        if parsed['interval'] == "daily":
            desc = f"⏰ <b>Когда:</b> ежедневно в {get_time_string_from_ts(parsed['remind_at'])}"
        elif parsed['interval'] == "weekly":
            dt = datetime.fromtimestamp(parsed['remind_at'], tz=timezone.utc).astimezone(MSK_TZ)
            weekday_name = WEEKDAYS_PLURAL[dt.weekday()]
            desc = f"⏰ <b>Когда:</b> каждую неделю по {weekday_name} в {get_time_string_from_ts(parsed['remind_at'])}"
        else:
            desc = f"⏰ <b>Когда:</b> {readable_time}"

        await message.answer(
            f"✅ <b>Напоминание успешно создано!</b>\n\n"
            f"<blockquote>📝 <b>Что:</b> {parsed['text']}\n"
            f"{desc} (по МСК)</blockquote>\n"
            f"🔔 <i>Первое уведомление: {readable_time}.</i>"
        )
        return

    # If parsing failed or no args, start FSM Wizard
    await state.set_state(ReminderStates.waiting_for_text)
    await message.answer(
        "📝 <b>Создание напоминания</b>\n\n"
        "Что вам напомнить?\n"
        "<i>Отправьте мне текст напоминания (например: «Выключить плиту»)...</i>",
        reply_markup=types.ReplyKeyboardRemove()
    )

# Wizard Step 1: Text
@router.message(ReminderStates.waiting_for_text)
async def process_reminder_text(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение.")
        return
        
    await state.update_data(text=message.text)
    await state.set_state(ReminderStates.waiting_for_period)
    
    await message.answer(
        "🔄 <b>Выберите периодичность напоминания:</b>",
        reply_markup=get_period_keyboard()
    )

# Wizard Step 2: Period Selection
@router.callback_query(ReminderStates.waiting_for_period, F.data.startswith("period:"))
async def process_period_callback(callback_query: types.CallbackQuery, state: FSMContext):
    period = callback_query.data.split(":")[1]
    await state.update_data(interval=period)
    
    if period == "once":
        await state.set_state(ReminderStates.waiting_for_time_rel)
        await callback_query.message.edit_text(
            "⏰ <b>Когда вам напомнить?</b>\n\n"
            "Выберите интервал или напишите своё время (например: <code>15м</code>, <code>2ч</code>, <code>1д</code>):",
            reply_markup=get_time_keyboard()
        )
    elif period == "daily":
        await state.set_state(ReminderStates.waiting_for_time_abs)
        await callback_query.message.edit_text(
            "⏰ <b>Введите время ежедневного напоминания:</b>\n\n"
            "Пришлите время в формате <code>ЧЧ:ММ</code> (по московскому времени), например: <code>08:00</code> или <code>21:30</code>."
        )
    elif period == "weekly":
        await state.set_state(ReminderStates.waiting_for_weekday)
        await callback_query.message.edit_text(
            "📅 <b>Выберите день недели для напоминания:</b>",
            reply_markup=get_weekdays_keyboard()
        )
    await callback_query.answer()

# Wizard Step 3 (Weekly): Weekday Selection
@router.callback_query(ReminderStates.waiting_for_weekday, F.data.startswith("weekday:"))
async def process_weekday_callback(callback_query: types.CallbackQuery, state: FSMContext):
    weekday = int(callback_query.data.split(":")[1])
    await state.update_data(weekday=weekday)
    await state.set_state(ReminderStates.waiting_for_time_abs)
    
    await callback_query.message.edit_text(
        f"⏰ Вы выбрали: <b>{WEEKDAYS_RU[weekday].capitalize()}</b>\n\n"
        "Теперь введите время напоминания в формате <code>ЧЧ:ММ</code> (по московскому времени), например: <code>12:00</code>."
    )
    await callback_query.answer()

# Wizard Step 4 (Once - Relative or Absolute Time Text Input)
@router.message(ReminderStates.waiting_for_time_rel)
async def process_time_rel_message(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    
    # 1. Try parsing as relative offset
    offset_seconds = parse_time_offset(user_input)
    if offset_seconds is not None:
        data = await state.get_data()
        reminder_text = data['text']
        remind_at = int(time.time() + offset_seconds)
        
        database.add_reminder(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            text=reminder_text,
            remind_at=remind_at,
            interval="once",
            user_first_name=message.from_user.first_name
        )
        
        readable_time = format_timestamp(remind_at)
        await state.clear()
        await message.answer(
            f"✅ <b>Напоминание успешно создано!</b>\n\n"
            f"<blockquote>📝 <b>Что:</b> {reminder_text}\n"
            f"⏰ <b>Когда:</b> {readable_time} (по МСК)</blockquote>\n"
            f"🔔 <i>Я пришлю уведомление вовремя.</i>"
        )
        return
        
    # 2. Try parsing as absolute time (e.g. 19:30)
    abs_time_str = parse_absolute_time(user_input)
    if abs_time_str is not None:
        remind_at = get_next_daily_timestamp(abs_time_str)
        if remind_at is not None:
            data = await state.get_data()
            reminder_text = data['text']
            
            database.add_reminder(
                user_id=message.from_user.id,
                chat_id=message.chat.id,
                text=reminder_text,
                remind_at=remind_at,
                interval="once",
                user_first_name=message.from_user.first_name
            )
            
            readable_time = format_timestamp(remind_at)
            await state.clear()
            await message.answer(
                f"✅ <b>Напоминание успешно создано!</b>\n\n"
                f"<blockquote>📝 <b>Что:</b> {reminder_text}\n"
                f"⏰ <b>Когда:</b> {readable_time} (по МСК)</blockquote>\n"
                f"🔔 <i>Я пришлю уведомление вовремя.</i>"
            )
            return

    # If both failed:
    await message.answer(
        "⚠️ <b>Некорректный формат времени!</b>\n\n"
        "Пришлите время:\n"
        "• Интервалом (например: <code>15м</code>, <code>2ч</code>)\n"
        "• Конкретным временем (например: <code>19:30</code>, <code>8:00</code>)"
    )

# Wizard Step 4 (Once - Relative Time Inline Selection)
@router.callback_query(ReminderStates.waiting_for_time_rel, F.data.startswith("remind_time:"))
async def process_time_rel_callback(callback_query: types.CallbackQuery, state: FSMContext):
    time_key = callback_query.data.split(":")[1]
    offset_seconds = parse_time_offset(time_key)
    
    if not offset_seconds:
        await callback_query.answer("Ошибка в формате.")
        return
        
    data = await state.get_data()
    reminder_text = data['text']
    remind_at = int(time.time() + offset_seconds)
    
    database.add_reminder(
        user_id=callback_query.from_user.id,
        chat_id=callback_query.message.chat.id,
        text=reminder_text,
        remind_at=remind_at,
        interval="once",
        user_first_name=callback_query.from_user.first_name
    )
    
    readable_time = format_timestamp(remind_at)
    await state.clear()
    
    await callback_query.message.edit_text(
        f"✅ <b>Напоминание успешно создано!</b>\n\n"
        f"<blockquote>📝 <b>Что:</b> {reminder_text}\n"
        f"⏰ <b>Когда:</b> {readable_time} (по МСК)</blockquote>\n"
        f"🔔 <i>Я пришлю уведомление вовремя.</i>"
    )
    await callback_query.answer()

# Wizard Step 4 (Daily/Weekly - Absolute Time HH:MM Input)
@router.message(ReminderStates.waiting_for_time_abs)
async def process_time_abs_message(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    if not re.match(r"^\d{1,2}:\d{2}$", time_str):
        await message.answer("⚠️ Неверный формат времени. Введите время в формате <code>ЧЧ:ММ</code>, например: <code>18:30</code>.")
        return
        
    data = await state.get_data()
    interval = data['interval']
    reminder_text = data['text']
    
    if interval == "daily":
        remind_at = get_next_daily_timestamp(time_str)
        if not remind_at:
            await message.answer("⚠️ Неверные часы или минуты. Попробуйте еще раз.")
            return
        
        database.add_reminder(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            text=reminder_text,
            remind_at=remind_at,
            interval="daily",
            user_first_name=message.from_user.first_name
        )
        
        readable_time = format_timestamp(remind_at)
        await state.clear()
        
        await message.answer(
            f"✅ <b>Ежедневное напоминание создано!</b>\n\n"
            f"<blockquote>📝 <b>Что:</b> {reminder_text}\n"
            f"⏰ <b>Когда:</b> ежедневно в {time_str} (по МСК)</blockquote>\n"
            f"🔔 <i>Первое уведомление: {readable_time}.</i>"
        )
        
    elif interval == "weekly":
        weekday = data['weekday']
        remind_at = get_next_weekly_timestamp(weekday, time_str)
        if not remind_at:
            await message.answer("⚠️ Неверные часы или минуты. Попробуйте еще раз.")
            return
            
        database.add_reminder(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            text=reminder_text,
            remind_at=remind_at,
            interval="weekly",
            user_first_name=message.from_user.first_name
        )
        
        readable_time = format_timestamp(remind_at)
        await state.clear()
        
        await message.answer(
            f"✅ <b>Еженедельное напоминание создано!</b>\n\n"
            f"<blockquote>📝 <b>Что:</b> {reminder_text}\n"
            f"⏰ <b>Когда:</b> по {WEEKDAYS_PLURAL[weekday]} в {time_str} (по МСК)</blockquote>\n"
            f"🔔 <i>Первое уведомление: {readable_time}.</i>"
        )

# Wizard Cancel
@router.callback_query(F.data == "remind_cancel")
async def process_cancel_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.edit_text("❌ <b>Создание напоминания отменено.</b>")
    await callback_query.answer()


# --- View List Command ---
@router.message(Command("list", "reminders"))
async def cmd_list_reminders(message: types.Message):
    user_id = message.from_user.id
    active = database.get_active_reminders(user_id)
    
    if not active:
        await message.answer(
            "📭 <b>У вас нет активных напоминаний.</b>\n\n"
            "Создайте новое с помощью:\n"
            "• Быстрой команды: <code>/remind Купить хлеб каждый день в 19:30</code>\n"
            "• Интерактивного меню: просто напишите <code>/remind</code>"
        )
        return

    response = ["📋 <b>Ваши активные напоминания:</b>\n"]
    builder = InlineKeyboardBuilder()
    
    for idx, item in enumerate(active, 1):
        interval = item.get('interval', 'once')
        t_str = get_time_string_from_ts(item['remind_at'])
        
        if interval == "daily":
            sched_label = f"🔁 каждый день в {t_str}"
        elif interval == "weekly":
            dt = datetime.fromtimestamp(item['remind_at'], tz=timezone.utc).astimezone(MSK_TZ)
            weekday_name = WEEKDAYS_SHORT[dt.weekday()]
            sched_label = f"📅 по {weekday_name} в {t_str}"
        else:
            sched_label = f"⏰ {format_timestamp(item['remind_at'])}"
            
        if item['text'] == '__compliment__':
            short_text = "🌸 Ежедневный комплимент"
        else:
            short_text = item['text'][:30] + "..." if len(item['text']) > 30 else item['text']
        response.append(f"{idx}️⃣ <b>{short_text}</b>\n    └ {sched_label}\n")
        builder.button(text=f"❌ Удалить #{idx}", callback_data=f"del_remind:{item['id']}")
    
    builder.adjust(2)
    
    await message.answer("\n".join(response), reply_markup=builder.as_markup())


# --- Delete Reminder Callback ---
@router.callback_query(F.data.startswith("del_remind:"))
async def process_delete_reminder(callback_query: types.CallbackQuery):
    reminder_id = int(callback_query.data.split(":")[1])
    user_id = callback_query.from_user.id
    
    deleted = database.delete_reminder(reminder_id, user_id)
    
    if deleted:
        await callback_query.answer("Напоминание удалено!")
        active = database.get_active_reminders(user_id)
        if not active:
            await callback_query.message.edit_text("📭 <b>Все напоминания удалены.</b>")
            return
            
        response = ["📋 <b>Ваши активные напоминания:</b>\n"]
        builder = InlineKeyboardBuilder()
        for idx, item in enumerate(active, 1):
            interval = item.get('interval', 'once')
            t_str = get_time_string_from_ts(item['remind_at'])
            
            if interval == "daily":
                sched_label = f"🔁 каждый день в {t_str}"
            elif interval == "weekly":
                dt = datetime.fromtimestamp(item['remind_at'], tz=timezone.utc).astimezone(MSK_TZ)
                weekday_name = WEEKDAYS_SHORT[dt.weekday()]
                sched_label = f"📅 по {weekday_name} в {t_str}"
            else:
                sched_label = f"⏰ {format_timestamp(item['remind_at'])}"
                
            if item['text'] == '__compliment__':
                short_text = "🌸 Ежедневный комплимент"
            else:
                short_text = item['text'][:30] + "..." if len(item['text']) > 30 else item['text']
            response.append(f"{idx}️⃣ <b>{short_text}</b>\n    └ {sched_label}\n")
            builder.button(text=f"❌ Удалить #{idx}", callback_data=f"del_remind:{item['id']}")
        
        builder.adjust(2)
        await callback_query.message.edit_text("\n".join(response), reply_markup=builder.as_markup())
    else:
        await callback_query.answer("Ошибка: Напоминание не найдено.", show_alert=True)


# --- Reminder Done callback (Yes Button) ---
@router.callback_query(F.data.startswith("remind_done:"))
async def process_remind_done(callback_query: types.CallbackQuery):
    reminder_id = int(callback_query.data.split(":")[1])
    reminder = database.get_reminder(reminder_id)
    
    text = reminder['text'] if reminder else "ваша задача"
    name = reminder['user_first_name'] if reminder else callback_query.from_user.first_name
    
    message_text = (
        f"✅ <b>Напоминание выполнено!</b>\n\n"
        f"<blockquote>✍️ <b>Задача:</b>\n"
        f"<b>{text}</b></blockquote>\n"
        f"<i>Отлично, {name}! Умница, задача выполнена! 🎉</i>"
    )
    
    await callback_query.message.edit_text(message_text, reply_markup=None)
    await callback_query.answer("Поздравляю с выполнением! 🎉")


# --- Reminder Undone callback (No Button) ---
@router.callback_query(F.data.startswith("remind_undone:"))
async def process_remind_undone(callback_query: types.CallbackQuery):
    reminder_id = int(callback_query.data.split(":")[1])
    reminder = database.get_reminder(reminder_id)
    
    text = reminder['text'] if reminder else "ваша задача"
    name = reminder['user_first_name'] if reminder else callback_query.from_user.first_name
    
    message_text = (
        f"❌ <b>Напоминание не выполнено</b>\n\n"
        f"<blockquote>✍️ <b>Задача:</b>\n"
        f"<b>{text}</b></blockquote>\n"
        f"<i>Ничего страшного, {name}! Хотите отложить его?</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏱️ На 15 минут", callback_data=f"snooze:15m:{reminder_id}")
    builder.button(text="⏱️ На 1 час", callback_data=f"snooze:1h:{reminder_id}")
    builder.button(text="❌ Закрыть", callback_data=f"snooze:close:{reminder_id}")
    builder.adjust(2, 1)
    
    await callback_query.message.edit_text(message_text, reply_markup=builder.as_markup())
    await callback_query.answer()


# --- Snooze callback ---
@router.callback_query(F.data.startswith("snooze:"))
async def process_snooze(callback_query: types.CallbackQuery):
    parts = callback_query.data.split(":")
    action = parts[1]
    reminder_id = int(parts[2])
    
    reminder = database.get_reminder(reminder_id)
    if not reminder:
        await callback_query.answer("Ошибка: Напоминание не найдено.", show_alert=True)
        return
        
    text = reminder['text']
    name = reminder['user_first_name']
    
    if action == "close":
        message_text = (
            f"❌ <b>Напоминание не выполнено</b>\n\n"
            f"<blockquote>✍️ <b>Задача:</b>\n"
            f"<b>{text}</b></blockquote>\n"
            f"<i>Хорошо, {name}. Задача закрыта без выполнения.</i>"
        )
        await callback_query.message.edit_text(message_text, reply_markup=None)
        await callback_query.answer("Задача закрыта.")
        return
        
    # Handle actual snooze (15m or 1h)
    offset_seconds = 900 if action == "15m" else 3600
    remind_at = int(time.time() + offset_seconds)
    
    # If the original reminder is recurring, we do NOT change it (it's already rescheduled for next run)
    # Instead, we add a new one-time reminder
    if reminder['interval'] in ("daily", "weekly"):
        database.add_reminder(
            user_id=reminder['user_id'],
            chat_id=reminder['chat_id'],
            text=text,
            remind_at=remind_at,
            interval="once",
            user_first_name=name
        )
    else:
        # If it was a one-time reminder, we just update it and set is_sent = 0 to trigger it again
        database.update_next_run(reminder_id, remind_at)
        
    readable_time = format_timestamp(remind_at)
    message_text = (
        f"⏱️ <b>Напоминание отложено</b>\n\n"
        f"<blockquote>✍️ <b>Задача:</b>\n"
        f"<b>{text}</b></blockquote>\n"
        f"<i>Хорошо, {name}. Я напомню еще раз {readable_time} (по МСК).</i>"
    )
    
    await callback_query.message.edit_text(message_text, reply_markup=None)
    await callback_query.answer(f"Отложено на 15 минут" if action == "15m" else "Отложено на 1 час")


# --- Daily Compliment Subscription ---
@router.message(Command("compliment", "love"))
async def cmd_compliment(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    first_name = message.from_user.first_name
    
    # Check if there is an argument (time)
    args = message.text.replace("/compliment", "").replace("/love", "").strip()
    
    time_str = "10:00"  # default time
    if args:
        parsed_time = parse_absolute_time(args)
        if parsed_time:
            time_str = parsed_time
        else:
            await message.answer(
                "⚠️ <b>Некорректный формат времени!</b>\n\n"
                "Пришлите время в формате <code>ЧЧ:ММ</code> (например: <code>/compliment 09:30</code>)."
            )
            return
            
    # Calculate next occurrence of this time
    remind_at = get_next_daily_timestamp(time_str)
    if not remind_at:
        await message.answer("⚠️ Не удалось рассчитать время. Попробуйте еще раз.")
        return
        
    # Delete any existing compliment subscriptions for this user in this chat
    active = database.get_active_reminders(user_id)
    deleted_any = False
    for item in active:
        if item['text'] == '__compliment__' and item['chat_id'] == chat_id:
            database.delete_reminder(item['id'], user_id)
            deleted_any = True
            
    # Add new subscription
    database.add_reminder(
        user_id=user_id,
        chat_id=chat_id,
        text="__compliment__",
        remind_at=remind_at,
        interval="daily",
        user_first_name=first_name
    )
    
    readable_time = format_timestamp(remind_at)
    
    if deleted_any:
        await message.answer(
            f"🔄 <b>Время подписки изменено!</b>\n\n"
            f"Теперь бот будет присылать вам милые комплименты каждый день в <b>{time_str}</b> (по МСК).\n"
            f"🔔 <i>Первый комплимент придёт: {readable_time}.</i>"
        )
    else:
        await message.answer(
            f"🌸 <b>Вы успешно подписались на ежедневные комплименты!</b>\n\n"
            f"Бот будет присылать вам милые слова каждый день в <b>{time_str}</b> (по МСК).\n"
            f"🔔 <i>Первый комплимент придёт: {readable_time}.</i>\n\n"
            f"💡 <i>Отписаться можно в любой момент через /list.</i>"
        )

# --- Handle Uploaded Compliment Photos ---
@router.message(F.photo)
async def process_uploaded_photo(message: types.Message, state: FSMContext):
    # Check if the user is currently in FSM wizard to avoid intercepting wizard flow
    curr_state = await state.get_state()
    if curr_state is not None:
        return

    # Telegram photos come in multiple sizes, the last one is the largest/highest resolution
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Save it to the database
    database.add_compliment_photo(message.from_user.id, file_id)
    
    await message.reply(
        "🌸 <b>Милая пичка успешно сохранена!</b>\n\n"
        "Я добавил эту картинку в вашу коллекцию. Теперь она будет случайно выбираться и присылаться вместе с ежедневными комплиментами!\n\n"
        "💡 <i>Отправить ещё одну? Просто пришлите следующее фото!</i>\n"
        "💡 <i>Очистить всю коллекцию сохраненных фото можно командой:</i> /clear_photos"
    )

@router.message(Command("clear_photos"))
async def cmd_clear_photos(message: types.Message):
    user_id = message.from_user.id
    count = database.delete_all_compliment_photos(user_id)
    
    if count > 0:
        await message.answer(
            f"🧹 <b>Коллекция картинок очищена!</b>\n\n"
            f"Успешно удалено картинок: <b>{count}</b>. Теперь при отправке комплиментов бот будет использовать стандартные картинки."
        )
    else:
        await message.answer("🤷‍♂️ <b>Ваша коллекция картинок уже пуста.</b>")
