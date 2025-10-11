# telegram_bot.py
import logging
import os
import asyncio
from pathlib import Path
from urllib.parse import urljoin

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile, ParseMode
from aiogram.utils.exceptions import InvalidQueryID, PhotoDimensions, TelegramAPIError
from dotenv import load_dotenv
from aiogram.utils.executor import start_webhook

# --- Load env ---
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("WEBHOOK_URL")  # full public URL e.g. https://your-app.onrender.com
PORT = int(os.getenv("PORT", "10000"))

if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env")
if not BASE_URL:
    raise RuntimeError("WEBHOOK_URL not set in .env")

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = urljoin(BASE_URL, WEBHOOK_PATH)

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
IMAGES_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# --- States ---
from aiogram.dispatcher.filters.state import State, StatesGroup

class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_onlyfans = State()
    quiz_waiting_answer = State()
    waiting_for_question_1 = State()
    waiting_for_question_2 = State()
    waiting_for_question_3 = State()
    waiting_for_balance_answer = State()


# --- Helpers ---
def input_file_safe(path):
    if not path:
        return None
    p = Path(path)
    if p.exists():
        return InputFile(str(p))
    return None

async def safe_answer(cq: types.CallbackQuery):
    """Ответ на callback_query, игнорируем 'Query is too old' ошибки."""
    try:
        # cache_time даёт клиенту знать, что он может не отправлять опять тот же callback
        await cq.answer(cache_time=1)
    except InvalidQueryID:
        logger.debug("CallbackQuery too old / already answered - ignoring.")
    except Exception:
        logger.exception("Unexpected error in cq.answer()")

