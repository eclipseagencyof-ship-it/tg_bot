# telegram_bot.py
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile, ParseMode
from aiogram.utils.exceptions import InvalidQueryID, PhotoDimensions, TelegramAPIError
from dotenv import load_dotenv

# --- Load environment ---
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # full public URL e.g. https://your-app.onrender.com/
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


# --- Helpers ---
def input_file_safe(path: Path | str):
    """Return InputFile if file exists, otherwise None."""
    if not path:
        return None
    p = Path(path)
    if p.exists():
        return InputFile(str(p))
    return None


async def safe_answer(cq: types.CallbackQuery):
    """Answer callback_query but ignore InvalidQueryID (too old) errors."""
    try:
        await cq.answer()
    except InvalidQueryID:
        logger.debug("CallbackQuery too old / already answered - ignoring.")
    except Exception as e:
        logger.exception("Unexpected error in cq.answer(): %s", e)


async def send_photo_with_fallback(chat_id: int, photo_path: Path | str, caption: str = None, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = None):
    """
    Try to send as photo. If Telegram rejects with PhotoDimensions, send as document instead.
    """
    f = input_file_safe(photo_path)
    if not f:
        # if no file, fallback to simple message
        await bot.send_message(chat_id, caption or "", parse_mode=parse_mode, reply_markup=reply_markup)
        return

    try:
        await bot.send_photo(chat_id, photo=f, caption=caption, parse_mode=parse_mode, reply_markup=reply_markup)
    except PhotoDimensions:
        # fallback to document (works for very large images)
        logger.warning("Photo invalid dimensions — sending as document instead: %s", photo_path)
        try:
            await bot.send_document(chat_id, document=f, caption=caption, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.exception("Failed to send document fallback: %s", e)
            # final fallback: send text only
            await bot.send_message(chat_id, caption or "", parse_mode=parse_mode, reply_markup=reply_markup)
    except TelegramAPIError as e:
        logger.exception("Telegram API error while sending photo: %s", e)
        # fallback to message
        await bot.send_message(chat_id, caption or "", parse_mode=parse_mode, reply_markup=reply_markup)


# ---------------- HANDLERS / FLOWS ----------------

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

    file_ = input_file_safe(welcome_img)
    if file_:
        await send_photo_with_fallback(message.chat.id, welcome_img, caption=caption + "\n\n" + intro_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(message.chat.id, caption + "\n\n" + intro_text, parse_mode=ParseMode.HTML, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "agree_conditions")
async def cb_agree_conditions(cq: types.CallbackQuery):
    await safe_answer(cq)

    # Первое сообщение — информация
    warning_text = (
        "❗️Обрати внимание: Условие ниже не распространяется на стажировочный период (7 дней)!\n\n"
        "Если ты решишь завершить сотрудничество, потребуется отработать не более 7 дней "
        "с момента уведомления администратора."
    )
    await bot.send_message(cq.from_user.id, warning_text)

    # Второе сообщение — отдельный вопрос (в одном сообщении бот не задаёт, а ждёт ответ)
    await bot.send_message(cq.from_user.id, "Теперь давай начнём с простого — как тебя зовут?")

    # Ожидаем ответ
    await Form.waiting_for_name.set()


@dp.message_handler(state=Form.waiting_for_name, content_types=types.ContentTypes.TEXT)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)

    # Inline Yes/No buttons are now active and handled; but if you prefer to remove them entirely you can
    # replace this with a simple message and a single "Продолжить" button. For now we'll use inline Yes/No.
    text = f"Красивое имя, {name}! 🌟\n\n{name}, ты знаком(-а) с работой на OnlyFans?"
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("Да", callback_data="onlyfans_yes"),
        InlineKeyboardButton("Нет", callback_data="onlyfans_no")
    )
    await bot.send_message(message.chat.id, text, reply_markup=kb)
    await Form.waiting_for_onlyfans.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("onlyfans_"), state=Form.waiting_for_onlyfans)
