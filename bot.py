"""Telegram recruitment questionnaire, aiogram 3.x.

Configure BOT_TOKEN and ADMIN_CHAT_ID via environment or .env file.
No external database: the current form is in memory; completed applications go to admin Telegram.
"""
import asyncio
import html
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)

# Read local .env without requiring python-dotenv.
def load_env(path: Path = Path(__file__).with_name('.env')) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, val = line.split('=', 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_env()
BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '').strip()

router = Router()

class Application(StatesGroup):
    name = State()
    adult = State()
    experience = State()
    experience_details = State()
    shift = State()
    salary = State()
    training = State()
    contact = State()


def options(*labels: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=v)] for v in labels], resize_keyboard=True)

SHIFT_OPTIONS = ('06:00–14:00', '14:00–22:00', '22:00–06:00')

@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Application.name)
    await message.answer('👋 Здравствуйте! Заполните короткую анкету кандидата.\n\n1/7. Как вас зовут?', reply_markup=ReplyKeyboardRemove())

@router.message(Command('cancel'))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Анкета отменена. Чтобы начать заново, нажмите /start.', reply_markup=ReplyKeyboardRemove())

@router.message(Application.name, F.text)
async def name(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not 2 <= len(value) <= 100:
        await message.answer('Пожалуйста, укажите имя (2–100 символов).')
        return
    await state.update_data(name=value)
    await state.set_state(Application.adult)
    await message.answer('2/7. Вам уже есть 18 лет?', reply_markup=options('Да', 'Нет'))

@router.message(Application.adult, F.text)
async def adult(message: Message, state: FSMContext) -> None:
    if message.text not in ('Да', 'Нет'):
        await message.answer('Выберите «Да» или «Нет» кнопкой.')
        return
    if message.text == 'Нет':
        await state.clear()
        await message.answer('Спасибо за интерес! На эту вакансию рассматриваем кандидатов от 18 лет.', reply_markup=ReplyKeyboardRemove())
        return
    await state.update_data(adult='Да')
    await state.set_state(Application.experience)
    await message.answer('3/7. Был ли у вас опыт работы?', reply_markup=options('Да', 'Нет'))

@router.message(Application.experience, F.text)
async def experience(message: Message, state: FSMContext) -> None:
    if message.text not in ('Да', 'Нет'):
        await message.answer('Выберите «Да» или «Нет» кнопкой.')
        return
    await state.update_data(experience=message.text)
    if message.text == 'Да':
        await state.set_state(Application.experience_details)
        await message.answer('В каком агентстве, на какой платформе и как долго работали?', reply_markup=ReplyKeyboardRemove())
    else:
        await state.update_data(experience_details='Нет опыта')
        await ask_shift(message, state)

@router.message(Application.experience_details, F.text)
async def experience_details(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer('Укажите агентство, платформу и стаж работы.')
        return
    await state.update_data(experience_details=text[:1000])
    await ask_shift(message, state)

async def ask_shift(message: Message, state: FSMContext) -> None:
    await state.set_state(Application.shift)
    await message.answer('4/7. Какую смену выбираете?', reply_markup=options(*SHIFT_OPTIONS))

@router.message(Application.shift, F.text)
async def shift(message: Message, state: FSMContext) -> None:
    if message.text not in SHIFT_OPTIONS:
        await message.answer('Пожалуйста, выберите смену кнопкой.')
        return
    await state.update_data(shift=message.text)
    await state.set_state(Application.salary)
    await message.answer('5/7. Какую зарплату ожидаете? (Укажите сумму и валюту)', reply_markup=ReplyKeyboardRemove())

@router.message(Application.salary, F.text)
async def salary(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not value:
        await message.answer('Укажите ожидаемую зарплату.')
        return
    await state.update_data(salary=value[:200])
    await state.set_state(Application.training)
    await message.answer('6/7. Готовы приступить к обучению?', reply_markup=options('Да', 'Нет'))

@router.message(Application.training, F.text)
async def training(message: Message, state: FSMContext) -> None:
    if message.text not in ('Да', 'Нет'):
        await message.answer('Выберите «Да» или «Нет» кнопкой.')
        return
    await state.update_data(training=message.text)
    await state.set_state(Application.contact)
    contact_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='📱 Поделиться номером', request_contact=True)],
                  [KeyboardButton(text='Продолжить без номера')]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await message.answer('7/7. Оставьте контакт для связи. Можете поделиться номером телефона или продолжить с вашим Telegram-профилем.', reply_markup=contact_keyboard)

@router.message(Application.contact)
async def contact(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.contact:
        if message.contact.user_id != message.from_user.id:
            await message.answer('Пожалуйста, поделитесь своим номером или продолжите без него.')
            return
        phone = message.contact.phone_number
    elif message.text == 'Продолжить без номера':
        phone = 'Не указан'
    else:
        await message.answer('Натисніть кнопку для передачі свого номера або виберіть «Продолжить без номера».')
        return

    data = await state.get_data()
    user = message.from_user
    esc = lambda s: html.escape(str(s), quote=False)
    username = f'@{user.username}' if user.username else 'Немає username'
    applicant_link = f'<a href="tg://user?id={user.id}">{esc(user.full_name)}</a>'
    report = (
        '📋 <b>Новая анкета кандидата</b>\n\n'
        f'👤 <b>Имя:</b> {esc(data["name"])}\n'
        '🔞 <b>18+:</b> Да\n'
        f'💼 <b>Опыт:</b> {esc(data["experience"])}\n'
        f'🏢 <b>Агентство / платформа / стаж:</b> {esc(data["experience_details"])}\n'
        f'🕒 <b>Смена:</b> {esc(data["shift"])}\n'
        f'💰 <b>Желаемая зарплата:</b> {esc(data["salary"])}\n'
        f'📚 <b>Готовность к обучению:</b> {esc(data["training"])}\n\n'
        f'📞 <b>Телефон:</b> {esc(phone)}\n'
        f'💬 <b>Telegram:</b> {esc(username)}\n'
        f'🔗 <b>Профиль:</b> {applicant_link}\n'
        f'🆔 <b>Telegram ID:</b> <code>{user.id}</code>'
    )
    try:
        await bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=report, parse_mode='HTML')
    except Exception:
        logging.exception('Не удалось отправить анкету администратору')
        await message.answer('Не удалось отправить анкету. Попробуйте снова или сообщите администратору.', reply_markup=options('Продолжить без номера'))
        return
    await state.clear()
    await message.answer('✅ Спасибо! Ваша анкета отправлена. Ожидайте ответа администратора.', reply_markup=ReplyKeyboardRemove())

@router.message()
async def fallback(message: Message) -> None:
    await message.answer('Чтобы начать анкету, нажмите /start. Для отмены — /cancel.')

async def main() -> None:
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        raise RuntimeError('Укажите BOT_TOKEN и ADMIN_CHAT_ID в файле .env или переменных окружения.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