async def send_photo_with_fallback(chat_id: int, photo_path, caption: str = None,
                                   reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = None):
    """
    Пытаемся отправить photo, при ошибке размеров — отправляем документ.
    Если файла нет — отправляем текстовое сообщение.
    """
    f = input_file_safe(photo_path)
    if not f:
        await bot.send_message(chat_id, caption or "", reply_markup=reply_markup, parse_mode=parse_mode)
        return
    try:
        await bot.send_photo(chat_id, photo=f, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
    except PhotoDimensions:
        logger.warning("Photo invalid dimensions — sending as document instead: %s", photo_path)
        try:
            await bot.send_document(chat_id, document=f, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            logger.exception("Failed to send document fallback, sending text.")
            await bot.send_message(chat_id, caption or "", reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramAPIError:
        logger.exception("Telegram API error while sending photo")
        await bot.send_message(chat_id, caption or "", reply_markup=reply_markup, parse_mode=parse_mode)

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

    await send_photo_with_fallback(message.chat.id, welcome_img, caption + "\n\n" + intro_text, reply_markup=kb, parse_mode=ParseMode.HTML)

# --- agree_conditions ---
@dp.callback_query_handler(lambda c: c.data == "agree_conditions")
async def cb_agree_conditions(cq: types.CallbackQuery):
    await safe_answer(cq)

    warning_text = (
        "❗️Обрати внимание: Условие ниже не распространяется на стажировочный период (7 дней)!\n\n"
        "Если ты решишь завершить сотрудничество, потребуется отработать не более 7 дней "
        "с момента уведомления администратора."
    )
    await bot.send_message(cq.from_user.id, warning_text)
    await bot.send_message(cq.from_user.id, "Теперь давай начнём с простого — как тебя зовут?")
    await Form.waiting_for_name.set()

# --- Receive name ---
@dp.message_handler(state=Form.waiting_for_name, content_types=types.ContentTypes.TEXT)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()

    # сохраняем имя в состояние FSM
    await state.update_data(name=name)

    # сохраняем имя глобально — чтобы использовать в конце обучения
    async with state.proxy() as data:
        data["name"] = name

    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("✅ Да", callback_data="onlyfans_yes"),
        InlineKeyboardButton("❌ Нет", callback_data="onlyfans_no")
    )
    await bot.send_message(
        message.chat.id,
        f"Красивое имя, {name}! 🌟\n\n{name}, ты знаком(-а) с работой на OnlyFans?",
        reply_markup=kb
    )

    await Form.waiting_for_onlyfans.set()

# --- Handle onlyfans yes/no ---
@dp.callback_query_handler(lambda c: c.data in ["onlyfans_yes", "onlyfans_no"], state=Form.waiting_for_onlyfans)
async def cb_onlyfans_answer(cq: types.CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    data = await state.get_data()
    name = data.get("name", "друг")

    if cq.data == "onlyfans_yes":
        await bot.send_message(cq.from_user.id, f"Отлично, {name}! Тогда двигаться дальше будет проще ✅")
    else:
        await bot.send_message(cq.from_user.id, f"Ничего страшного, {name}, я всё объясню с нуля 😉")

    await state.finish()

    # 1️⃣ Локальная картинка + текст (OnlyFans intro)
    photo = IMAGES_DIR / "onlyfans_intro.jpg"
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
    await send_photo_with_fallback(cq.from_user.id, photo, caption=caption1, parse_mode=ParseMode.MARKDOWN)

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

# --- of_next_1 ---
@dp.callback_query_handler(lambda c: c.data == "of_next_1")
async def of_next_1(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_path = IMAGES_DIR / "of_people.jpg"
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
    await send_photo_with_fallback(cq.from_user.id, photo_path, caption=caption2, reply_markup=kb_next2, parse_mode=ParseMode.MARKDOWN)

# --- of_next_2 ---
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

# --- how_to_earn ---
@dp.callback_query_handler(lambda c: c.data == "how_to_earn")
async def how_to_earn_info(cq: types.CallbackQuery):
    await safe_answer(cq)
    await asyncio.sleep(0.2)
    logger.info(f"➡️ Callback how_to_earn от {cq.from_user.id}")


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
    await asyncio.sleep(0.5)

    # 2️⃣ Второй блок
    text2 = (
        "Ты будешь создавать сотни историй отношений между моделью и клиентом 🙌\n\n"
        "У каждого клиента свой интерес — твоя задача предложить то, от чего он не сможет отказаться.\n\n"
        "Из этого формула продажи очень проста:\n\n"
        "🧩 На основе собранной информации понимаешь, чего хочет фан + "
        "давишь на это во время продажи = прибыль 📈"
    )
    await bot.send_message(cq.from_user.id, text2)
    await asyncio.sleep(0.5)


    # 3️⃣ Третий блок с кнопкой
    text3 = (
        "Пиши клиентам каждый день, даже если они в данный момент не готовы тратить денежки 💬\n\n"
        "Деньги у них рано или поздно появятся, а потратят они их на ту модель, "
        "что не забила на них в период, когда у них не было кэша ❤️‍🩹"
    )
    kb_next = InlineKeyboardMarkup().add(InlineKeyboardButton("⭐ Где и как искать клиентов? ⭐", callback_data="find_clients"))
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb_next)

# --- find_clients ---
@dp.callback_query_handler(lambda c: c.data == "find_clients")
async def find_clients_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_path = IMAGES_DIR / "find_clients.jpg"
    caption1 = (
        "🖼 Представь, что ты на рыбалке: улов зависит от наживки. В нашем случае — это рассылка фанам.\n\n"
        "Фан уже видел сотни сообщений, сделай так, чтобы клюнул на твоё 🎣\n\n"
        "Добавляй сленг, сокращай, меняй формулировки — главное, чтобы выглядело живо и по-своему. Например:\n\n"
        "👉 Hey, do you mind getting to know each other? → Hey! U down to link up to me? 👋😄\n"
        "(Привет, не против узнать друг друга? → Хей! Не хочешь присоединиться ко мне?)\n\n"
        "👉 Are you here for fun or are you looking for something more? → U here 4 fun or lookin’ 4 sumthin’ more? 😄\n"
        "(Ты здесь для развлечения или ищешь что-то большее?)"
    )
    kb_next = InlineKeyboardMarkup().add(InlineKeyboardButton("➡️ Дальше", callback_data="find_clients_done"))
    await send_photo_with_fallback(cq.from_user.id, photo_path, caption=caption1, reply_markup=kb_next)

# --- find_clients_done -> show mailing intro and button to full diff ---
@dp.callback_query_handler(lambda c: c.data == "find_clients_done")
async def show_diff_intro(cq: types.CallbackQuery):
    await safe_answer(cq)

    text2 = (
        "Да, OnlyFans — платформа для откровенного контента, но рассылки не должны быть слишком прямыми или порнографичными 🔞\n\n"
        "Почему?\n\n"
        "Откровенный спам быстро убивает интерес. Клиенты заносят вас в список «ещё одной шлюхи» — "
        "а такие не цепляют и не вызывают желания платить 💸\n\n"
        "Работай тонко: лёгкая эротика, намёки, игра с воображением. Пусть его фантазия доделает остальное 💡"
    )
    await bot.send_message(cq.from_user.id, text2)

    text3 = (
        "Мы используем 3 типа рассылок, каждый из которых ориентирован на разную аудиторию. "
        "Во время смены тебе нужно будет работать по следующей схеме:\n\n"
        "✔️ VIP — персональные сообщения постоянным клиентам, которые уже покупали контент.\n\n"
        "✔️ Онлайн — рассылка для тех, кто сейчас в сети.\n\n"
        "✔️ Массовая — охват всех клиентов страницы, кроме VIP, чтобы не перегружать их.\n\n"
        "Каждый тип рассылки — это свой подход и шанс на продажу. Работай с умом 💬💸"
    )
    kb_diff = InlineKeyboardMarkup().add(InlineKeyboardButton("💡 Зачем нужны разные рассылки?", callback_data="diff_mailings"))
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb_diff)

# --- diff_mailings (VIP -> ONLINE -> MASS, only MASS has buttons) ---
@dp.callback_query_handler(lambda c: c.data == "diff_mailings")
async def diff_mailings_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    # VIP
    photo_vip = IMAGES_DIR / "vip.jpg"
    caption_vip = (
        "Рассылка подбирается под тип клиента 💬\n\n"
        "VIP-клиентам — только индивидуальные рассылки.\n\n"
        "Они платят за внимание, а не за шаблон. Проявляй интерес, вспоминай прошлые темы, держи связь 👀\n\n"
        "Например, обсуждали *Hogwarts Legacy*? Загугли что-то прикольное и напиши:\n\n"
        "«Ты уже видел танцующего эльфа в тазике? Надеюсь, не пропустил этот момент! Только не шути, что он — это я в ванной 😂»\n\n"
        "Уловил суть? VIP клиент должен получать рассылку, привязанную исключительно к уже состоявшимся диалогам ранее."
    )
    await send_photo_with_fallback(cq.from_user.id, photo_vip, caption=caption_vip, parse_mode=ParseMode.MARKDOWN)

    # ONLINE
    photo_online = IMAGES_DIR / "online.jpg"
    caption_online = (
        "Если клиент сейчас онлайн — это лучший момент для рассылки 💬\n\n"
        "Шанс получить ответ выше, поэтому цепляйся за его ник или аватар — это уже элемент персонализации.\n\n"
        "Пример:\n\n"
        "“Я точно нашла тебя вне сайта! Хотя после часа поисков руки опустились… Таких ников слишком много 😪 "
        "А мне правда важно быть на связи с фанатами, как ты ❤️”\n\n"
        "Здесь мы:\n"
        "🔹 Заманили ярким началом\n"
        "🔹 Объяснили, почему 'искали'\n"
        "🔹 Ушли от темы мессенджеров — ведь фанаты важны нам именно здесь."
    )
    await send_photo_with_fallback(cq.from_user.id, photo_online, caption=caption_online, parse_mode=ParseMode.MARKDOWN)

    # MASS + buttons
    photo_mass = IMAGES_DIR / "mass.jpg"
    caption_mass = (
        "Массовая рассылка летит всем, поэтому её нужно строить так, чтобы зацепить любого, "
        "но не отпугнуть тех, с кем ты уже общался(-ась) 📝\n\n"
        "Темы могут быть любые — от бытового до лёгкой эротики, но без перебора, чтобы не скатиться "
        "в образ «ещё одной шлюхи» ☝️\n\n"
        "Если не хватает фантазии — обратись к новостям:\n\n"
        "“БОЛЬШОЙ крах банка! Слышал? Один из крупнейших банков США обанкротился. Надеюсь, тебя это не задело 🤞”\n\n"
        "Либо же с уклоном в эротику:\n\n"
        "\"Ur fingers been here b4? 😏 Just wonderin’...\" + фото модели\n"
        "(Ваши пальцы уже были здесь? 😏 Просто интересно)\n\n"
        "Фан сможет увидеть до 25 символов в листе чатов, поэтому старайся в эти 25 символов ставить самую «байтовую» часть своего сообщения 💥"
    )
    kb_mass = InlineKeyboardMarkup(row_width=1)
    kb_mass.add(InlineKeyboardButton("🌟 Я всё понял! 🌟", callback_data="mailing_done"))
    kb_mass.add(InlineKeyboardButton("🌟 Можно ещё информации? 🌟", callback_data="mailing_done"))

    await send_photo_with_fallback(cq.from_user.id, photo_mass, caption=caption_mass, reply_markup=kb_mass, parse_mode=ParseMode.MARKDOWN)

# --- Финальный блок после рассылки ---
@dp.callback_query_handler(lambda c: c.data == "mailing_done")
async def mailing_done(cq: types.CallbackQuery):
    await safe_answer(cq)

    text4 = (
        "🎯 Наша цель — дать тебе максимум полезной информации. Сегодня — о банальности в диалоге.\n\n"
        "Как большинство моделей начинают общение в чате?\n\n"
        "\"Hi. How are u?\" — классика. Но теперь представь, что ты уже 25-я, кто это спросил, "
        "а у него, как у того самого котика из тиктока, — всё заебись... 👍\n\n"
        "🛑 СТОП!\n\n"
        "Стандартное приветствие = стандартные ожидания. А значит — клиент жмёт \"назад\"."
    )
    await bot.send_message(cq.from_user.id, text4)

    text5 = (
        "✅ Как быть? Нарушай правила. Будь запоминающейся.\n\n"
        "Клиенты платят за уникальность — не за дежурное \"привет\".\n\n"
        "📌 Примеры нестандартного старта:\n\n"
        "- Ого, это ты? Я тебя ждала! Где пропадал? (Даже если он впервые — скажи, что виделась с ним во сне 😄)\n\n"
        "- Слушай, нужен совет! Красный или чёрный? (Цвет белья, лака, помады — включай фантазию)\n\n"
        "- А ты когда-нибудь пробовал секс после вдоха гелия? Мне кажется, так было бы веселее и... дольше жить! 😉"
    )
    await bot.send_message(cq.from_user.id, text5)

    text6 = (
        "🧠 Совет:\n\n"
        "Не жди вдохновения — заготавливай приветствия заранее. Это сэкономит время и придаст уверенности.\n\n"
        "💡 Что это тебе даст?\n\n"
        "Моментальных денег — нет.\n\n"
        "Запоминаемость, вовлечение и лояльность — ДА. А это уже залог будущих продаж 💸\n\n"
        "🙅‍♀️ Потому что когда ты пишешь \"How are you?\", чаще всего слышишь:\n\n"
        "\"I'm OK.\" И всё. А дальше? Ничего. 💀"
    )
    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Двигаемся дальше?", callback_data="start_questions")
    )
    await bot.send_message(cq.from_user.id, text6, reply_markup=kb_next)


# --- Переход к вопросам ---
@dp.callback_query_handler(lambda c: c.data == "start_questions")
async def start_questions_intro(cq: types.CallbackQuery):
    await safe_answer(cq)

    intro_text = (
        "Сейчас нам важно закрепить ту часть информации, которую ты уже успел усвоить. "
        "После каждого блока я буду задавать тебе несколько вопросов — это поможет тебе лучше всё запомнить и уверенно двигаться дальше.\n\n"
        "⚠️ Но сразу хочу предупредить:\n\n"
        "Мы легко определяем, когда кто-то проходит обучение с помощью ИИ. "
        "И поверь, всех, кто так делает, мы отправляем на повтор до тех пор, пока ответы не станут живыми и осознанными.\n\n"
        "💡 В твоих же интересах — отвечать от себя, своими словами и мыслями. "
        "Это не только ускорит процесс, но и поможет тебе быстрее начать реально зарабатывать 💸"
    )

    await bot.send_message(cq.from_user.id, intro_text)

    # --- Первый вопрос ---
    await asyncio.sleep(2)
    await bot.send_message(
        cq.from_user.id,
        "Теперь давай проверим, насколько хорошо ты усвоил материал 💬"
    )

    question1 = "🙋 На что в первую очередь нужно опираться при общении с клиентами?"
    await bot.send_message(cq.from_user.id, question1)
    await Form.waiting_for_question_1.set()


# --- Ответ на вопрос 1 ---
@dp.message_handler(state=Form.waiting_for_question_1, content_types=types.ContentTypes.TEXT)
async def handle_question_1(message: types.Message, state: FSMContext):
    await state.update_data(q1=message.text.strip())

    question2 = "🙋 Можно ли в рассылках использовать сообщения со слишком откровенным посылом и почему, если Да/Нет?"
    await bot.send_message(message.chat.id, question2)
    await Form.waiting_for_question_2.set()


# --- Вопрос 2 ---
@dp.message_handler(state=Form.waiting_for_question_2, content_types=types.ContentTypes.TEXT)
async def question_2(message: types.Message, state: FSMContext):
    await state.update_data(question_2=message.text.strip())

    question3 = (
        "✍️ Напиши персонализированное сообщение-рассылку клиенту.\n\n"
        "Для примера: Его зовут Саймон, у него есть 3-летняя дочь, и он увлекается баскетболом. "
        "Можешь использовать эту информацию для написания рассылки."
    )
    await bot.send_message(message.chat.id, question3)
    await Form.waiting_for_question_3.set()


# --- Вопрос 3 ---
@dp.message_handler(state=Form.waiting_for_question_3, content_types=types.ContentTypes.TEXT)
async def question_3(message: types.Message, state: FSMContext):
    # ✅ Сохраняем ответ пользователя
    await state.update_data(question_3=message.text.strip())

    # 💬 Сообщаем, что все ответы получены
    await bot.send_message(
        message.chat.id,
        "✅ Отлично! Все ответы получены.\n"
        "Ты справился с первой частью обучения и можешь переходить дальше 🚀"
    )

    # 🧹 Завершаем состояние FSM
    await state.finish()

    # --- 💻 Кнопка для перехода к следующему разделу ---
    next_step_kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("💻 Перейти к ПО", callback_data="soft_tools")
    )

    # 📩 Отправляем сообщение с кнопкой
    await bot.send_message(
        message.chat.id,
        "Теперь давай обсудим ПО, которое ты будешь использовать 🤖\n\n"
        "Это поможет тебе понять, как всё устроено и почему работа у нас идёт так слаженно 💪",
        reply_markup=next_step_kb
    )
