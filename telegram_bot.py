import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")

# Логирование
logging.basicConfig(level=logging.INFO)

# Бот и диспетчер с памятью для FSM
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# --- Состояния ---
class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_onlyfans = State()


# --- Клавиатуры ---
btn_conditions = KeyboardButton("⭐Мне подходят условия⭐")
keyboard_conditions = ReplyKeyboardMarkup(resize_keyboard=True).add(btn_conditions)

btn_yes = KeyboardButton("Да")
btn_no = KeyboardButton("Нет")
keyboard_yes_no = ReplyKeyboardMarkup(resize_keyboard=True).add(btn_yes, btn_no)


# --- Хендлеры ---
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    # Первое приветствие с картинкой
    if os.path.exists("welcome.jpg"):
        with open("welcome.jpg", "rb") as photo:
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=photo,
                caption=(
                    "Добро пожаловать на обучение *Eclipse Agency!* 🌑\n\n"
                    "Я буду твоим личным гидом в освоении роли *оператора* — сотрудника, "
                    "который умеет выстраивать связь, удерживать внимание и превращать диалог в результат.\n\n"
                    "А теперь стартовые условия:\n\n"
                    "💰 20% от всех продаж\n"
                    "🕗 Гибкий 8-часовой график\n"
                    "📆 1 выходной в неделю\n"
                    "💸 Выплаты — 7 и 22 числа (USDT)\n"
                    "⚠️ Комиссия за конвертацию (~5%) не покрывается агентством"
                ),
                parse_mode="Markdown"
            )
    else:
        await message.answer("Добро пожаловать на обучение Eclipse Agency! 🌑")

    # Второе сообщение с условиями и кнопкой
    await bot.send_message(
        chat_id=message.chat.id,
        text=(
            "Почему именно такие стартовые условия?\n\n"
            "📈 Повышение процента — до 23% при выполнении KPI\n"
            "👥 Роль Team Lead — +1% от заработка команды (3 человека)\n"
            "🎯 Бонусы за достижения — выплаты за стабильность и инициативу\n"
            "🚀 Карьерный рост — от оператора до администратора\n\n"
            "Нажми кнопку ниже, если тебе подходят условия 👇"
        ),
        reply_markup=keyboard_conditions
    )


@dp.message_handler(lambda message: message.text == "⭐Мне подходят условия⭐")
async def agree_conditions(message: types.Message):
    await message.answer(
        "❗️Обрати внимание: Условие ниже не распространяется на стажировочный период (7 дней)!\n\n"
        "— Если ты решишь завершить сотрудничество, потребуется отработать не более 7 дней "
        "с момента уведомления администратора.\n\n"
        "Теперь давай начнём с простого — как тебя зовут?",
        reply_markup=ReplyKeyboardRemove()
    )
    await Form.waiting_for_name.set()


@dp.message_handler(state=Form.waiting_for_name)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    await message.answer(
        f"Красивое имя, {name}! 🌟\n\n"
        f"{name}, ты знаком(-а) с работой на OnlyFans?",
        reply_markup=keyboard_yes_no
    )
    await Form.waiting_for_onlyfans.set()


@dp.message_handler(state=Form.waiting_for_onlyfans)
async def onlyfans_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")

    if message.text == "Да":
        await message.answer(f"Отлично, {name}! Тогда двигаться дальше будет проще ✅")
    elif message.text == "Нет":
        await message.answer(f"Ничего страшного, {name}, я всё объясню с нуля 😉")
    else:
        await message.answer("Пожалуйста, выбери: Да или Нет", reply_markup=keyboard_yes_no)
        return

    # очищаем состояние (можно оставить, если дальше будет новое состояние)
    await state.finish()


# --- Запуск ---
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
