```python
import logging
import os
from pathlib import Path
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, InputFile, ParseMode
)
from dotenv import load_dotenv
from urllib.parse import urlparse

# --- Load environment ---
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # full public URL e.g. https://app.onrender.com/webhook/
PORT = int(os.getenv("PORT", "10000"))

if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL not set in .env — required for webhook mode (Render)")

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Init bot & dispatcher ---
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- Directories ---
IMAGES_DIR = Path("images")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


# --- States ---
class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_onlyfans = State()
    quiz_waiting_answer = State()


# --- Helper for inline keyboards ---
def make_kb(*rows):
    kb = InlineKeyboardMarkup(row_width=2)
    for row in rows:
        buttons = [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        kb.row(*buttons)
    return kb


def input_file_safe(path: Path):
    if path.exists():
        return InputFile(str(path))
    return None


# ======================== HANDLERS ========================

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    welcome_img = IMAGES_DIR / "welcome.jpg"
    caption = (
        "<b>Добро пожаловать на обучение Eclipse Agency!</b> 🌑\n\n"
        "Я буду твоим личным гидом в освоении роли <b>оператора</b> — сотрудника, "
        "который умеет выстраивать связь, удерживать внимание и превращать диалог в результат.\n\n"
        "<b>Стартовые условия:</b>\n"
        "💰 20% от всех продаж\n"
        "🕗 Гибкий 8-часовой график\n"
        "📆 1 выходной в неделю\n"
        "💸 Выплаты — 7 и 22 числа (USDT)\n"
        "⚠️ Комиссия за конвертацию (~5%) не покрывается агентством"
    )

    intro_text = (
        "Почему именно такие стартовые условия?\n\n"
        "📈 Повышение процента — до 23% при выполнении KPI\n"
        "👥 Роль Team Lead — +1% от заработка команды (3 человека)\n"
        "🎯 Бонусы за достижения — выплаты за стабильность и инициативу\n"
        "🚀 Карьерный рост — от оператора до администратора\n\n"
        "Нажми кнопку ниже, если тебе подходят условия 👇"
    )
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("⭐Мне подходят условия⭐", callback_data="agree_conditions")
    )

    if welcome_img.exists():
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=InputFile(str(welcome_img)),
            caption=caption + "\n\n" + intro_text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    else:
        await bot.send_message(
            chat_id=message.chat.id,
            text=caption + "\n\n" + intro_text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )


@dp.callback_query_handler(lambda c: c.data == "agree_conditions")
async def cb_agree_conditions(cq: types.CallbackQuery):
    await cq.answer()
    text = (
        "❗️Обрати внимание: Условие ниже не распространяется на стажировочный период (7 дней)!\n\n"
        "Если ты решишь завершить сотрудничество, потребуется отработать не более 7 дней "
        "с момента уведомления администратора.\n\n"
        "Теперь давай начнём с простого — как тебя зовут?"
    )
    await bot.send_message(cq.from_user.id, text)
    await Form.waiting_for_name.set()


@dp.message_handler(state=Form.waiting_for_name, content_types=types.ContentTypes.TEXT)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    text = f"Красивое имя, {name}! 🌟\n\n{name}, ты знаком(-а) с работой на OnlyFans?"
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("Да", callback_data="onlyfans_yes"),
        InlineKeyboardButton("Нет", callback_data="onlyfans_no")
    )
    await bot.send_message(message.chat.id, text, reply_markup=kb)
    await Form.waiting_for_onlyfans.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("onlyfans_"), state=Form.waiting_for_onlyfans)
async def cb_onlyfans_answer(cq: types.CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    name = data.get("name", "друг")
    if cq.data == "onlyfans_yes":
        await bot.send_message(cq.from_user.id, f"Отлично, {name}! Тогда двигаться дальше будет проще ✅")
    else:
        await bot.send_message(cq.from_user.id, f"Ничего страшного, {name}, я всё объясню с нуля 😉")
    await state.finish()

    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("А как заработать?", callback_data="earn_money"))
    await bot.send_message(cq.from_user.id, "Теперь расскажу, как именно ты сможешь зарабатывать 💸", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "earn_money")
async def cb_earn_money(cq: types.CallbackQuery):
    await cq.answer()
    uid = cq.from_user.id
    text1 = (
        "Ещё со времён брачных агентств я научился мгновенно находить контакт и превращать любую деталь "
        "в точку опоры для продажи. Ты спросишь как? Всё просто:\n\n"
        "Узнал имя? — загуглил интересные факты.\n"
        "Ещё и фамилию? — нашёл фото, закинул шутку.\n"
        "Фан рассказал где живет? — изучаю местные фишки.\n\n"
        "Любая мелочь — повод для сближения, если цель не просто продать, а завоевать доверие."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Где и как искать клиентов ?", callback_data="find_clients"))
    await bot.send_message(uid, text1, reply_markup=kb)


# ======================== Новая часть: ПО и Командная работа ========================

@dp.callback_query_handler(lambda c: c.data == "questions_start")
async def cb_questions_start(cq: types.CallbackQuery):
    await cq.answer()
    uid = cq.from_user.id
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🌟ПО", callback_data="soft_first"),
        InlineKeyboardButton("🌟Командная работа", callback_data="teamwork_first")
    )
    caption = "Теперь обсудим ПО и командную работу 🤖"
    photo = input_file_safe(IMAGES_DIR / "teamwork.jpg")
    if photo:
        await bot.send_photo(uid, photo=photo, caption=caption, reply_markup=kb)
    else:
        await bot.send_message(uid, caption, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "teamwork_first")
async def teamwork_first(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "🤝 Командная работа — основа успеха, особенно в нашей сфере.\n\n"
        "Вот несколько простых правил:\n"
        "🔹 Доверие — выполняй обещания.\n"
        "🔹 Общение — решай вопросы сразу.\n"
        "🔹 Совместное развитие — делись опытом.\n"
        "🔹 Ответственность — отвечай за результат.\n\n"
        "💬 Командная синергия не случается сама собой — её нужно строить."
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🟩 А теперь поговорим о ПО", callback_data="soft_second")
    )
    await callback.message.edit_text(text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "soft_first")
async def soft_first(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "🟩 Для работы мы используем Onlymonster.\n\n"
        "💻 Скачай: https://onlymonster.ai/downloads\n"
        "⚠️ Не регистрируйся — после обучения получишь ссылку.\n\n"
        "💸 Учет баланса — в Google Таблицах: в начале и в конце смены."
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🤝 А теперь поговорим о команде", callback_data="teamwork_second")
    )
    await callback.message.edit_text(text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "soft_second")
async def soft_second(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "🟩 Onlymonster — наш браузер для работы на странице.\n\n"
        "💻 Скачай: https://onlymonster.ai/downloads\n\n"
        "💸 Учет баланса — фиксируй в Google Таблицах.\n"
        "Для этого нужен Google-аккаунт."
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Дальше", callback_data="final_question")
    )
    await callback.message.edit_text(text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "teamwork_second")
async def teamwork_second(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "🤝 Командная работа — ключ к успеху.\n\n"
        "🔹 Доверие\n🔹 Общение\n🔹 Понимание ролей\n🔹 Совместное развитие\n\n"
        "💬 Уважай коллег и поддерживай связь."
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Дальше", callback_data="final_question")
    )
    await callback.message.edit_text(text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "final_question")
async def final_question(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "А теперь быстрый вопрос, чтобы проверить, как ты усвоил материал:\n\n"
        "🙋 Куда нужно записывать балансы за начало и конец смены?"
    )


# ======================== Webhook startup/shutdown ========================

async def on_startup(dp: Dispatcher):
    try:
        await bot.delete_webhook()
        logger.info("Old webhook deleted.")
    except Exception:
        logger.exception("Error deleting old webhook.")
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")


async def on_shutdown(dp: Dispatcher):
    logger.info("Shutting down...")
    try:
        await bot.delete_webhook()
    except Exception:
        logger.exception("Error removing webhook")
    await bot.session.close()


if __name__ == "__main__":
    parsed = urlparse(WEBHOOK_URL)
    webhook_path = parsed.path
    executor.start_webhook(
        dispatcher=dp,
        webhook_path=webhook_path,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host="0.0.0.0",
        port=PORT,
    )
```