# --- Обработка кнопки "💻 Перейти к ПО" ---
@dp.callback_query_handler(lambda c: c.data == "soft_tools")
async def soft_tools(cq: types.CallbackQuery):
    try:
        await cq.answer()  # чтобы Telegram не показывал "загрузка..."
        await send_soft_block(cq.from_user.id, next_callback="teamwork_info_final")
    except Exception as e:
        await bot.send_message(cq.from_user.id, f"⚠️ Ошибка при загрузке блока ПО: {e}")

# --- Универсальная функция: блок "ПО (Onlymonster)" ---
async def send_soft_block(chat_id: int, next_callback: str = "teamwork_info_final"):
    # 1️⃣ Текст + картинка
    image_path = IMAGES_DIR / "onlymonster_image.jpg"
    text1 = (
        "🟩 Для работы непосредственно на странице мы используем Onlymonster.\n\n"
        "💻 Благодаря Onlymonster наши сотрудники работают в максимально удобной и функциональной среде.\n\n"
        "👉 https://onlymonster.ai/downloads\n\n"
        "⚠️ Не регистрируйся — после обучения мы отправим пригласительную ссылку."
    )
    await bot.send_photo(chat_id, photo=open(image_path, "rb"), caption=text1)

    # 2️⃣ Видео (OnlyMonster Intro)
    video_path = IMAGES_DIR / "onlymonster_intro.mp4"  # исправлено!
    await bot.send_video(chat_id, video=open(video_path, "rb"))

    # 3️⃣ Финальный текст + кнопка
    text2 = (
        "💸 Учёт баланса — вторая ключевая задача оператора.\n\n"
        "В начале и в конце смены ты фиксируешь свой баланс в Google Таблицах.\n\n"
        "Для этого понадобится аккаунт Google — это обязательное условие."
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🤝 Теперь перейдём к работе в команде", callback_data=next_callback)
    )

    await bot.send_message(chat_id, text2, reply_markup=kb_next)

