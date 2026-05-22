import random
from aiogram import Router, types
from aiogram.filters import Command

import database

router = Router()

@router.message(Command("roll"))
async def cmd_roll(message: types.Message):
    chat_id = message.chat.id
    
    # Parse arguments, support both space and comma separators
    raw_text = message.text.replace("/roll", "", 1).replace(",", " ").strip()
    
    if raw_text:
        # User provided list of participants
        participants = [p.strip() for p in raw_text.split() if p.strip()]
        # Save this list to the database for this chat
        database.save_dish_roll_settings(chat_id, ",".join(participants))
    else:
        # User ran empty /roll, load last used list of participants
        settings = database.get_dish_roll_settings(chat_id)
        if settings and settings.get('participants'):
            participants = [p.strip() for p in settings['participants'].split(",") if p.strip()]
        else:
            await message.answer(
                "⚠️ <b>Укажите участников ролла через пробел!</b>\n\n"
                "Например: <code>/roll Мария Александр</code>\n\n"
                "<i>Я запомню участников, и в следующий раз вам достаточно будет просто написать <code>/roll</code>.</i>"
            )
            return

    # Validation: must have at least 2 participants
    if len(participants) < 2:
        await message.answer(
            "⚠️ <b>Для выбора нужно как минимум 2 участника!</b>\n"
            "Пример: <code>/roll Мария Александр</code>"
        )
        return

    # Load history
    settings = database.get_dish_roll_settings(chat_id)
    last_rolled = settings.get('last_rolled') if settings else None
    prev_rolled = settings.get('prev_rolled') if settings else None
    
    # Calculate weights based on history to ensure fairness (anti-consecutive repetition)
    weights = []
    last_lower = last_rolled.lower() if last_rolled else None
    prev_lower = prev_rolled.lower() if prev_rolled else None
    
    for p in participants:
        p_lower = p.lower()
        if len(participants) == 2:
            # For 2 participants, give the last winner a 20% weight, other gets 100% (83% vs 17% probability)
            # This makes alternation highly likely, but still leaves a small chance of surprise.
            if p_lower == last_lower:
                weights.append(0.2)
            else:
                weights.append(1.0)
        else:
            # For 3+ participants, give last winner 5% weight (virtually zero), 
            # second last gets 30% weight, everyone else gets 100% weight.
            if p_lower == last_lower:
                weights.append(0.05)
            elif p_lower == prev_lower:
                weights.append(0.3)
            else:
                weights.append(1.0)

    # Perform weighted random choice
    winner = random.choices(participants, weights=weights)[0]
    
    # Save new history: winner becomes last_rolled, previous last_rolled becomes prev_rolled
    database.save_dish_roll_settings(
        chat_id=chat_id,
        participants=",".join(participants),
        last_rolled=winner,
        prev_rolled=last_rolled
    )
    
    # Format the participants with their calculated probabilities
    total_weight = sum(weights)
    chances_list = []
    
    for p, w in zip(participants, weights):
        chance_percent = int((w / total_weight) * 100)
        p_lower = p.lower()
        
        status_note = ""
        if p_lower == last_lower:
            status_note = " 🧽 <i>(мыл(а) прошлый раз)</i>"
        elif p_lower == prev_lower and len(participants) >= 3:
            status_note = " 🧼 <i>(мыл(а) позапрошлый раз)</i>"
            
        chances_list.append(f"• <b>{p}</b> — {chance_percent}% шанс{status_note}")
        
    chances_text = "\n".join(chances_list)
    
    message_text = (
        f"🎲 <b>ЖРЕБИЙ ЧИСТОТЫ: КТО МОЕТ ПОСУДУ?</b> 🧽\n\n"
        f"👥 <b>Участники и шансы:</b>\n"
        f"{chances_text}\n\n"
        f"⚡ <i>Барабан крутится, тарелки блестят...</i>\n\n"
        f"🎉 <b>Сегодня посуду моет: {winner}!</b> 🧼\n\n"
        f"<i>Чистая посуда — залог крепкой любви! Желаем легкой мойки! 💪</i>"
    )
    
    await message.answer(message_text)