async def cb_onlyfans_answer(cq: types.CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    data = await state.get_data()
    name = data.get("name", "друг")

    # Ответ пользователю
    if cq.data == "onlyfans_yes":
        await bot.send_message(cq.from_user.id, f"Отлично, {name}! Тогда двигаться дальше будет проще ✅")
    else:
        await bot.send_message(cq.from_user.id, f"Ничего страшного, {name}, я всё объясню с нуля 😉")

    # Завершаем состояние
    await state.finish()

    # ---- Продолжаем урок: отправляем блоки (все изображения берём из images/) ----

    # 1) OnlyFans intro (photo or text)
    photo_onlyfans = IMAGES_DIR / "onlyfans_intro.jpg"
    caption1 = (
        "*OnlyFans* — это пространство, куда приходят люди за чувственным и эмоциональным контактом.\n\n"
        "В большинстве случаев речь идёт о «сексе по переписке», дополненном атмосферой тёплого диалога — "
        "о жизни, мыслях, желаниях.\n\n"
        "Да, платформа позволяет продавать разнообразный контент, но давай говорить честно: просто так никто ничего покупать не станет. "
        "Тут важно не «контент», а связь и ощущение значимости.\n\n"
        "Оборот платформы — десятки миллиардов долларов в год, а владелец получает миллиардные дивиденды, "
        "так что вопрос с деньгами тут же и закроем. Деньги здесь есть. И их много.\n\n"
        "Наша задача — может и не гнаться за всем пирогом🥧, а отрезать себе действительно достойный кусок💸"
    )
    await send_photo_with_fallback(cq.from_user.id, photo_onlyfans, caption=caption1, parse_mode=ParseMode.MARKDOWN)

    # 2) Follow-up text + button "Дальше"
    text2 = (
        "Прежде чем начать обучение — запомни главное: ты не просто продаёшь контент, ты даришь людям ощущение счастья 📌\n\n"
        "С таким подходом ты не только обойдёшь конкурентов, но и почувствуешь настоящую ценность своей работы 🤙\n\n"
        "В мире полно одиноких и потерянных людей, ищущих тепло и внимание 💔\n\n"
        "Мы не можем дать им физическую любовь, но можем подарить им близость, страсть… ну и, конечно, нюдсы 😏\n\n"
        "Ладно, хватит лирики — поехали дальше! 💥"
    )
    kb_next = InlineKeyboardMarkup().add(InlineKeyboardButton("➡️ Дальше", callback_data="of_next_1"))
    await bot.send_message(cq.from_user.id, text2, reply_markup=kb_next)


@dp.callback_query_handler(lambda c: c.data == "of_next_1")
async def of_next_1(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_of_people = IMAGES_DIR / "of_people.jpg"
    caption2 = (
        "🖼 Многие приходят в Adult-индустрию ради заработка, но забывают о главном — о людях по ту сторону экрана 🥲\n\n"
        "В интернете побеждает тот, кто отдаёт больше: не контента, а внимания и понимания.\n\n"
        "Пользователи платят не за «WOW», а за тёплое, живое общение.\n\n"
        "OnlyFans — это не просто платформа, а социальная сеть, куда заходят не только «выпустить пар», но и пообщаться 🫂\n\n"
        "Если хочешь зарабатывать стабильно, а не срубить быстро и сгореть — делай так, чтобы с тобой хотели общаться.\n\n"
        "Понимание потребностей и индивидуальный подход — вот что приносит настоящие деньги 💸\n\n"
        "Сделай жизнь клиента чуть ярче, и он точно это оценит 😉"
    )
    kb_next2 = InlineKeyboardMarkup().add(InlineKeyboardButton("➡️ Дальше", callback_data="of_next_2"))
    await send_photo_with_fallback(cq.from_user.id, photo_of_people, caption=caption2, reply_markup=kb_next2, parse_mode=ParseMode.MARKDOWN)


@dp.callback_query_handler(lambda c: c.data == "of_next_2")
async def of_next_2(cq: types.CallbackQuery):
    await safe_answer(cq)

    text4 = (
        "Если хочешь зарабатывать стабильно, а не сжечь аудиторию ради быстрого профита — "
        "делай так, чтобы фанам нравилось общаться с тобой.\n\n"
        "Кто-то ищет страсть, кто-то — тепло.\n\n"
        "Понимание потребностей и индивидуальный подход — вот путь к большим деньгам 💸\n\n"
        "Сделай жизнь клиента чуточку лучше — и он точно это оценит 😉"
    )
    kb_earn = InlineKeyboardMarkup().add(InlineKeyboardButton("⭐ А как заработать? ⭐", callback_data="how_to_earn"))
    await bot.send_message(cq.from_user.id, text4, reply_markup=kb_earn)


@dp.callback_query_handler(lambda c: c.data == "how_to_earn")
async def how_to_earn_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    text1 = (
        "Ещё со времён брачных агентств я научился мгновенно находить контакт "
        "и превращать любую деталь в точку опоры для продажи. Ты спросишь как? Всё просто:\n\n"
        "🔹 Узнал имя? — загуглил интересные факты.\n"
        "🔹 Ещё и фамилию? — нашёл фото, закинул шутку.\n"
        "🔹 Фан рассказал где живёт? — изучаю местные фишки.\n\n"
        "Любая мелочь — повод для сближения, если цель не просто продать, а завоевать доверие."
    )
    await bot.send_message(cq.from_user.id, text1)

    text2 = (
        "Ты будешь создавать сотни историй отношений между моделью и клиентом 🙌\n\n"
        "Из этого формула продажи очень проста:\n"
        "Инфо о фанате + верное предложение = прибыль 📈"
    )
    await bot.send_message(cq.from_user.id, text2)

    text3 = (
        "Пиши клиентам каждый день, даже если они в данный момент не готовы тратить деньги. "
        "Когда деньги появятся — они вспомнят именно тебя ❤️‍🩹"
    )
    kb_next = InlineKeyboardMarkup().add(InlineKeyboardButton("⭐ Где и как искать клиентов? ⭐", callback_data="find_clients"))
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb_next)


@dp.callback_query_handler(lambda c: c.data == "find_clients")
async def find_clients_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_path = IMAGES_DIR / "find_clients.jpg"
    caption1 = (
        "🖼 Представь, что ты на рыбалке: улов зависит от наживки. В нашем случае — это рассылка фанам.\n\n"
        "Фан уже видел сотни сообщений, сделай так, чтобы клюнул на твоё 🎣\n\n"
        "Добавляй сленг, сокращай, меняй формулировки — главное, чтобы выглядело живо и по-своему."
    )
    await send_photo_with_fallback(cq.from_user.id, photo_path, caption=caption1)

    text2 = (
        "Да, OnlyFans — платформа для откровенного контента, но рассылки не должны быть слишком прямыми или порнографичными 🔞\n\n"
        "Откровенный спам быстро убивает интерес. Клиенты заносят вас в список «ещё одной шлюхи» — "
        "а такие не цепляют и не вызывают желания платить 💸\n\n"
        "Работай тонко: лёгкая эротика, намёки, игра с воображением."
    )
    await bot.send_message(cq.from_user.id, text2)

    text3 = (
        "Мы используем 3 типа рассылок:\n\n"
        "✔️ VIP — персональные сообщения постоянным клиентам\n"
        "✔️ Онлайн — рассылка для тех, кто сейчас в сети\n"
        "✔️ Массовая — охват всех клиентов страницы, кроме VIP\n\n"
        "Каждый тип рассылки — это свой подход и шанс на продажу."
    )
    kb_diff = InlineKeyboardMarkup().add(InlineKeyboardButton("💡 Зачем нужны разные рассылки?", callback_data="diff_mailings"))
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb_diff)