# --- После блока ПО идёт командная работа ---
@dp.callback_query_handler(lambda c: c.data == "teamwork_info_final")
async def teamwork_info_final(cq: types.CallbackQuery):
    await safe_answer(cq)

    teamwork_photo = IMAGES_DIR / "teamwork_image.jpg"
    teamwork_text = (
        "🤝 Командная работа — основа успеха, особенно в нашей сфере.\n\n"
        "🔹 Доверие — выполняй обещания, будь честен и открыт.\n"
        "🔹 Общение — решай вопросы сразу.\n"
        "🔹 Понимание ролей — знай, кто за что отвечает.\n"
        "🔹 Толерантность — уважай чужие мнения.\n"
        "🔹 Совместное развитие — делись опытом.\n"
        "🔹 Ответственность — отвечай за результат — свой и общий.\n\n"
        "💬 Командная синергия не случается сама собой — её нужно строить. Но поверь, она того стоит!"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Что дальше?", callback_data="after_teamwork_question")
    )

    teamwork_photo_path = IMAGES_DIR / "teamwork_image.jpg"
    if teamwork_photo_path.exists():
        await bot.send_photo(
            cq.from_user.id,
            photo=open(teamwork_photo_path, "rb"),
            caption=teamwork_text,
            reply_markup=kb_next
        )
    else:
        await bot.send_message(cq.from_user.id, teamwork_text, reply_markup=kb_next)
# --- Завершающий вопрос ---
@dp.callback_query_handler(lambda c: c.data == "after_teamwork_question")
async def after_teamwork_question(cq: types.CallbackQuery):
    await safe_answer(cq)

    question_text = (
        "А теперь быстрый вопрос, чтобы проверить, как ты усвоил материал 💬\n\n"
        "🙋 Куда нужно записывать балансы за начало и конец смены?"
    )

    await bot.send_message(cq.from_user.id, question_text)
    await Form.waiting_for_balance_answer.set()


# --- Ответ пользователя ---
@dp.message_handler(state=Form.waiting_for_balance_answer, content_types=types.ContentTypes.TEXT)
async def handle_balance_answer(message: types.Message, state: FSMContext):
    await state.update_data(balance_answer=message.text.strip())

    await bot.send_message(
        message.chat.id,
        "✅ Отлично! Ответ принят.\n\nТы прошёл этот блок обучения — двигаемся дальше 🚀"
    )

    # Завершаем FSM, но перед этим ловим ошибки на всякий случай
    try:
        await state.finish()
    except Exception as e:
        print(f"⚠️ Ошибка при завершении FSM: {e}")

    # ⚡ Запускаем следующий блок
    try:
        await send_objections_block(message.chat.id)
    except Exception as e:
        print(f"❌ Ошибка при запуске блока 'Возражения': {e}")
        await bot.send_message(
            message.chat.id,
            "⚠️ Произошла ошибка при загрузке следующего раздела. Попробуй ещё раз /start или сообщи администратору."
        )


# --- ФУНКЦИЯ: Блок "Возражения" ---
async def send_objections_block(chat_id: int):
    objections_img = IMAGES_DIR / "objections_intro.jpg"
    text1 = (
        "🎯 Завершаем первый блок обучения одной из ключевых тем — <b>возражения</b>.\n\n"
        "Клиенты часто не покупают сразу — и это абсолютно нормально.👌\n\n"
        "Иногда самые щедрые с первого взгляда — исчезают через день 🏃‍♂️\n\n"
        "А вот те, кто говорит «нет», часто просто ждут другого подхода.\n\n"
        "💡 Отказ — это не конец, а повод найти новый путь к продаже.\n\n"
        "Все клиенты разные: кому-то хватит двух фраз, а кому-то нужно время и внимание ⏳"
    )

    try:
        if objections_img.exists():
            with open(objections_img, "rb") as f:
                await bot.send_photo(chat_id, photo=f, caption=text1, parse_mode="HTML")
        else:
            await bot.send_message(chat_id, text1, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ Ошибка при отправке фото 'обучения возражениям': {e}")
        await bot.send_message(chat_id, text1, parse_mode="HTML")

    # --- Второе сообщение ---
    await asyncio.sleep(2)
    text2 = (
        "🔥 <b>Топ-5 возражений:</b>\n\n"
        "1. Это дорого!\n\n"
        "2. Почему я должен верить тебе?\n\n"
        "3. А ты не обманешь меня? Мне часто показывают не то, что обещают.\n\n"
        "4. У меня всего лишь 10$...\n\n"
        "5. Я не хочу ничего покупать, я хочу найти любовь."
    )
    await bot.send_message(chat_id, text2, parse_mode="HTML")

    # --- Заключительное сообщение + кнопка ---
    await asyncio.sleep(2)
    text3 = (
        "🕵️‍♂️ Теперь я покажу тебе примеры ответов на возражения.\n\n"
        "Всего будет около 18–20 инструментов — и все они реально работают 💪"
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ Это дорого!", callback_data="objection_expensive")
    )
    await bot.send_message(chat_id, text3, reply_markup=kb, parse_mode="HTML")
# --- Обработка: "Это дорого!" ---
@dp.callback_query_handler(lambda c: c.data == "objection_expensive")
async def objection_expensive(cq: types.CallbackQuery):
    await safe_answer(cq)

    text = (
        "Если клиент так пишет, чаще всего — нет <b>раппорта</b>, то есть доверия и эмоциональной связи.\n\n"
        "Клиент просто не понимает, почему он должен отдать $30 за пару фото именно тебе, а не любой другой модели.\n\n"
        "📌 <b>Как исправить?</b>\n\n"
        "Контент сам по себе не продаёт. Продаёт — описание.\n\n"
        "Клиент принимает решение, читая сообщение, а не глядя на превью.\n\n"
        "Твоя задача — включить его воображение 🧠\n\n"
        "Пусть он сам «дорисует» то, что ты не показала. Это создаёт интерес и желание.\n\n"
        "<b>Пример 1 (нейтрально и слабо):</b>\n\n"
        "🩷 <i>Милый, мои два фото поднимут тебе настроение и не только 😏</i>\n\n"
        "🚫 <u>Комментарий:</u> Клиенту непонятно, что он покупает и зачем.\n\n"
        "<b>Пример 2 (визуально, персонализировано):</b>\n\n"
        "(Имя), на первом фото я буквально обнажилась не только телом, но и душой... ещё и в твоей любимой позе. Угадаешь какая?\n\n"
        "А второе фото связано напрямую с тобой.. 😈\n\n"
        "✅ Здесь мы:\n"
        "- обращаемся по имени\n"
        "- подсказываем сюжет\n"
        "- возбуждаем фантазию\n"
        "- создаём ценность\n\n"
        "Суть: не нужно продавать фото — <b>продавай ощущение</b>, которое клиент получит. Тогда $30 не будут казаться дорогими 💸\n\n"
        "⚙️ Первые 10–20 продаж проводи через руководителя — так ты быстрее научишься правильной подаче."
    )
    await bot.send_message(cq.from_user.id, text, parse_mode="HTML")

    # 5️⃣ Следующее сообщение
    await asyncio.sleep(3)
    text2 = (
        "✍🏻 <b>Как делать продажи эффективнее?</b>\n\n"
        "Делай развёрнутое описание — это ключ к доверию.\n\n"
        "Сухое «2 фото — 30$» не вызывает эмоций.\n\n"
        "А хорошо оформленное превью повышает лояльность и вовлечённость.\n\n"
        "💬 Если клиент продолжает писать: «Это дорого...»\n\n"
        "Возможно, он ещё ни разу не покупал.\n\n"
        "В этом случае стоит не давить, а вовлечь через диалог и секстинг.\n\n"
        "<b>Секстинг</b> — это общение, где цена растёт вместе с интересом клиента ⏫\n\n"
        "Пример:\n\n"
        "(Имя), когда ты говоришь «дорого», я думаю:\n\n"
        "ты либо не уверен, что тебе понравится…\n"
        "либо сейчас просто не тот момент. Что ближе к правде? ✅"
    )
    await bot.send_message(cq.from_user.id, text2, parse_mode="HTML")

    # 6️⃣ Следующее сообщение
    await asyncio.sleep(3)
    text3 = (
        "💰 <b>Как предложить варианты?</b>\n\n"
        "Мне нравится с тобой общаться, поэтому дам выбор:\n\n"
        "👉 2 фото + видео-дразнилка за $25\n\n"
        "или\n\n"
        "👉 2–3 фото за $20, от которых твой член сойдёт с ума.\n\n"
        "Что выбираешь? 😉"
    )
    await bot.send_message(cq.from_user.id, text3, parse_mode="HTML")

    # 7️⃣ Финал — кнопка на следующее возражение
    await asyncio.sleep(3)
    text4 = (
        "🤗 Главное — эмоции.\n\n"
        "Клиенты приходят не за конфликтом, а за вниманием и лёгкостью.\n\n"
        "Усталость, раздражение, давление — они и так получают это в реальной жизни.\n\n"
        "Будь умнее: спокойствие + игривость = продажи и лояльность 😌"
    )
    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ Почему я должен верить тебе?", callback_data="objection_trust")
    )
    await bot.send_message(cq.from_user.id, text4, reply_markup=kb_next, parse_mode="HTML")


