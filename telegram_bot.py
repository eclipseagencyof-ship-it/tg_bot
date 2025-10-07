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
from aiogram.utils.exceptions import InvalidQueryID

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
    """Return InputFile if exists, otherwise None."""
    if path and Path(path).exists():
        return InputFile(str(path))
    return None


async def safe_answer(cq: types.CallbackQuery):
    """Answer callback_query but ignore InvalidQueryID (too old) errors."""
    try:
        await cq.answer()
    except InvalidQueryID:
        logger.debug("CallbackQuery too old / already answered - ignoring.")
    except Exception as e:
        logger.exception("Unexpected error in cq.answer(): %s", e)


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

    file_ = input_file_safe(welcome_img)
    if file_:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=file_,
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
    await safe_answer(cq)

    # Первое сообщение — информация
    warning_text = (
        "❗️Обрати внимание: Условие ниже не распространяется на стажировочный период (7 дней)!\n\n"
        "Если ты решишь завершить сотрудничество, потребуется отработать не более 7 дней "
        "с момента уведомления администратора."
    )
    await bot.send_message(cq.from_user.id, warning_text)

    # Второе сообщение — отдельный вопрос
    await bot.send_message(cq.from_user.id, "Теперь давай начнём с простого — как тебя зовут?")

    # Ожидаем ответ
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
    await safe_answer(cq)
    data = await state.get_data()
    name = data.get("name", "друг")

    # Ответ пользователю в зависимости от его выбора
    if cq.data == "onlyfans_yes":
        await bot.send_message(cq.from_user.id, f"Отлично, {name}! Тогда двигаться дальше будет проще ✅")
    else:
        await bot.send_message(cq.from_user.id, f"Ничего страшного, {name}, я всё объясню с нуля 😉")

    # Завершаем состояние
    await state.finish()

    # ---- продолжение урока: отправляем блоки безопасно ----
    # 1️⃣ Отправляем первый блок с изображением и описанием OnlyFans
    photo_file = input_file_safe(IMAGES_DIR / "onlyfans_intro.jpg")
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
    if photo_file:
        await bot.send_photo(cq.from_user.id, photo=photo_file, caption=caption1, parse_mode=ParseMode.MARKDOWN)
    else:
        await bot.send_message(cq.from_user.id, caption1, parse_mode=ParseMode.MARKDOWN)

    # 2️⃣ Отправляем второй блок с кнопкой «Дальше»
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

    # 3️⃣ Вторая локальная картинка + текст
    photo_file = input_file_safe(IMAGES_DIR / "of_people.jpg")
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
    if photo_file:
        await bot.send_photo(cq.from_user.id, photo=photo_file, caption=caption2, reply_markup=kb_next2, parse_mode=ParseMode.MARKDOWN)
    else:
        await bot.send_message(cq.from_user.id, caption2, reply_markup=kb_next2, parse_mode=ParseMode.MARKDOWN)


@dp.callback_query_handler(lambda c: c.data == "of_next_2")
async def of_next_2(cq: types.CallbackQuery):
    await safe_answer(cq)

    # 4️⃣ Финальное сообщение
    text4 = (
        "Если хочешь зарабатывать стабильно, а не сжечь аудиторию ради быстрого профита — "
        "делай так, чтобы фанам нравилось общаться с тобой.\n\n"
        "Кто-то ищет страсть, кто-то — тепло.\n\n"
        "Понимание потребностей и индивидуальный подход — вот путь к большим деньгам 💸\n\n"
        "Сделай жизнь клиента чуточку лучше — и он точно это оценит 😉"
    )
    kb_earn = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ А как заработать? ⭐", callback_data="how_to_earn")
    )

    await bot.send_message(cq.from_user.id, text4, reply_markup=kb_earn)


