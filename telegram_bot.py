# telegram_bot.py
import logging
import os
from pathlib import Path
from urllib.parse import urljoin

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile, ParseMode
from aiogram.utils.exceptions import InvalidQueryID, PhotoDimensions, TelegramAPIError
from dotenv import load_dotenv

# --- Load env ---
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.onrender.com
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
RESULTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

# --- States ---
class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_onlyfans = State()
    quiz_waiting_answer = State()

# --- Helpers ---
def input_file_safe(path: Path | str):
    """Return InputFile if exists or None."""
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
    If file not found, fallback to send_message.
    """
    f = input_file_safe(photo_path)
    if not f:
        # fallback to text message
        await bot.send_message(chat_id, caption or "", reply_markup=reply_markup, parse_mode=parse_mode)
        return
    try:
        await bot.send_photo(chat_id, photo=f, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
    except PhotoDimensions:
        logger.warning("Photo invalid dimensions — sending as document instead: %s", photo_path)
        try:
            await bot.send_document(chat_id, document=f, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.exception("Failed to send document fallback: %s", e)
            await bot.send_message(chat_id, caption or "", reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramAPIError as e:
        logger.exception("Telegram API error while sending photo: %s", e)
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


# --- Agree conditions: ask name (separate message) ---
@dp.callback_query_handler(lambda c: c.data == "agree_conditions")
async def cb_agree_conditions(cq: types.CallbackQuery):
    await safe_answer(cq)

    warning_text = (
        "❗️Обрати внимание: Условие ниже не распространяется на стажировочный период (7 дней)!\n\n"
        "Если ты решишь завершить сотрудничество, потребуется отработать не более 7 дней "
        "с момента уведомления администратора."
    )
    # send warning text and then a separate prompt asking name — bot should wait for a reply
    await bot.send_message(cq.from_user.id, warning_text)
    await bot.send_message(cq.from_user.id, "Теперь давай начнём с простого — как тебя зовут?")
    await Form.waiting_for_name.set()


# --- Receive name ---
@dp.message_handler(state=Form.waiting_for_name, content_types=types.ContentTypes.TEXT)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)

    # Создаём инлайн-кнопки
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✅ Да", callback_data="onlyfans_yes"),
        types.InlineKeyboardButton("❌ Нет", callback_data="onlyfans_no")
    )

    # Отправляем сообщение с кнопками
    await bot.send_message(
        message.chat.id,
        f"Красивое имя, {name}! 🌟\n\n{name}, ты знаком(-а) с работой на OnlyFans?",
        reply_markup=keyboard
    )
    await Form.waiting_for_onlyfans.set()


@dp.callback_query_handler(lambda c: c.data in ["onlyfans_yes", "onlyfans_no"], state=Form.waiting_for_onlyfans)
async def process_onlyfans_inline(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    data = await state.get_data()
    name = data.get("name", "друг")

    if callback_query.data == "onlyfans_yes":
        await bot.send_message(callback_query.message.chat.id, f"Отлично, {name}! Тогда двигаться дальше будет проще ✅")
    else:
        await bot.send_message(callback_query.message.chat.id, f"Ничего страшного, {name}, я всё объясню с нуля 😉")

    # Отправляем блок с фото
    photo_onlyfans = IMAGES_DIR / "onlyfans_intro.jpg"
    caption1 = (
        "*OnlyFans* — это пространство, куда приходят люди за чувственным и эмоциональным контактом.\n\n"
        "В большинстве случаев речь идёт о «сексе по переписке», дополненном атмосферой тёплого диалога — о жизни, мыслях, желаниях.\n\n"
        "Да, платформа позволяет продавать разнообразный контент, но давай говорить честно: просто так никто ничего покупать не станет. "
        "Тут важно не «контент», а связь и ощущение значимости.\n\n"
        "Оборот платформы — десятки миллиардов долларов в год, а владелец получает миллиардные дивиденды, так что вопрос с деньгами тут же и закроем. Деньги здесь есть. И их много.\n\n"
        "Наша задача — может и не гнаться за всем пирогом🥧, а отрезать себе действительно достойный кусок💸"
    )
    await send_photo_with_fallback(callback_query.message.chat.id, photo_onlyfans, caption1, parse_mode=ParseMode.MARKDOWN)

    # Второй блок + кнопка "Дальше"
    text2 = (
        "Прежде чем начать обучение — запомни главное: ты не просто продаёшь контент, ты даришь людям ощущение счастья 📌\n\n"
        "С таким подходом ты не только обойдёшь конкурентов, но и почувствуешь настоящую ценность своей работы 🤙\n\n"
        "В мире полно одиноких и потерянных людей, ищущих тепло и внимание 💔\n\n"
        "Мы не можем дать им физическую любовь, но можем подарить им близость, страсть… ну и, конечно, нюдсы 😏\n\n"
        "Ладно, хватит лирики — поехали дальше! 💥"
    )
    kb_next = InlineKeyboardMarkup().add(InlineKeyboardButton("➡️ Дальше", callback_data="of_next_1"))
    await bot.send_message(callback_query.message.chat.id, text2, reply_markup=kb_next)

    # 💡 Завершаем состояние, чтобы кнопки дальше работали
    await state.finish()



@dp.callback_query_handler(lambda c: c.data == "of_next_1")
async def of_next_1(cq: types.CallbackQuery):
    await cq.answer()

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

    # безопасная отправка фото (исправление ошибки Photo_invalid_dimensions)
    try:
        with open(photo_path, "rb") as photo:
            await bot.send_photo(
                cq.from_user.id,
                photo=photo,
                caption=caption2,
                reply_markup=kb_next2,
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception as e:
        # если фото не открылось, просто шлём текст
        await bot.send_message(
            cq.from_user.id,
            caption2,
            reply_markup=kb_next2,
            parse_mode=ParseMode.MARKDOWN,
        )
        print("⚠️ Ошибка отправки фото:", e)


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

    text1 = (
        "Ещё со времён брачных агентств я научился мгновенно находить контакт и превращать любую деталь "
        "в точку опоры для продажи. Ты спросишь как? Всё просто:\n\n"
        "Узнал имя? — загуглил интересные факты.\n"
        "Ещё и фамилию? — нашёл фото, закинул шутку: «Это не ты гонял на байке в Бруклине?»\n"
        "Фан рассказал где живет? — изучаю местные фишки, подбираю тему для диалога.\n"
        "Фанат NBA? — спрашиваю про любимую команду и продолжаю разговор на знакомой волне.\n\n"
        "Любая мелочь — повод для сближения, если цель не просто продать, а завоевать доверие."
    )
    await bot.send_message(cq.from_user.id, text1)

    text2 = (
        "Ты будешь создавать сотни историй отношений между моделью и клиентом 🙌\n\n"
        "У каждого клиента свой интерес — твоя задача предложить то, от чего он не сможет отказаться.\n\n"
        "Формула проста:\nИнфо о фанате + верное предложение = прибыль 📈"
    )
    await bot.send_message(cq.from_user.id, text2)

    text3 = (
        "Пиши клиентам каждый день, даже если они в данный момент не готовы тратить. Деньги у них рано или поздно появятся — и они вспомнят именно тебя ❤️‍🩹"
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("⭐ Где и как искать клиентов? ⭐", callback_data="find_clients"))
    await bot.send_message(cq.from_user.id, text3, reply_markup=kb)


# --- find_clients ---
@dp.callback_query_handler(lambda c: c.data == "find_clients")
async def find_clients_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_path = IMAGES_DIR / "find_clients.jpg"
    caption1 = (
        "🖼 Представь, что ты на рыбалке: улов зависит от наживки. В нашем случае — это рассылка фанам.\n\n"
        "Фан уже видел сотни сообщений, сделай так, чтобы клюнул на твоё.\n\n"
        "Добавляй сленг, сокращай, меняй формулировки — главное, чтобы выглядело живо и по-своему.\n\n"
        "Например:\n\n"
        "Hey, do you mind getting to know each other? > Hey! U down to link up to me? 👋😄\n\n"
        "(Привет, не против узнать друг друга? > Хей! Не хочешь присоединится ко мне?)\n\n" 
        "Are you here for fun or are you looking for something more? > U here 4 fun or lookin’ 4 sumthin’ more? 😄\n\n"
        "(Ты здесь для развлечения или ищешь что-то большее?)\n\n"

    )
    await send_photo_with_fallback(cq.from_user.id, photo_path, caption=caption1)

    text2 = (
        "Да, OnlyFans — платформа для откровенного контента, но рассылки не должны быть слишком прямыми или порнографичными 🔞\n\n"
        "Откровенный спам быстро убивает интерес. Клиенты заносят вас в список «ещё одной шлюхи» — а такие не цепляют и не вызывают желания платить 💸\n\n"
        "Работай тонко: лёгкая эротика, намёки, игра с воображением. Пусть его фантазия доделает остальное 💡"
    )
    await bot.send_message(cq.from_user.id, text2)

 # --- Рассылка с кнопкой ---
@dp.callback_query_handler(lambda c: c.data == "of_next_3")  # можешь поменять на нужный callback
async def send_diff_intro(cq: types.CallbackQuery):
    await safe_answer(cq)

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



# --- diff_mailings ---
@dp.callback_query_handler(lambda c: c.data == "diff_mailings")
async def diff_mailings_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_vip = IMAGES_DIR / "vip.jpg"
    caption_vip = (
        "Рассылка подбирается под тип клиента 💬\n\n"
        "VIP-клиентам — только индивидуальные рассылки.\n\n"
        "Они платят за внимание, а не за шаблон. Проявляй интерес, вспоминай прошлые темы, держи связь 👀\n\n"
        "Например, обсуждали 'Hogwarts Legacy'? Загугли что-то прикольное и напиши:\n\n"
        "«Ты уже видел танцующего эльфа в тазике? Надеюсь, не пропустил этот момент! Только не шути, что он — это я в ванной 😂»\n\n"
        "Уловил суть? VIP клиент должен получать рассылку, привязанную исключительно к уже состоявшимся диалогам ранее."
    )
    await send_photo_with_fallback(cq.from_user.id, photo_vip, caption=caption_vip)

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Далее", callback_data="diff_online")
    )
    await bot.send_message(cq.from_user.id, "Продолжим?", reply_markup=kb_next)


# --- diff_online ---
@dp.callback_query_handler(lambda c: c.data == "diff_online")
async def diff_online_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_online = IMAGES_DIR / "online.jpg"
    caption_online = (
        "Если клиент сейчас онлайн — это лучший момент для рассылки 💬\n\n"
        "Шанс получить ответ выше, поэтому цепляйся за его ник или аватар — это уже элемент персонализации.\n\n"
        "Если ты уже пробовал такой подход раньше — не беда, просто заходи с другой стороны.\n\n"
        "Пример:\n\n"
        "“Я точно нашла тебя вне сайта! Хотя после часа поисков руки опустились… Таких ников слишком много 😪 А мне правда важно быть на связи с фанатами, как ты ❤️”\n\n"
        "Здесь мы:\n\n"
        "🔹 Заманили ярким началом\n"
        "🔹 Объяснили, почему 'искали'\n"
        "🔹 Ушли от темы мессенджеров — ведь фанаты важны нам именно здесь."
    )
    await send_photo_with_fallback(cq.from_user.id, photo_online, caption=caption_online)

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Массовая рассылка", callback_data="diff_mass")
    )
    await bot.send_message(cq.from_user.id, "Двигаемся дальше?", reply_markup=kb_next)


# --- diff_mass ---
@dp.callback_query_handler(lambda c: c.data == "diff_mass")
async def diff_mass_info(cq: types.CallbackQuery):
    await safe_answer(cq)

    photo_mass = IMAGES_DIR / "mass.jpg"
    caption_mass = (
        "Массовая рассылка летит всем, поэтому её нужно строить так, чтобы зацепить любого, но не отпугнуть тех, с кем ты уже общался(-ась) 📝\n\n"
        "Темы могут быть любые — от бытового до лёгкой эротики, но без перебора, чтобы не скатиться в образ «ещё одной шлюхи» ☝️\n\n"
        "Если не хватает фантазии — обратись к новостям:\n\n"
        "“БОЛЬШОЙ крах банка! Слышал? Один из крупнейших банков США обанкротился. Надеюсь, тебя это не задело 🤞”\n\n"
        "Либо же с уклоном в эротику:\n\n"
        "«Ur fingers been here b4? 😏 Just wonderin’…» + фото модели\n\n"
        "(Ваши пальцы уже были здесь? 😏 Просто интересно)\n\n"
        "Фан сможет увидеть до 25 символов в листе чатов, поэтому старайся в эти 25 символов ставить самую 'байтовую' часть своего сообщения."
    )

    kb_mass = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🌟 Я всё понял! 🌟", callback_data="mailing_done"),
        InlineKeyboardButton("🌟 Можно ещё информации? 🌟", callback_data="mailing_done")
    )

    await send_photo_with_fallback(cq.from_user.id, photo_mass, caption=caption_mass, reply_markup=kb_mass)


# --- После выбора любой кнопки ---
@dp.callback_query_handler(lambda c: c.data == "mailing_done")
async def mailing_done(cq: types.CallbackQuery, state: FSMContext):
    await safe_answer(cq)

    text4 = (
        "🎯 Наша цель — дать тебе максимум полезной информации. Сегодня — о банальности в диалоге.\n\n"
        "Как большинство моделей начинают общение в чате?\n\n"
        "\"Hi. How are u?\" — классика. Но теперь представь, что ты уже 25-я, кто это спросил, "
        "а у него, как у того самого котика из тиктока — всё заебись... 👍\n\n"
        "🛑 СТОП!\n\n"
        "Стандартное приветствие = стандартные ожидания. А значит — клиент жмёт 'назад'."
    )
    await bot.send_message(cq.from_user.id, text4)

    text5 = (
        "✅ Как быть? Нарушай правила. Будь запоминающейся.\n\n"
        "Клиенты платят за уникальность — не за дежурное 'привет'.\n\n"
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
        "🙅‍♀️ Потому что когда ты пишешь 'How are you?', чаще всего слышишь:\n\n"
        "'I'm OK.'\n\n"
        "И всё. А дальше?\n\n"
        "Ничего. 💀"
    )

    kb_next = InlineKeyboardMarkup().add(
        InlineKeyboardButton("➡️ Двигаемся дальше?", callback_data="after_mailing_next")
    )

    await bot.send_message(cq.from_user.id, text6, reply_markup=kb_next)


# --- after_mailing_next ---
@dp.callback_query_handler(lambda c: c.data == "after_mailing_next")
async def after_mailing_next(cq: types.CallbackQuery, state: FSMContext):
    await safe_answer(cq)

    text7 = (
        "Сейчас нам важно закрепить ту часть информации, которую ты уже успел усвоить. "
        "После каждого блока я буду задавать тебе несколько вопросов — это поможет тебе лучше всё запомнить "
        "и уверенно двигаться дальше.\n\n"
        "⚠️ Но сразу хочу предупредить:\n\n"
        "Мы легко определяем, когда кто-то проходит обучение с помощью ИИ. "
        "И поверь, всех, кто так делает, мы отправляем на повтор до тех пор, пока ответы не станут живыми и осознанными.\n\n"
        "💡 В твоих же интересах — отвечать от себя, своими словами и мыслями. "
        "Это не только ускорит процесс, но и поможет тебе быстрее начать реально зарабатывать 💸"
    )

    await bot.send_message(cq.from_user.id, text7)

    question = "🙋 На что в первую очередь нужно опираться при общении с клиентами?"
    await bot.send_message(cq.from_user.id, question)

    await state.set_state("waiting_for_question_1")


# === Обработчики меню возражений (содержимое сохранено) ===
@dp.callback_query_handler(lambda c: c.data == "start_objections")
async def cb_start_objections(cq: types.CallbackQuery):
    await safe_answer(cq)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Это дорого!", callback_data="obj_expensive"),
        InlineKeyboardButton("Почему я должен верить тебе?", callback_data="obj_trust"),
        InlineKeyboardButton("А ты не обманешь меня?", callback_data="obj_scam"),
        InlineKeyboardButton("У меня всего 10$", callback_data="obj_10"),
        InlineKeyboardButton("Я хочу найти любовь", callback_data="obj_love"),
        InlineKeyboardButton("Правила платформы", callback_data="obj_rules_platform"),
        InlineKeyboardButton("Запреты агентства", callback_data="obj_rules_agency"),
        InlineKeyboardButton("Чек-лист", callback_data="obj_checklist"),
        InlineKeyboardButton("Пройти тест", callback_data="start_quiz")
    )
    text = (
        "🔥 Топ-5 возражений:\n"
        "1. Это дорого!\n2. Почему я должен верить тебе?\n3. А ты не обманешь меня?\n4. У меня всего лишь 10$...\n5. Я не хочу ничего покупать, я хочу найти любовь.\n\n"
        "Выбери пункт, чтобы получить инструменты и ответы:"
    )
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_expensive")
async def cb_obj_expensive(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "Если клиент пишет 'Это дорого' — чаще всего нет раппорта, доверия.\n\n"
        "Контент сам по себе не продаёт. Продаёт — описание и ощущение.\n\n"
        "Пример слабого ответа:\nМилый, мои два фото поднимут тебе настроение и не только 😏\n\n"
        "Пример сильного (персональный + сюжет):\n(Имя), на первом фото я буквально обнажилась не только телом, но и душой... ещё и в твоей любимой позе. Угадаешь какая?"
    )
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Как предлагать варианты?", callback_data="obj_expensive_options"),
        InlineKeyboardButton("Вернуться", callback_data="start_objections")
    )
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_expensive_options")
async def cb_obj_expensive_options(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "💡 Как предлагать варианты:\n\n"
        "👉 2 фото + видео-дразнилка за $25\n"
        "👉 2–3 фото за $20\n\n"
        "Или мягкая провокация: 'Мне нравится с тобой общаться, поэтому дам выбор: что выбираешь?'"
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_trust")
async def cb_obj_trust(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "🧠 'Почему я должен верить тебе?'\n\n"
        "Варианты ответов:\n"
        "— 'По той же причине, по которой я доверяю тебе и верю, что наше общение останется между нами. Что ты думаешь об этом?'\n"
        "— 'Ты не доверяешь мне, потому что тебя кто-то обманывал ранее? Или ты просто торгуешься?'"
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_scam")
async def cb_obj_scam(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "💬 'А ты не обманешь меня? Мне часто показывают не то, что обещают.'\n\n"
        "Варианты ответов:\n\n"
        "1) Честность + логика:\n"
        "\"Можно я буду с тобой откровенной? Наше общение — как игра, в которой мы оба получаем эмоции и кайф. Зачем мне обманывать тебя ради $30?\" 😂\n\n"
        "2) Флирт + юмор:\n"
        "\"Ты не заметил, но я уже обманула тебя...\" — и дальше лёгкая игра."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_10")
async def cb_obj_10(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "❗️ 'У меня всего 10$' — не злись и не унижай клиента.\n\n"
        "Вариант мягкой провокации:\n"
        "\"Мне приятно, что ты откровенный со мной. Могу я быть честной? Скажи, ты действительно думаешь, что делиться всем за $10 нормально?\""
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_love")
async def cb_obj_love(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "💌 'Я хочу найти любовь' — важный момент: никаких обещаний о реальной встрече.\n\n"
        "\"Правильно ли я тебя понимаю, что на сайте, где мужчины покупают контент, ты хочешь найти любовь?\"\n\n"
        "Дальше мягко объяснить рамки: ваши отношения остаются виртуальными, и труд/время модели оплачиваются."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_rules_platform")
async def cb_obj_rules_platform(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "🚫 Правила OnlyFans (основное):\n"
        "- Никаких лиц младше 18 лет\n"
        "- Никакого насилия/изнасилования/без согласия\n"
        "- Никакой зоофилии\n"
        "- Не публикуй чужие личные данные и т.д.\n\n"
        "Смотри на источник и помни об ограничениях."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Правила агентства", callback_data="obj_rules_agency"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_rules_agency")
async def cb_obj_rules_agency(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "Агентство ценит дисциплину. За нарушение — штрафы и возможное увольнение.\n"
        "Честность и уважение к делу — всегда в приоритете."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Чек-лист и завершение", callback_data="obj_checklist"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "obj_checklist")
async def cb_obj_checklist(cq: types.CallbackQuery):
    await safe_answer(cq)
    text = (
        "🎉 Вводная часть завершена — осталось ознакомиться с чек-листом для смены.\n"
        "Чек-лист — базовые задачи на каждую смену (фиксировать баланс, работать рассылки, VIP, онлайн и массовая рассылки и т.д.)."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Пройти тест", callback_data="start_quiz"))
    await bot.send_message(cq.from_user.id, text, reply_markup=kb)


# === QUIZ / TEST SEQUENCE ===
QUIZ_QUESTIONS = [
    "🙋 На что в первую очередь нужно опираться при общении с клиентами?",
    "🙋 Можно ли в рассылках использовать слишком откровенные сообщения и почему?",
    "✍️ Напиши персонализированное сообщение-рассылку клиенту. (Пример: Саймон, у него 3-х летняя дочь, и он увлекается баскетболом.)",
    "После длительного общения с мужчиной ты отправил заблокированное видео, он пишет: 'Я думал ты покажешь мне бесплатно...' — как ответишь?",
    "VIP 100-500$ не открыл платное видео, пишет: 'У меня нет денег' — что ответишь?",
    "VIP 500-1000$ купил видео за $80 и просит бесплатное — как ответишь?",
    "Клиент: 'Я получу деньги через несколько дней, покажешь бесплатно?' — что ответишь?",
    "Клиент: 'Как дела?' — какой ответ, чтобы диалог не застрял?",
    "Новый клиент открыл заблокированное видео и недоволен — хочет возврат. Как сохранить лояльность?",
    "Клиент хочет видео, которое модель не делает (наездница с дилдо) — как перенаправить на другую покупку?",
    "Новый клиент сразу требует самый откровенный контент — как ответишь?"
]

user_quiz_data = {}  # user_id -> {"q_index": int, "answers": []}

@dp.callback_query_handler(lambda c: c.data == "start_quiz")
async def cb_start_quiz(cq: types.CallbackQuery):
    await safe_answer(cq)
    uid = cq.from_user.id
    user_quiz_data[uid] = {"q_index": 0, "answers": []}
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Отмена", callback_data="start_objections"))
    await bot.send_message(uid, "🔎 Тест начат. Отвечай честно, своими словами. Поехали!", reply_markup=kb)
    await bot.send_message(uid, QUIZ_QUESTIONS[0])
    await Form.quiz_waiting_answer.set()


@dp.message_handler(state=Form.quiz_waiting_answer, content_types=types.ContentTypes.TEXT)
async def process_quiz_answer(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = user_quiz_data.get(uid)
    if not data:
        await message.answer("Тест не начат. Нажми 'Пройти тест' в меню.")
        await state.finish()
        return

    q_index = data["q_index"]
    ans = message.text.strip()
    data["answers"].append({"question": QUIZ_QUESTIONS[q_index], "answer": ans})
    q_index += 1
    data["q_index"] = q_index
    user_quiz_data[uid] = data

    if q_index < len(QUIZ_QUESTIONS):
        await bot.send_message(uid, QUIZ_QUESTIONS[q_index])
        return
    else:
        await state.finish()
        save_path = RESULTS_DIR / f"{uid}_answers.txt"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(f"Quiz results for user_id: {uid}\n\n")
            for i, qa in enumerate(data["answers"], start=1):
                f.write(f"Q{i}: {qa['question']}\nA{i}: {qa['answer']}\n\n")
        await bot.send_message(uid, "✅ Тест завершён! Спасибо за ответы.")
        user_name = message.from_user.first_name or "друг"
        final_text = (
            f"Ну что ж, {user_name}, открывай бутылку Moet Chandon 🍾 — поздравляю с окончанием вводного обучения 🔥\n\n"
            "Мы с тобой отлично провели время и думаю тебе пора начинать зарабатывать 💸\n\n"
            "Напиши рекрутеру, который передал тебе ссылку на бот (либо @loco_hr, если ты нашёл бот самостоятельно), "
            "и он направит тебя к твоему администратору.\n\n"
            "Топи вперёд и порви эту сферу 🚀\n\n"
            "Шутка: не забывай отправлять мне 50% своей зарплаты 😉"
        )
        await bot.send_message(uid, final_text)
        user_quiz_data.pop(uid, None)


# --- small menu handlers & fallback ---
@dp.message_handler(commands=['menu'])
async def cmd_menu(message: types.Message):
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Меню возражений и тест", callback_data="start_objections"))
    await message.answer("Главное меню:", reply_markup=kb)

@dp.message_handler(lambda message: message.text and message.text.lower() in ["меню", "menu"])
async def text_menu(message: types.Message):
    await cmd_menu(message)

@dp.message_handler()
async def fallback(message: types.Message):
    # catches plain messages when not in FSM states or unknown commands
    await message.answer("Не распознал команду. Используй /start или /menu. Если хочешь пройти тест — открой меню возражений.")


# ======================== Webhook startup/shutdown ========================
async def on_startup(dp: Dispatcher):
    # ensure no previous webhook
    try:
        await bot.delete_webhook()
        logger.info("Old webhook deleted (if existed).")
    except Exception:
        logger.debug("Failed deleting webhook (ignored).")

    # set webhook to full path: BASE_URL + WEBHOOK_PATH
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")


async def on_shutdown(dp: Dispatcher):
    # remove webhook and close
    try:
        await bot.delete_webhook()
    except Exception:
        logger.debug("Failed deleting webhook on shutdown.")
    try:
        await bot.close()
    except Exception:
        logger.debug("bot.close() failed (ignored).")


if __name__ == '__main__':
    # start webhook server (Render will provide PORT)
    executor.start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host='0.0.0.0',
        port=PORT,
    )