# --- Ответ на кнопку "Почему я должен верить тебе" ---
@dp.callback_query_handler(lambda c: c.data == "objection_trust")
async def objection_trust(cq: types.CallbackQuery):
    await safe_answer(cq)

    text = (
        "<b>🧠 Когда клиент пишет подобное...</b>\n\n"
        "🔹 <i>ты либо общаешься слишком навязчиво</i>\n"
        "🔹 <i>либо он провоцирует, чтобы сбить цену или набить себе значимость</i>\n\n"
        "🚫 <b>Что НЕ стоит писать:</b>\n\n"
        "- Давай я покажу тебе, что я реальная!\n"
        "- Почему ты сомневаешься?\n"
        "- Ты обижаешь меня! Как ты смеешь такое мне писать?\n"
        "- Что ты имеешь в виду? я не понимаю…\n\n"
        "❌ <i>Эти фразы — реакция, а не контроль ситуации. Они выдают неуверенность.</i>\n\n"
        "✅ <b>Что писать вместо:</b>\n\n"
        "— <i>По той же причине, по которой я доверяю тебе и верю, что наше общение, "
        "наши фотографии останутся между нами. Иначе, какой смысл общаться, если мы "
        "постоянно будем подозревать друг друга в чем-либо? Что ты думаешь об этом? 🙂</i>\n\n"
        "— <i>Ты не доверяешь мне, потому что тебя кто-то обманывал, и ты разочарован "
        "во всех женщинах на этом сайте или ты просто решил торговаться со мной насчет цены?</i>\n\n"
        "😂 <b>Такие ответы — искренние и цепляющие 🤩</b>\n\n"
        "<i>Клиент раскрывается, а ты выстраиваешь доверие и собираешь его психологический портрет ❤️</i>"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ А ты не обманешь меня ?", callback_data="objection_deceive")
    )
    await bot.send_message(cq.from_user.id, text, reply_markup=kb_next, parse_mode="HTML")

# --- Ответ на кнопку "А ты не обманешь меня ?" ---
@dp.callback_query_handler(lambda c: c.data == "objection_deceive")
async def objection_deceive(cq: types.CallbackQuery):
    await safe_answer(cq)

    text = (
        "💬 <b>«Мне часто показывают не то, что обещают…»</b>\n\n"
        "Если клиент так говорит — задай себе вопрос:\n\n"
        "почему он так думает? 🧐\n\n"
        "Скорее всего, его действительно обманывали — продавали контент, который не соответствовал описанию.\n\n"
        "И да, такое бывает часто 😢\n\n"
        "<b>Что ответить?</b>\n\n"
        "Ниже пара примеров, чтобы и разрядить обстановку, и вернуть доверие.\n\n"
        "<b>Вариант 1 (честность + логика):</b>\n\n"
        "— <i>Можно я буду с тобой откровенной? Наше общение — как игра, в которой мы оба получаем эмоции и кайф. "
        "Мне важно, чтобы ты был доволен и хотел возвращаться ко мне снова. Зачем мне обманывать тебя ради $30? "
        "Смешно, правда? 😂</i>\n\n"
        "📌 (в этот момент — напомни о превью к контенту)\n\n"
        "<b>Вариант 2 (флирт + юмор):</b>\n\n"
        "— <i>Ты не заметил, но я уже обманула тебя...</i>\n\n"
        "— <i>Что именно?</i>\n\n"
        "— <i>Я говорила, что ты просто секси... но врала. Ты ещё и слишком умный. "
        "А это опасное сочетание. Думаешь, такая малышка смогла бы обмануть тебя? 😈</i>\n\n"
        "(и 💌 отправь лёгкое, сдержанное фото в тему)\n\n"
        "📈 <b>Флирт, юмор, логика, сексуальность и лёгкая дерзость — вот инструменты, которые реально работают.</b>\n\n"
        "Если ты ими владеешь или быстро учишься — поздравляю, ты в правильной команде 🚀💋"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ У меня всего 10 $", callback_data="objection_money")
    )
    await bot.send_message(cq.from_user.id, text, reply_markup=kb_next, parse_mode="HTML")