# 🟢 Реакция на кнопку "⭐ А как заработать? ⭐"
@dp.callback_query_handler(lambda c: c.data == "how_to_earn")
async def how_to_earn_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    # 1️⃣ Первый блок
    text1 = (
        "Ещё со времён брачных агентств я научился мгновенно находить контакт "
        "и превращать любую деталь в точку опоры для продажи. Ты спросишь как? Всё просто:\n\n"
        "🔹 Узнал имя? — загуглил интересные факты.\n"
        "🔹 Ещё и фамилию? — нашёл фото, закинул шутку: «Это не ты гонял на байке в Бруклине?»\n"
        "🔹 Фан рассказал где живёт? — изучаю местные фишки, подбираю тему для диалога.\n"
        "🔹 Фанат NBA? — спрашиваю про любимую команду и продолжаю разговор на знакомой волне.\n\n"
        "Любая мелочь — повод для сближения, если цель не просто продать, а завоевать доверие. "
        "Ведь, как и в любви, по-настоящему вовлекает тот, кто цепляет чем-то личным 💘"
    )
    await bot.send_message(cq.from_user.id, text1)

    # 2️⃣ Второй блок
    text2 = (
        "Ты будешь создавать сотни историй отношений между моделью и клиентом 🙌\n\n"
        "У каждого клиента свой интерес — твоя задача предложить то, от чего он не сможет отказаться.\n\n"
        "Из этого формула продажи очень проста:\n\n"
        "🧩 На основе собранной информации понимаешь, чего хочет фан + "
        "давишь на это во время продажи = прибыль 📈"
    )
    await bot.send_message(cq.from_user.id, text2)

    # 3️⃣ Третий блок с кнопкой
    text3 = (
        "Пиши клиентам каждый день, даже если они в данный момент не готовы тратить денежки 💬\n\n"
        "Деньги у них рано или поздно появятся, а потратят они их на ту модель, "
        "что не забила на них в период, когда у них не было кэша ❤️‍🩹"
    )
    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ Где и как искать клиентов? ⭐", callback_data="find_clients")
    )
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb_next)


# 🟢 Реакция на кнопку "⭐ Где и как искать клиентов? ⭐"
@dp.callback_query_handler(lambda c: c.data == "find_clients")
async def find_clients_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    # 1️⃣ Первый блок — с фото
    photo_path = IMAGES_DIR / "find_clients.jpg"
    caption1 = (
        "🖼 Представь, что ты на рыбалке: улов зависит от наживки. В нашем случае — это рассылка фанам.\n\n"
        "Фан уже видел сотни сообщений, сделай так, чтобы клюнул на твоё 🎣\n\n"
        "Добавляй сленг, сокращай, меняй формулировки — главное, чтобы выглядело живо и по-своему. Например:\n\n"
        "👉 Hey, do you mind getting to know each other? → Hey! U down to link up to me? 👋😄\n"
        "(Привет, не против узнать друг друга? → Хей! Не хочешь присоединиться ко мне?)\n\n"
        "👉 Are you here for fun or are you looking for something more? → U here 4 fun or lookin’ 4 sumthin’ more? 😄"
    )
    f = input_file_safe(photo_path)
    if f:
        await bot.send_photo(cq.from_user.id, photo=f, caption=caption1)
    else:
        await bot.send_message(cq.from_user.id, caption1)

    # 2️⃣ Второй блок — текст без фото
    text2 = (
        "Да, OnlyFans — платформа для откровенного контента, но рассылки не должны быть слишком прямыми "
        "или порнографичными 🔞\n\n"
        "Откровенный спам быстро убивает интерес. Клиенты заносят вас в список «ещё одной шлюхи» — "
        "а такие не цепляют и не вызывают желания платить 💸\n\n"
        "Работай тонко: лёгкая эротика, намёки, игра с воображением. Пусть его фантазия доделает остальное 💡"
    )
    await bot.send_message(cq.from_user.id, text2)

    # 3️⃣ Третий блок — текст + кнопка
    text3 = (
        "Мы используем 3 типа рассылок, каждый из которых ориентирован на разную аудиторию. "
        "Во время смены тебе нужно будет работать по следующей схеме:\n\n"
        "✔️ VIP — персональные сообщения постоянным клиентам, которые уже покупали контент.\n\n"
        "✔️ Онлайн — рассылка для тех, кто сейчас в сети.\n\n"
        "✔️ Массовая — охват всех клиентов страницы, кроме VIP, чтобы не перегружать их.\n\n"
        "Каждый тип рассылки — это свой подход и шанс на продажу. Работай с умом 💬💸"
    )
    kb_diff = InlineKeyboardMarkup().add(
        InlineKeyboardButton("💡 Зачем нужны разные рассылки?", callback_data="diff_mailings")
    )
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb_diff)


