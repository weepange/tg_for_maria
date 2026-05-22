from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.full_name}! 🌟\n\n"
        "Я бот-напоминалка. Я могу присылать вам уведомления "
        "как один раз, так и регулярно (каждый день или раз в неделю).\n\n"
        "📖 Чтобы посмотреть список команд, введите /help\n"
        "⏰ Чтобы создать напоминание, введите /remind"
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "📋 <b>ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ БОТА</b>\n\n"
        "<b>Доступные команды:</b>\n"
        "• /start — Приветствие и начало работы\n"
        "• /help — Показать это справочное сообщение\n"
        "• /remind — Создать напоминание (через пошаговый мастер или быстрой командой)\n"
        "• /list — Посмотреть ваши активные напоминания и удалить их\n"
        "• /roll — Выбрать, кто моет посуду (честный жребий)\n"
        "• /compliment — Подписаться на ежедневные милые комплименты\n"
        "• /tz — Показать текущее время и часовой пояс бота\n\n"
        
        "⚠️ <b>Важные правила установки времени:</b>\n"
        "• Если вы указываете точное время (например, <code>17:40</code>), ставьте его хотя бы на <b>2–3 минуты вперед</b> от текущего времени бота.\n"
        "• Если указать время, которое <b>уже прошло</b> сегодня (или до него осталось меньше минуты), бот автоматически запланирует напоминание на **завтра**, чтобы вы его не пропустили.\n"
        "• Сверить текущие часы бота можно с помощью команды /tz.\n\n"
        
        "📝 <b>Примеры быстрого создания напоминаний:</b>\n"
        "💡 <code>/remind Проверить духовку 15м</code> (напомнить через 15 минут)\n"
        "💡 <code>/remind Позвонить маме в 19:30</code> (сегодня, если время еще не прошло)\n"
        "💡 <code>/remind Пить воду каждый день в 09:00</code> (ежедневное напоминание)\n"
        "💡 <code>/remind Полить цветы каждую пятницу в 18:00</code> (еженедельное напоминание)\n\n"
        
        "🎲 <b>Жребий посуды (/roll):</b>\n"
        "💡 <code>/roll Мария Александр</code> (сделать жребий и запомнить имена)\n"
        "💡 <code>/roll</code> (запустить повторный жребий с сохраненными именами)\n\n"
        
        "🌸 <b>Ежедневные комплименты:</b>\n"
        "💡 <code>/compliment</code> (подписка на комплименты каждый день в 10:00)\n"
        "💡 <code>/compliment 18:30</code> (подписка на комплименты в указанное время)"
    )
    await message.answer(help_text)

from config import BOT_TZ
import datetime

@router.message(Command("tz"))
async def cmd_tz(message: types.Message):
    from handlers.reminders import MSK_TZ
    now_naive = datetime.datetime.now()
    now_tz = datetime.datetime.now(BOT_TZ)
    await message.answer(
        f"ℹ️ <b>Диагностика часового пояса бота:</b>\n\n"
        f"• <code>BOT_TZ</code>: {BOT_TZ} ({type(BOT_TZ).__name__})\n"
        f"• <code>MSK_TZ</code>: {MSK_TZ} ({type(MSK_TZ).__name__})\n"
        f"• Локальное время (без TZ): {now_naive.strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"• Локальное время (с BOT_TZ): {now_tz.strftime('%d.%m.%Y %H:%M:%S %Z')}"
    )