# --- Ответ на кнопку "У меня всего 10 $" ---
@dp.callback_query_handler(lambda c: c.data == "objection_money")
async def objection_money(cq: types.CallbackQuery):
    await safe_answer(cq)

    text = (
        "❗️<b>Никогда не злись и не унижай клиента, называя его 'нищим' или 'бомжом' ❗️</b>\n\n"
        "Многие 💳 действительно обеспеченные люди прекрасно знают цену деньгам — "
        "и далеко не всегда начинают с больших трат. 💵\n\n"
        "Иногда самые щедрые — это те, кто сначала просто наблюдает.\n\n"
        "Твоя цель — не спорить, а показать, что ты — <b>ценность</b>, а не дешёвый товар.\n\n"
        "🔥 <b>Вариант 1 (мягкая провокация + уважение к себе):</b>\n\n"
        "Модель: <i>Мне приятно, что ты откровенный со мной, правда. "
        "Могу я так же быть честной с тобой? 😊</i>\n\n"
        "Клиент: “ответ”\n\n"
        "Модель: <i>Скажи мне, ты действительно думаешь, что делиться своим обнаженным телом "
        "и фантазиями с мужчиной на сайте за 10$ - это нормально? "
        "А как же флирт с леди, чаевые, азарт, сексуальность? "
        "Неужели такого мужчину, как ты, возбуждают женщины, которые за 10$ готовы показать всё? 😒</i>\n\n"
        "👑 <b>Вариант 2 (прямо, но с достоинством):</b>\n\n"
        "<i>Я не из тех женщин, которые за 10$ готовы показать все свои отверстия мужчине и написать все свои фантазии. "
        "Мне не нужны все твои деньги, но для меня важно понимать, что ты правда ценишь моё тело. "
        "Понимаешь, о чём я? 😋</i>\n\n"
        "📌 <b>Почему это работает?</b>\n\n"
        "<i>Потому что это — про цену и ценность. "
        "Ты не просишь — ты формируешь восприятие. "
        "И большинство клиентов остаются — с уважением, интересом и желанием увидеть больше… 🙌</i>"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ Я хочу найти любовь", callback_data="objection_love")
    )
    await bot.send_message(cq.from_user.id, text, reply_markup=kb_next, parse_mode="HTML")


# --- Ответ на кнопку "Я хочу найти любовь" ---
@dp.callback_query_handler(lambda c: c.data == "objection_love")
async def objection_love(cq: types.CallbackQuery):
    await safe_answer(cq)

    text = (
        "<i>“Правильно ли я тебя понимаю, что на сайте, где мужчины покупают сексуальный контент, "
        "ты хочешь найти любовь? Почему тут? Неужели в реальной жизни у тебя трудности "
        "с тем, чтобы найти достойную девушку?”</i>\n\n"
        "Одно из важнейших правил: <b>никакой любви, никаких обещаний о встречах и отношениях 🚫</b>\n\n"
        "<i>Если ты влюбишь в себя клиента, старайся дать ему понимание, что ваши отношения "
        "будут строиться только в рамках коммуникации на OnlyFans, а фактор заработка для тебя важен.</i>\n\n"
        "🧩 Пример:\n\n"
        "<i>“В смысле? Мы же любим друг-друга! Что значит — платить за контент?!”</i>\n\n"
        "В таких ситуациях стоит объяснить клиенту, что ваши отношения будут развиваться "
        "на данный момент только виртуально, а ваше время и труд всё равно должны быть оплачены, "
        "ведь это — <b>твоя работа 🧑‍💼</b>"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ Далее", callback_data="objection_next1")
    )
    await bot.send_message(cq.from_user.id, text, reply_markup=kb_next, parse_mode="HTML")


# --- Далее 1 ---
@dp.callback_query_handler(lambda c: c.data == "objection_next1")
async def objection_next1(cq: types.CallbackQuery):
    await safe_answer(cq)

    text = (
        "🏁 <b>Финишная прямая!</b>\n\n"
        "Ты уже освоил основы, теперь давай конкретно — что именно ты можешь предложить клиенту.\n\n"
        "Ниже список услуг, с которыми ты будешь работать.\n\n"
        "💼 <b>Что мы продаём:</b>\n\n"
        "👉 Секстинг — горячий диалог + контент до финала\n"
        "👉 Фото/видео — стандартные сеты\n"
        "👉 JOI-видео — инструкции для мастурбации\n"
        "👉 Кастом — индивидуальные фото/видео под запрос\n"
        "👉 Фетиш-контент — всё, что укладывается в рамки платформы\n"
        "👉 Dick-rate — оценка члена в тексте или на видео\n"
        "👉 Virtual GF — формат «виртуальной девушки» (неделя/месяц)\n"
        "👉 Видеозвонки — через Snapchat"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ Далее", callback_data="objection_next2")
    )
    await bot.send_message(cq.from_user.id, text, reply_markup=kb_next, parse_mode="HTML")


# --- Далее 2 ---
# --- Обработка кнопки "Далее 2" ---
@dp.callback_query_handler(lambda c: c.data == "objection_next2")
async def objection_next2(cq: types.CallbackQuery):
    await cq.answer()  # мгновенно отвечаем, чтобы Telegram не завис

    text = (
        "💸 <b>Клиенты могут не только покупать — но и помогать.</b>\n\n"
        "Когда с клиентом установлены тёплые отношения, у него может появиться желание сделать что-то приятное: "
        "подарок, поддержка на лечение, переезд и т.д.\n\n"
        "📌 Важно помнить: просьба остаётся просьбой, даже если она завуалирована.\n\n"
        "Наша цель — сделать так, чтобы клиент сам захотел перевести деньги и остался доволен этим решением.\n\n"
        "🎁 <b>Ситуация 1: Клиент хочет сделать подарок</b>\n\n"
        "<i>Милый, я знаю, что ты уважаешь мои личные границы так же, как и я твои. "
        "Но мне хочется открыться тебе больше, чем я могу, поэтому мне было бы приятно иметь что-то от тебя рядом со мной. "
        "Мы можем сделать так: ты выберешь для меня сюрприз, или мы сделаем это вместе, типнешь мне тут, "
        "а я пойду и куплю. А потом покажу тебе это. Что-то общее, что будет нас объединять, несмотря на километры.</i>\n\n"
        "Такой подход подчёркивает доверие, уважение и конфиденциальность 🤍"
    )

    # 👉 Кнопка "⭐ Правила платформы"
    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ Правила платформы", callback_data="rules")
    )

    await bot.send_message(
        cq.from_user.id,
        text,
        reply_markup=kb_next,
        parse_mode="HTML"
    )


