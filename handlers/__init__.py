from aiogram import Dispatcher
from . import common, reminders, roll, echo

def register_handlers(dp: Dispatcher):
    # Register common commands first
    dp.include_router(common.router)
    # Register reminders router
    dp.include_router(reminders.router)
    # Register roll router
    dp.include_router(roll.router)
    # Register the catch-all echo router last
    dp.include_router(echo.router)
