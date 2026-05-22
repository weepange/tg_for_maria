from aiogram import Router, types

router = Router()

@router.message()
async def echo_all(message: types.Message):
    if message.text:
        await message.answer(f"Вы написали: {message.text}")
    else:
        await message.answer("Пока я умею повторять только текстовые сообщения.")