@dp.callback_query_handler(lambda c: c.data == "diff_mailings")
async def diff_mailings_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    # VIP
    photo_vip = IMAGES_DIR / "vip_clients.jpg"
    caption_vip = (
        "Рассылка подбирается под тип клиента 💬\n\n"
        "VIP-клиентам — только индивидуальные рассылки. Они платят за внимание, а не за шаблон."
    )
    await send_photo_with_fallback(cq.from_user.id, photo_vip, caption=caption_vip, parse_mode=ParseMode.MARKDOWN)

    # ONLINE
    photo_online = IMAGES_DIR / "online_clients.jpg"
    caption_online = (
        "Если клиент сейчас онлайн — это лучший момент для рассылки. Цепляйся за ник/аватар — элемент персонализации."
    )
    await send_photo_with_fallback(cq.from_user.id, photo_online, caption=caption_online)

    # MASS + two buttons
    photo_mass = IMAGES_DIR / "mass_message.jpg"
    caption_mass = (
        "Массовая рассылка летит всем — делай её цепляющей, но не навязчивой. "
        "Фан увидит ~25 символов — ставь самое главное в начало."
    )
    kb_mass = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("😏 Я всё понял", callback_data="understood"),
        InlineKeyboardButton("☝️ Можно ещё информацию?", callback_data="more_info")
    )
    await send_photo_with_fallback(cq.from_user.id, photo_mass, caption=caption_mass, reply_markup=kb_mass, parse_mode=ParseMode.MARKDOWN)


