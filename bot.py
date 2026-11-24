"""Eclipse recruitment questionnaire (Ukrainian), aiogram 3.x."""
import asyncio
import html
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove


def load_env(path: Path = Path(__file__).with_name('.env')) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '').strip()
WELCOME_IMAGE = Path(__file__).with_name('welcome.jpg')
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
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label in labels], resize_keyboard=True
    )


SHIFT_OPTIONS = ('06:00–14:00', '14:00–22:00', '22:00–06:00')
YES_18, NO_18 = '✅ Так', '❌ Ні'
YES_EXPERIENCE, NO_EXPERIENCE = '✅ Так, є досвід', '🌱 Ні, я новачок'
YES_TRAINING, NO_TRAINING = '✅ Так, готовий(-а)', '⏳ Поки що ні'
SKIP_PHONE = 'Продовжити без номера'


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Application.name)
    greeting = (
        '💗 <b>Вітаємо в Eclipse!</b>\n\n'
        'Раді, що тебе зацікавила наша вакансія перекладача. '
        'Заповни невелику анкету — і наш адміністратор зможе з тобою зв’язатися. ✨'
    )
    if WELCOME_IMAGE.exists():
        try:
            await message.answer_photo(FSInputFile(WELCOME_IMAGE), caption=greeting, parse_mode='HTML')
        except Exception:
            logging.exception('Не вдалося надіслати вітальне зображення')
            await message.answer(greeting, parse_mode='HTML')
    else:
        await message.answer(greeting, parse_mode='HTML')
    await message.answer('<b>1. 👤 Як тебе звати?</b>', parse_mode='HTML', reply_markup=ReplyKeyboardRemove())


@router.message(Command('cancel'))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer('Анкету скасовано. Щоб почати знову, натисни /start.', reply_markup=ReplyKeyboardRemove())