# 🟢 Продолжение после кнопки "💡 Зачем нужны разные рассылки?"
@dp.callback_query_handler(lambda c: c.data == "diff_mailings")
async def diff_mailings_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    # 1️⃣ Текст + картинка (VIP)
    photo_vip = IMAGES_DIR / "vip_clients.jpg"
    caption_vip = (
        "Рассылка подбирается под тип клиента 💬\n\n"
        "VIP-клиентам — только индивидуальные рассылки.\n\n"
        "Они платят за внимание, а не за шаблон. Проявляй интерес, вспоминай прошлые темы, держи связь 👀\n\n"
        "Например, обсуждали *Hogwarts Legacy*? Загугли что-то прикольное и напиши:\n\n"
        "«Ты уже видел танцующего эльфа в тазике? Надеюсь, не пропустил этот момент! Только не шути, что он — это я в ванной 😂»"
    )
    f_vip = input_file_safe(photo_vip)
    if f_vip:
        await bot.send_photo(cq.from_user.id, photo=f_vip, caption=caption_vip, parse_mode=ParseMode.MARKDOWN)
    else:
        await bot.send_message(cq.from_user.id, caption_vip, parse_mode=ParseMode.MARKDOWN)

    # 2️⃣ Текст + картинка (онлайн)
    photo_online = IMAGES_DIR / "online_clients.jpg"
    caption_online = (
        "Если клиент сейчас онлайн — это лучший момент для рассылки 💬\n\n"
        "Шанс получить ответ выше, поэтому цепляйся за его ник или аватар — это уже элемент персонализации.\n\n"
        "Пример:\n\n"
        "“Я точно нашла тебя вне сайта! Хотя после часа поисков руки опустились… Таких ников слишком много 😪 " 
        "А мне правда важно быть на связи с фанатами, как ты ❤️”"
    )
    f_online = input_file_safe(photo_online)
    if f_online:
        await bot.send_photo(cq.from_user.id, photo=f_online, caption=caption_online)
    else:
        await bot.send_message(cq.from_user.id, caption_online)

    # 3️⃣ Текст + картинка + кнопки (mass)
    photo_mass = IMAGES_DIR / "mass_message.jpg"
    caption_mass = (
        "Массовая рассылка летит всем, поэтому её нужно строить так, чтобы зацепить любого, "
        "но не отпугнуть тех, с кем ты уже общался(-ась) 📝\n\n"
        "Фан сможет увидеть до *25 символов* в списке чатов, поэтому ставь в начало самое важное."
    )
    kb_mass = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("😏 Я всё понял", callback_data="understood"),
        InlineKeyboardButton("☝️ Можно ещё информацию?", callback_data="more_info")
    )
    f_mass = input_file_safe(photo_mass)
    if f_mass:
        await bot.send_photo(cq.from_user.id, photo=f_mass, caption=caption_mass, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_mass)
    else:
        await bot.send_message(cq.from_user.id, caption_mass, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_mass)


@dp.callback_query_handler(lambda c: c.data == "questions_start")
async def cb_questions_start(cq: types.CallbackQuery):
    await safe_answer(cq)
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
    await safe_answer(callback)
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
    # редактируем сообщение, если возможно — если нет, отправляем новое
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
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🤝 А теперь поговорим о команде", callback_data="teamwork_second")
    )
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
        "💸 Учет баланса — фиксируй в Google Таблицах.\n"
        "Для этого нужен Google-аккаунт."
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Дальше", callback_data="final_question")
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "teamwork_second")
async def teamwork_second(callback: types.CallbackQuery):
    await safe_answer(callback)
    text = (
        "🤝 Командная работа — ключ к успеху.\n\n"
        "🔹 Доверие\n🔹 Общение\n🔹 Понимание ролей\n🔹 Совместное развитие\n\n"
        "💬 Уважай коллег и поддерживай связь."
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Дальше", callback_data="final_question")
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await bot.send_message(callback.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "final_question")
async def final_question(callback: types.CallbackQuery):
    await safe_answer(callback)
    try:
        await callback.message.edit_text(
            "А теперь быстрый вопрос, чтобы проверить, как ты усвоил материал:\n\n"
            "🙋 Куда нужно записывать балансы за начало и конец смены?"
        )
    except Exception:
        await bot.send_message(callback.from_user.id,
            "А теперь быстрый вопрос, чтобы проверить, как ты усвоил материал:\n\n"
            "🙋 Куда нужно записывать балансы за начало и конец смены?"
        )


# ======================== Webhook startup/shutdown ========================

async def on_startup(dp: Dispatcher):
    try:
        await bot.delete_webhook()
        logger.info("Old webhook deleted.")
    except Exception:
        logger.debug("No previous webhook or failed to delete (ignored).")
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")


async def on_shutdown(dp: Dispatcher):
    logger.info("Shutting down...")
    try:
        await bot.delete_webhook()
    except Exception:
        logger.debug("Webhook deletion on shutdown failed (ignored).")
    try:
        await bot.session.close()
    except Exception:
        logger.debug("bot.session.close() failed (ignored).")


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