# Small example handlers for understood / more_info to keep flow consistent
@dp.callback_query_handler(lambda c: c.data == "understood")
async def cb_understood(cq: types.CallbackQuery):
    await safe_answer(cq)
    await bot.send_message(cq.from_user.id, "Отлично! Тогда двигаемся дальше. /menu (или продолжай по кнопкам).")


@dp.callback_query_handler(lambda c: c.data == "more_info")
async def cb_more_info(cq: types.CallbackQuery):
    await safe_answer(cq)
    await bot.send_message(cq.from_user.id, "Хочешь ещё материалов? Скоро добавим расширенный модуль.")


# Example: questions_start -> ПО / Команда flow
@dp.callback_query_handler(lambda c: c.data == "questions_start")
async def cb_questions_start(cq: types.CallbackQuery):
    await safe_answer(cq)
    uid = cq.from_user.id
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🌟ПО", callback_data="soft_first"),
        InlineKeyboardButton("🌟Командная работа", callback_data="teamwork_first")
    )
    caption = "Теперь обсудим ПО и командную работу 🤖"
    photo = IMAGES_DIR / "teamwork.jpg"
    await send_photo_with_fallback(uid, photo, caption=caption, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "teamwork_first")
async def teamwork_first(callback: types.CallbackQuery):
    await safe_answer(callback)
    text = (
        "🤝 Командная работа — основа успеха.\n\n"
        "🔹 Доверие — выполняй обещания.\n🔹 Общение — решай вопросы сразу.\n🔹 Совместное развитие — делись опытом."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🟩 А теперь поговорим о ПО", callback_data="soft_second"))
    # try edit message, if not possible — send new
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "soft_first")
async def soft_first(callback: types.CallbackQuery):
    await safe_answer(callback)
    text = (
        "🟩 Для работы мы используем Onlymonster.\n\n"
        "💻 Скачай: https://onlymonster.ai/downloads\n"
        "⚠️ Не регистрируйся — после обучения получишь ссылку.\n\n"
        "💸 Учет баланса — в Google Таблицах: в начале и в конце смены."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🤝 А теперь поговорим о команде", callback_data="teamwork_second"))
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "soft_second")
async def soft_second(callback: types.CallbackQuery):
    await safe_answer(callback)
    text = (
        "🟩 Onlymonster — наш браузер для работы на странице.\n\n"
        "💻 Скачай: https://onlymonster.ai/downloads\n\n"
        "💸 Учет баланса — фиксируй в Google Таблицах. Для этого нужен Google-аккаунт."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("➡️ Дальше", callback_data="final_question"))
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "teamwork_second")
async def teamwork_second(callback: types.CallbackQuery):
    await safe_answer(callback)
    text = (
        "🤝 Командная работа — ключ к успеху.\n\n"
        "🔹 Доверие\n🔹 Общение\n🔹 Понимание ролей\n\n"
        "💬 Уважай коллег и поддерживай связь."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("➡️ Дальше", callback_data="final_question"))
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "final_question")
async def final_question(callback: types.CallbackQuery):
    await safe_answer(callback)
    q = "А теперь быстрый вопрос, чтобы проверить, как ты усвоил материал:\n\n🙋 Куда нужно записывать балансы за начало и конец смены?"
    try:
        await callback.message.edit_text(q)
    except Exception:
        await bot.send_message(callback.from_user.id, q)


# Fallback message handler
@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Не распознал команду. Используй /start. Кнопки — inline под сообщениями.")


# ======================== Webhook startup/shutdown ========================

async def on_startup(dp: Dispatcher):
    try:
        await bot.delete_webhook()
        logger.info("Old webhook deleted (if existed).")
    except Exception:
        logger.debug("No previous webhook or failed to delete (ignored).")
    # set webhook
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")


async def on_shutdown(dp: Dispatcher):
    logger.info("Shutting down...")
    try:
        await bot.delete_webhook()
    except Exception:
        logger.debug("Webhook deletion on shutdown failed (ignored).")
    try:
        await bot.close()
    except Exception:
        logger.debug("bot.close() failed (ignored).")


if __name__ == "__main__":
    parsed = urlparse(WEBHOOK_URL)
    webhook_path = parsed.path  # e.g. '/webhook/....'
    executor.start_webhook(
        dispatcher=dp,
        webhook_path=webhook_path,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host="0.0.0.0",
        port=PORT,
    )
