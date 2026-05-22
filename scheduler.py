import asyncio
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database
import compliments

logger = logging.getLogger(__name__)

async def check_reminders_loop(bot: Bot):
    """Background loop that periodically checks database for due reminders, sends them
    with personal greetings and interactive Yes/No inline feedback buttons.
    """
    logger.info("Reminders background scheduler started.")
    
    while True:
        try:
            # Fetch all unsent reminders that are due
            pending = database.get_pending_reminders()
            
            for reminder in pending:
                reminder_id = reminder['id']
                chat_id = reminder['chat_id']
                user_id = reminder['user_id']
                text = reminder['text']
                interval = reminder.get('interval', 'once')
                user_first_name = reminder.get('user_first_name', 'Мария')
                
                logger.info(f"Processing due reminder #{reminder_id} ({interval}) for chat {chat_id}")
                
                # Check if it is a compliment subscription
                sent_successfully = False
                if text == "__compliment__":
                    message_text = compliments.get_random_compliment(user_first_name)
                    try:
                        # 1. Check if the user has uploaded their own custom photos
                        custom_photos = database.get_compliment_photos(user_id)
                        if custom_photos:
                            import random
                            selected_photo = random.choice(custom_photos)
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=selected_photo,
                                caption=message_text
                            )
                            logger.info(f"Compliment sent as custom user photo (file_id) to chat {chat_id}")
                        else:
                            # 2. Fetch image from public TG channels/APIs as fallback
                            photo_file = await compliments.get_pinterest_image()
                            if photo_file:
                                await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=photo_file,
                                    caption=message_text
                                )
                                logger.info(f"Compliment sent as scraped photo to chat {chat_id}")
                            else:
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=message_text
                                )
                                logger.info(f"Compliment sent as text (no photo fetched) to chat {chat_id}")
                        sent_successfully = True
                    except Exception as photo_err:
                        logger.error(f"Failed to send compliment photo/text: {photo_err}, sending text only.")
                        try:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=message_text
                            )
                            sent_successfully = True
                        except TelegramAPIError as e:
                            logger.error(f"Telegram API error when sending text-only compliment: {e}")
                            if "forbidden" in str(e).lower() or "chat not found" in str(e).lower():
                                database.delete_reminder(reminder_id, user_id)
                else:
                    # Format a beautiful HTML notification message
                    interval_label = ""
                    if interval == "daily":
                        interval_label = " 🔁 <i>(Ежедневное)</i>"
                    elif interval == "weekly":
                        interval_label = " 📅 <i>(Еженедельное)</i>"
                    
                    message_text = (
                        f"⏰ <b>{user_first_name}, пришло время!{interval_label}</b> 🔔\n\n"
                        f"<blockquote>✍️ Вы просили напомнить:\n"
                        f"<b>{text}</b></blockquote>\n"
                        "<i>Вы выполнили эту задачу?</i>"
                    )
                    
                    # Create Yes / No feedback keyboard
                    builder = InlineKeyboardBuilder()
                    builder.button(text="✅ Да", callback_data=f"remind_done:{reminder_id}")
                    builder.button(text="❌ Нет", callback_data=f"remind_undone:{reminder_id}")
                    builder.adjust(2)
                    
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=message_text,
                            reply_markup=builder.as_markup()
                        )
                        sent_successfully = True
                    except TelegramAPIError as e:
                        logger.error(f"Telegram API error when sending reminder #{reminder_id}: {e}")
                        if "forbidden" in str(e).lower() or "chat not found" in str(e).lower():
                            database.delete_reminder(reminder_id, user_id)
                
                # Update status based on interval
                if sent_successfully:
                    if interval == "daily":
                        # Reschedule for tomorrow (+24 hours)
                        next_run = reminder['remind_at'] + 86400
                        database.update_next_run(reminder_id, next_run)
                        logger.info(f"Daily reminder #{reminder_id} rescheduled to timestamp {next_run}.")
                    elif interval == "weekly":
                        # Reschedule for next week (+7 days)
                        next_run = reminder['remind_at'] + 604800
                        database.update_next_run(reminder_id, next_run)
                        logger.info(f"Weekly reminder #{reminder_id} rescheduled to timestamp {next_run}.")
                    else:
                        # One-time reminder: mark as sent
                        database.mark_as_sent(reminder_id)
                        logger.info(f"One-time reminder #{reminder_id} marked as completed.")
                        
        except Exception as e:
            logger.error(f"Error in reminders scheduler loop: {e}", exc_info=True)
            
        # Check every 10 seconds for new reminders
        await asyncio.sleep(10)

async def check_daily_routines_loop(bot: Bot):
    """Background loop that checks for daily weather and mood prompts."""
    from datetime import datetime
    import config
    from handlers import weather, mood
    
    logger.info("Daily routines scheduler started.")
    
    while True:
        try:
            now = datetime.now(config.BOT_TZ)
            current_time_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")
            
            settings = database.get_all_user_settings()
            for s in settings:
                user_id = s['user_id']
                
                # Check weather
                weather_time = s.get('weather_time')
                last_w_date = s.get('last_weather_date')
                if weather_time and last_w_date != today_str and weather_time <= current_time_str:
                    logger.info(f"Sending daily weather to {user_id} (scheduled for {weather_time})")
                    # Fetch coordinates
                    lat = s.get('latitude')
                    lon = s.get('longitude')
                    city = s.get('city') or weather.DEFAULT_CITY
                    if lat is None or lon is None:
                        lat, lon = weather.DEFAULT_LAT, weather.DEFAULT_LON
                        
                    w_data = await weather.get_weather_forecast(lat, lon)
                    msg = weather.format_weather_message(w_data, city)
                    try:
                        await bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
                        database.set_user_setting(user_id, 'last_weather_date', today_str)
                        logger.info(f"Daily weather sent successfully to {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send weather to {user_id}: {e}")
                
                # Check mood
                mood_time = s.get('mood_time')
                last_m_date = s.get('last_mood_date')
                if mood_time and last_m_date != today_str and mood_time <= current_time_str:
                    logger.info(f"Sending daily mood prompt to {user_id} (scheduled for {mood_time})")
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text="Как прошел твой день? Поделись настроением:",
                            reply_markup=mood.get_mood_keyboard()
                        )
                        database.set_user_setting(user_id, 'last_mood_date', today_str)
                        logger.info(f"Daily mood prompt sent successfully to {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send mood prompt to {user_id}: {e}")
                            
        except Exception as e:
            logger.error(f"Error in daily routines loop: {e}", exc_info=True)
            
        # Check every 30 seconds
        await asyncio.sleep(30)

