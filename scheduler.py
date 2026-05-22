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