# --- Обработка кнопки "⭐ Правила платформы" ---
@dp.callback_query_handler(lambda c: c.data == "rules")
async def rules(cq: types.CallbackQuery):
    
    # 🖼️ Отправляем картинку + текст
    text1 = (
        "<b>📋 Ниже будет список запретов непосредственно от OnlyFans:</b>\n\n"
        "🚫 Выставлять контент с третьими лицами (подругами, парнем, случайным прохожим), если на него не подписан модельный релиз или он не зарегистрирован на ОФ\n"
        "🚫 Любые лица моложе 18 лет или ссылки на несовершеннолетних (ролевые игры, разговоры о детстве, детские фото)\n"
        "🚫 Огнестрельное оружие, холодное оружие\n"
        "🚫 Наркотики или наркотические атрибуты\n"
        "🚫 Членовредительство или самоубийство\n"
        "🚫 Инцест (не только видео, но и текстовые ролевые игры)\n"
        "🚫 Зоофилия. Всех своих котиков и собачек лучше убрать. Были случаи, когда кошечка модели случайно попала в кадр при съемке контента, а за это страница получила предупреждение\n"
    )

    await bot.send_message(cq.from_user.id, text1, parse_mode="HTML")

    # ⏳ Ещё одна пауза
    await asyncio.sleep(1.5)

    # 🧾 Второй блок текста + кнопка
    text2 = (
        "🚫 Насилие, изнасилование, отсутствие согласия, гипноз, опьянение, сексуальное нападение, пытки, садомазохистское насилие или жесткий бондаж, экстремальный фистинг или калечащие операции на половых органах. Тут для себя понимаем, что с БДСМ контентом и играми в жестких доминаторов лучше быть аккуратнее\n\n"
        "🚫 Некрофилия\n\n"
        "🚫 Материалы, связанные с мочой, рвотой или экскрементами\n\n"
        "🚫 Эскорт-услуги, секс-торговлю или проституцию\n\n"
        "🚫 Контент, направленный на очернение, унижение, угрозы или возбуждение ненависти, страха или насилия в отношении любой группы людей или одного человека по любой причине (раса, пол, внешность и тд)\n\n"
        "🚫 Распространение личных данных, частной или конфиденциальной информации. Например, номера телефонов, информация о конкретном местоположении(просто сказать из какой вы с траны не считается,это ок), документы, адреса электронной почты, учетные данные для входа в OnlyFans, финансовую информацию(сюда входят любые попытки провести оплату вне онлика)\n\n"
        "🚫 Контент +18, если он был записан или транслируется из публичного места, где прохожие с достаточной вероятностью могут увидеть совершаемые действия (сюда не входят открытые места, где случайные прохожие не присутствуют, например частный двор, или уединенные места на природе, парк не считается😂)\n\n"
        "🚫 Используется или предназначено для использования с целью получения денег или иной выгоды от любого другого лица в обмен на удаление Контента (blackmail). Простыми словами, если вам саб скинул дикпик, а вы угрожаете скинуть его всем его друзьям если он не купит ваше ппв. Будьте осторожнее с такими фетишистами.\n\n"
        "🚫 Коммерческая деятельность для продажи третьим лицам, такие как конкурсы, тотализаторы и другие акции продаж, размещение товаров, рекламу, или размещение объявлений о работе или трудоустройстве без предварительного прямого согласия администрации сайта.\n\n"
        "🚫 Уважать права интеллектуальной собственности Создателей, в том числе не записывать, не воспроизводить, не делиться, не сообщать публике и не распространять иным образом их Контент без разрешения.\n\n"
        "🚫 Не размещайте и не создавайте условия для размещения какого-либо Содержания, которое является спамом, которое имеет намерение или эффект искусственного увеличения просмотров или взаимодействий любого Создателя, или которое является не аутентичным, повторяющимся, вводящим в заблуждение или низкокачественным.\n\n"
        "🚫 Не передавайте, не транслируйте и не отправляйте каким-либо другим способом заранее записанные аудио- или видеоматериалы во время прямого эфира и не пытайтесь выдать записанные материалы за прямой эфир.\n\n"
        "🚫 Не используйте другие средства или методы (например, использование кодовых слов или сигналов) для передачи информации, нарушающей настоящую Политику (сюда можно засунуть любимое meeeet, pay.pal, yo ung и ид)\n\n"
        "<b>⚠️ Соблюдение этих правил — твоя безопасность и стабильная работа аккаунта.</b>"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⭐ А что насчёт запретов агентства?", callback_data="rules_agency")
    )

    await bot.send_message(
        cq.from_user.id,
        text2,
        reply_markup=kb_next,
        parse_mode="HTML"
    )
# --- 2️⃣ Кнопка: "⭐ А что насчёт запретов агентства?" ---
@dp.callback_query_handler(lambda c: c.data == "rules_agency")
async def rules_agency(cq: types.CallbackQuery):
    asyncio.create_task(cq.answer())  # мгновенный ответ Telegram

    try:
        # --- Текст №1 ---
        text1 = (
            "Агентство очень ценит усердных и дисциплинированных сотрудников 💼\n\n"
            "Если ты один из них — смело переходи к следующему разделу ⏭️\n\n"
            "Но помни: за нарушение порядка и несоблюдение правил могут применяться штрафные санкции.\n\n"
            "Работаем честно — и всё будет ок! ✅"
        )
        await bot.send_message(cq.from_user.id, text1, parse_mode="HTML")

        # --- Картинка "Штрафные санкции" ---
        await asyncio.sleep(1.5)
        photo2 = IMAGES_DIR / "fines.png"

        if not photo2.exists():
            # если файла нет — показываем предупреждение один раз
            await bot.send_message(
                cq.from_user.id,
                "⚠️ Изображение 'fines.png' не найдено, пропускаем этот шаг.",
            )
        else:
            await bot.send_photo(cq.from_user.id, open(photo2, "rb"))

        # --- Текст №2 ---
        await asyncio.sleep(1.5)
        text2 = (
            "Важно понимать: штрафы — не наказание, а способ скорректировать работу ⚖️\n\n"
            "Мы не заинтересованы в их частом применении.\n\n"
            "Если человек не проявляет мотивации и не хочет работать — мы спокойно прощаемся 👋\n\n"
            "А вот если сотрудник намеренно вредит агентству — он не только увольняется, "
            "но и теряет право на выплату зарплаты 💁‍♀️\n\n"
            "<b>Честность и уважение к делу — всегда в приоритете.</b>"
        )

        kb_next = InlineKeyboardMarkup().add(
            InlineKeyboardButton("⏭️ Далее", callback_data="rules_next")
        )
        await bot.send_message(cq.from_user.id, text2, reply_markup=kb_next, parse_mode="HTML")

    except Exception as e:
        print(f"[rules_agency] Ошибка: {e}")
        await bot.send_message(cq.from_user.id, f"⚠️ Ошибка: {e}")


# --- 3️⃣ Кнопка: "⏭️ Далее" ---
@dp.callback_query_handler(lambda c: c.data == "rules_next")
async def rules_next(cq: types.CallbackQuery):
    await cq.answer()

    # 🖼️ Картинка "Причины"
    await asyncio.sleep(1.5)
    photo3 = IMAGES_DIR / "reasons.png"
    if photo3.exists():
        await bot.send_photo(cq.from_user.id, open(photo3, "rb"))

    # Финальный блок
    await asyncio.sleep(1.5)
    text3 = (
        "🎉 <b>Хорошая новость!</b>\n\n"
        "Вводная часть завершена — ты почти у финиша 🏁\n\n"
        "Осталось только одно: ознакомиться с чек-листом для работы на смене 📄\n\n"
        "Это список базовых задач, которые ты должен выполнять на каждой смене 🧑‍💻\n\n"
        "Простой, понятный и очень полезный инструмент для уверенного старта!"
    )

    kb_checklist = InlineKeyboardMarkup().add(
        InlineKeyboardButton("📋 Чек-лист", callback_data="checklist")
    )
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb_checklist, parse_mode="HTML")

class QuizStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()
    q6 = State()
    q7 = State()