@router.message(Application.name, F.text)
async def name(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not 2 <= len(value) <= 100:
        await message.answer('Будь ласка, вкажи ім’я (від 2 до 100 символів).')
        return
    await state.update_data(name=value)
    await state.set_state(Application.adult)
    await message.answer('<b>2. 🎂 Тобі вже виповнилося 18 років?</b>', reply_markup=options(YES_18, NO_18), parse_mode='HTML')


@router.message(Application.adult, F.text)
async def adult(message: Message, state: FSMContext) -> None:
    if message.text not in (YES_18, NO_18):
        await message.answer('Обери відповідь за допомогою кнопки нижче 👇')
        return
    if message.text == NO_18:
        await state.clear()
        await message.answer('💗 Дякуємо за інтерес до Eclipse! Зараз ми розглядаємо кандидатів віком від 18 років.', reply_markup=ReplyKeyboardRemove())
        return
    await state.update_data(adult='Так')
    await state.set_state(Application.experience)
    await message.answer('<b>3. 💼 Чи маєш досвід роботи в шлюбному агентстві?</b>', reply_markup=options(YES_EXPERIENCE, NO_EXPERIENCE), parse_mode='HTML')


@router.message(Application.experience, F.text)
async def experience(message: Message, state: FSMContext) -> None:
    if message.text not in (YES_EXPERIENCE, NO_EXPERIENCE):
        await message.answer('Обери один із варіантів нижче 👇')
        return
    await state.update_data(experience='Так' if message.text == YES_EXPERIENCE else 'Ні')
    if message.text == YES_EXPERIENCE:
        await state.set_state(Application.experience_details)
        await message.answer(
            '<b>4. 🏢 У якому агентстві та на якій платформі ти працював(-ла)? Як довго?</b>\n\n'
            '<i>Можна відповісти одним повідомленням.</i>',
            reply_markup=ReplyKeyboardRemove(), parse_mode='HTML'
        )
    else:
        await state.update_data(experience_details='Без досвіду')
        await ask_shift(message, state)


@router.message(Application.experience_details, F.text)
async def experience_details(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not value:
        await message.answer('Вкажи, будь ласка, агентство, платформу та тривалість роботи.')
        return
    await state.update_data(experience_details=value[:1000])
    await ask_shift(message, state)


async def ask_shift(message: Message, state: FSMContext) -> None:
    await state.set_state(Application.shift)
    number = '5.' if (await state.get_data()).get('experience') == 'Так' else '4.'
    await message.answer(f'<b>{number} 🕒 Яку зміну тобі зручніше працювати?</b>\n\nОбери графік нижче 👇', reply_markup=options(*SHIFT_OPTIONS), parse_mode='HTML')


@router.message(Application.shift, F.text)
async def shift(message: Message, state: FSMContext) -> None:
    if message.text not in SHIFT_OPTIONS:
        await message.answer('Будь ласка, обери зміну за допомогою кнопки.')
        return
    await state.update_data(shift=message.text)
    await state.set_state(Application.salary)
    number = '6.' if (await state.get_data()).get('experience') == 'Так' else '5.'
    await message.answer(f'<b>{number} 💰 На яку заробітну плату на місяць ти розраховуєш?</b>\n\n<i>Наприклад: 500 USD.</i>', reply_markup=ReplyKeyboardRemove(), parse_mode='HTML')


@router.message(Application.salary, F.text)
async def salary(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not value:
        await message.answer('Вкажи, будь ласка, очікувану зарплату.')
        return
    await state.update_data(salary=value[:200])
    await state.set_state(Application.training)
    number = '7.' if (await state.get_data()).get('experience') == 'Так' else '6.'
    await message.answer(f'<b>{number} 📚 Чи готовий(-а) ти розпочати навчання?</b>', reply_markup=options(YES_TRAINING, NO_TRAINING), parse_mode='HTML')


@router.message(Application.training, F.text)
async def training(message: Message, state: FSMContext) -> None:
    if message.text not in (YES_TRAINING, NO_TRAINING):
        await message.answer('Обери один із варіантів нижче 👇')
        return
    await state.update_data(training='Так' if message.text == YES_TRAINING else 'Поки що ні')
    await state.set_state(Application.contact)
    contact_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='📱 Поділитися номером', request_contact=True)],
            [KeyboardButton(text=SKIP_PHONE)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    number = '8.' if (await state.get_data()).get('experience') == 'Так' else '7.'
    await message.answer(
        f'<b>{number} 📲 Останній крок — контактні дані</b>\n\n'
        'Можеш поділитися номером телефону або продовжити без нього. '
        'Ми спробуємо зв’язатися з тобою через Telegram.\n\n'
        '<i>Номер телефону отримає лише адміністратор для зв’язку щодо вакансії.</i>',
        reply_markup=contact_keyboard,
        parse_mode='HTML',
    )


@router.message(Application.contact)
async def contact(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.contact:
        if message.contact.user_id != message.from_user.id:
            await message.answer('Поділися, будь ласка, власним номером або продовжуй без нього.')
            return
        phone = message.contact.phone_number
    elif message.text == SKIP_PHONE:
        phone = 'Не вказано'
    else:
        await message.answer('Натисни «Поділитися номером» або «Продовжити без номера».')
        return

    data = await state.get_data()
    user = message.from_user
    esc = lambda value: html.escape(str(value), quote=False)
    username = f'@{user.username}' if user.username else 'Не вказано'
    applicant_link = f'<a href="tg://user?id={user.id}">{esc(user.full_name)}</a>'
    report = (
        '💌 <b>ECLIPSE | НОВА АНКЕТА КАНДИДАТА</b>\n━━━━━━━━━━━━\n\n'
        f'👤 <b>Ім’я:</b> {esc(data["name"])}\n'
        '🔞 <b>18+:</b> Так\n'
        f'💼 <b>Досвід:</b> {esc(data["experience"])}\n'
        f'🏢 <b>Агентство / платформа / стаж:</b> {esc(data["experience_details"])}\n'
        f'🕒 <b>Бажана зміна:</b> {esc(data["shift"])}\n'
        f'💰 <b>Очікувана зарплата:</b> {esc(data["salary"])}\n'
        f'📚 <b>Готовність до навчання:</b> {esc(data["training"])}\n\n'
        f'📱 <b>Телефон:</b> {esc(phone)}\n'
        f'💬 <b>Telegram:</b> {esc(username)}\n'
        f'🔗 <b>Профіль:</b> {applicant_link}\n'
        f'🆔 <b>Telegram ID:</b> <code>{user.id}</code>'
    )
    try:
        await bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=report, parse_mode='HTML')
    except Exception:
        logging.exception('Не вдалося надіслати анкету адміністратору')
        await message.answer('Не вдалося надіслати анкету. Спробуй ще раз або звернися до адміністратора.', reply_markup=options(SKIP_PHONE))
        return
    await state.clear()
    await message.answer(
        '🎉 <b>Дякуємо! Анкету надіслано.</b>\n\n'
        'Наш адміністратор ознайомиться з твоїми відповідями й зв’яжеться з тобою в Telegram. 💗\n\n'
        '✨ <i>До зв’язку! Команда Eclipse</i>',
        parse_mode='HTML', reply_markup=ReplyKeyboardRemove()
    )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer('Щоб заповнити анкету, натисни /start. Щоб скасувати — /cancel.')


async def main() -> None:
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        raise RuntimeError('Укажіть BOT_TOKEN та ADMIN_CHAT_ID у змінних середовища Render.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
