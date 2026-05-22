import logging
import sys
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import config
import database
import scheduler
from handlers import register_handlers

# Configure logging to see bot activity in server logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

from aiogram.types import BotCommand

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Запуск и приветствие"),
        BotCommand(command="help", description="Справка по командам"),
        BotCommand(command="remind", description="Создать напоминание"),
        BotCommand(command="list", description="Показать список напоминаний"),
        BotCommand(command="roll", description="Кто моет посуду (честный выбор)"),
        BotCommand(command="compliment", description="Ежедневные комплименты"),
        BotCommand(command="clear_photos", description="Очистить коллекцию комплимент-картинок"),
    ]
    await bot.set_my_commands(commands)

async def on_startup(bot: Bot) -> None:
    # Initialize SQLite database
    database.init_db()
    
    # Start the reminders background loop
    asyncio.create_task(scheduler.check_reminders_loop(bot))
    

    # Set bot commands in Telegram menu
    await set_bot_commands(bot)

    # Register webhook url when the application starts
    if config.RUN_MODE == "webhook":
        if not config.WEBHOOK_URL:
            raise ValueError("WEBHOOK_HOST is not set in environment variables! Cannot set webhook.")
        
        # Check current webhook info first to avoid redundant API calls
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url != config.WEBHOOK_URL:
            logging.info(f"Setting webhook to: {config.WEBHOOK_URL}")
            await bot.set_webhook(
                url=config.WEBHOOK_URL,
                drop_pending_updates=True  # Clear old updates to avoid spam on start
            )
        else:
            logging.info(f"Webhook is already set to: {config.WEBHOOK_URL}")


def main():
    # Initialize Bot instance with default HTML formatting
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Initialize Dispatcher
    dp = Dispatcher()

    # Register all handlers (common commands and echo fallback)
    register_handlers(dp)

    # Register startup event
    dp.startup.register(on_startup)

    if config.RUN_MODE == "webhook":
        # Webhook Mode: Run web server listening to Telegram callback requests
        app = web.Application()

        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        )
        # Register the webhook path on the aiohttp web app
        webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)

        # Connect the dispatcher and bot lifecycle to the web app
        setup_application(app, dp, bot=bot)

        logging.info(f"Starting web server on http://{config.HOST}:{config.PORT}")
        web.run_app(app, host=config.HOST, port=config.PORT)
    else:
        # Polling Mode: Fetch updates directly from Telegram (for local development)
        async def run_polling():
            logging.info("Deleting webhook before starting polling...")
            await bot.delete_webhook(drop_pending_updates=True)
            logging.info("Starting bot in long polling (local) mode...")
            await dp.start_polling(bot)

        # Run the polling loop
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