# --- Обработка кнопки "📋 Чек-лист" ---
@dp.callback_query_handler(lambda c: c.data == "checklist")
async def checklist_handler(cq: types.CallbackQuery):
    await cq.answer()

    # 1️⃣ Отправляем картинку чек-листа + текст
    image_path = IMAGES_DIR / "checklist.jpg"  # убедись, что название совпадает
    caption_text = (
        "Сохрани себе этот лист, потому что у нас в “я забыл(-а)” не верят 🧡\n\n"
        "А следом пойдет табличка с минимальными ценниками на контент."
    )

    try:
        with open(image_path, "rb") as photo:
            await bot.send_photo(cq.from_user.id, photo=photo, caption=caption_text)
    except Exception as e:
        await bot.send_message(cq.from_user.id, f"⚠️ Ошибка при отправке чек-листа: {e}")

    await asyncio.sleep(1.2)

    # 2️⃣ Отправляем картинку "ценности контента"
    image_path2 = IMAGES_DIR / "content.jpg"  # проверь, правильное имя файла
    try:
        with open(image_path2, "rb") as photo2:
            await bot.send_photo(cq.from_user.id, photo=photo2)
    except Exception as e:
        await bot.send_message(cq.from_user.id, f"⚠️ Ошибка при отправке изображения ценностей: {e}")

    await asyncio.sleep(1.2)

    # 3️⃣ Сообщение с кнопкой "Старт"
    start_text = (
        "Теперь, когда ты прошёл весь материал, самое время проверить, насколько хорошо ты всё усвоил.\n\n"
        "Сейчас будет небольшой опрос по пройденному курсу — и, поверь, он покажет, как именно ты провёл это время 😉\n\n"
        "Совет: постарайся ответить на все вопросы правильно. Если не получится — увы, придётся начинать сначала 🥸 (особенно при использовании ИИ)\n\n"
        "Ну что, вперёд! Или, как говорил мой дед, — пошло-поехало."
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚀 Старт", callback_data="start_quiz"))

    await bot.send_message(cq.from_user.id, start_text, reply_markup=kb)


# --- Начало опроса ---
@dp.callback_query_handler(lambda c: c.data == "start_quiz")
async def start_quiz(cq: types.CallbackQuery, state: FSMContext):
    await cq.answer()
    await bot.send_message(
        cq.from_user.id,
        "1️⃣ После длительного общения с мужчиной ты качественно подвел его к видео и отправил его заблокированным, "
        "поставив на него цену, но мужчина не открыл видео и пишет:\n\n"
        "«Я думал ты покажешь мне это видео бесплатно, ведь мы так мило говорили, почему я должен платить за это видео?»\n\n"
        "✍️ Напиши то, что ответил бы ты:"
    )
    await QuizStates.q1.set()


# --- Последовательная обработка ответов ---
@dp.message_handler(state=QuizStates.q1)
async def quiz_q1(message: types.Message, state: FSMContext):
    await state.update_data(q1=message.text)
    await bot.send_message(
        message.chat.id,
        "2️⃣ Представь ситуацию, постоянный VIP-клиент из категории 100$-500$ не открыл платное видео, "
        "которое ты ему отправил и пишет:\n\n"
        "«Прости, детка, у меня нет денег и я не могу открыть твоё видео»\n\n"
        "✍️ Напиши то, что ответил бы ты:"
    )
    await QuizStates.q2.set()


@dp.message_handler(state=QuizStates.q2)
async def quiz_q2(message: types.Message, state: FSMContext):
    await state.update_data(q2=message.text)
    await bot.send_message(
        message.chat.id,
        "3️⃣ VIP-клиент из категории 500$-1000$ только что купил у тебя видео за 80$ и пишет:\n\n"
        "«Милая, мне нравится это видео, сделаешь для меня следующее видео бесплатно? Я думаю я заслужил это!»\n\n"
        "✍️ Напиши то, что ответил бы ты:"
    )
    await QuizStates.q3.set()


@dp.message_handler(state=QuizStates.q3)
async def quiz_q3(message: types.Message, state: FSMContext):
    await state.update_data(q3=message.text)
    await bot.send_message(
        message.chat.id,
        "4️⃣ Мужчина, с которым ты уже общаешься два дня и он ни разу не покупал контент, пишет:\n\n"
        "«Я получу деньги через несколько дней и смогу тебе заплатить! Покажешь мне твою сладкую киску сейчас, и я отдам тебе деньги позже?»\n\n"
        "✍️ Напиши то, что ответил бы ты:"
    )
    await QuizStates.q4.set()


@dp.message_handler(state=QuizStates.q4)
async def quiz_q4(message: types.Message, state: FSMContext):
    await state.update_data(q4=message.text)
    await bot.send_message(
        message.chat.id,
        "5️⃣ Клиент спрашивает у тебя — «Как дела?». Каким будет твой ответ, чтоб диалог не перешел в тупиковую форму?\n\n"
        "✍️ Напиши то, что ответил бы ты:"
    )
    await QuizStates.q5.set()


@dp.message_handler(state=QuizStates.q5)
async def quiz_q5(message: types.Message, state: FSMContext):
    await state.update_data(q5=message.text)
    await bot.send_message(
        message.chat.id,
        "6️⃣ Новый клиент открыл заблокированное видео, но оказался недовольным: "
        "«Я получил не то, о чем тебя просил. Я хочу вернуть свои деньги».\n\n"
        "Каким будет твой ответ, чтобы сохранить лояльность клиента?\n\n"
        "✍️ Напиши то, что ответил бы ты:"
    )
    await QuizStates.q6.set()


@dp.message_handler(state=QuizStates.q6)
async def quiz_q6(message: types.Message, state: FSMContext):
    await state.update_data(q6=message.text)
    await bot.send_message(
        message.chat.id,
        "7️⃣ Новый клиент только написал тебе, и уже хочет самый откровенный контент:\n\n"
        "«Хочу фотографию/видео, где будет видно всё, и чтобы ты делала это и то»\n\n"
        "✍️ Напиши то, что ответил бы ты:"
    )
    await QuizStates.q7.set()


@dp.message_handler(state=QuizStates.q7)
async def quiz_q7(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_name = data.get("name") or "Друг"  # ← достаём имя из FSM, если есть
    await state.finish()

    final_text = (
        f"Ну что ж, {user_name}, открывай бутылку Moet Chandon 🍾 — тебя можно поздравить с окончанием вводного обучения 🔥\n\n"
        "Мы с тобой отлично провели время, и думаю, тебе пора начинать делать бабки 💸\n\n"
        "Напиши рекрутеру, который передал тебе ссылку на бот (либо @eclipseagencyy, если ты нашёл бот самостоятельно), "
        "и он направит тебя к твоему администратору, с которым ты в дальнейшем будешь работать.\n\n"
        "Не скажу, что ты мне сильно понравился... Но кажется, я буду скучать 🥺\n\n"
        "Топи вперёд и порви эту сферу 🚀\n\n"
        "А главное — не забывай отправлять мне 50% своей зарплаты!\n\n"
        "Шутка 😄"
    )

    await bot.send_message(message.chat.id, final_text)


# ======================== Webhook startup/shutdown ========================
async def on_startup(dp):
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(dp):
    logger.warning("⏹️ Остановка бота...")
    try:
        await bot.delete_webhook()
    except Exception as e:
        logger.error(f"Ошибка при удалении вебхука: {e}")
    await bot.close()
    logger.info("🛑 Webhook удалён и бот остановлен.")

if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=PORT,
    )