# telegram_bot.py
import logging
import os
from pathlib import Path
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, InputFile, ParseMode
)
from dotenv import load_dotenv
from aiohttp import web

# === Настройка окружения ===
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env")

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Инициализация ===
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Папка для картинок/видео
IMAGES_DIR = Path("images")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

# --- WEB SERVER RUNNER (для Render) ---
web_runner = None  # will hold aiohttp AppRunner

async def web_index(request):
    return web.Response(text="OK — bot is running")

async def start_web_app():
    """Start aiohttp web app on PORT (Render provides PORT env var)."""
    global web_runner
    port = int(os.getenv("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", web_index)
    web_runner = web.AppRunner(app)
    await web_runner.setup()
    site = web.TCPSite(web_runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server started on 0.0.0.0:{port}")

async def stop_web_app():
    global web_runner
    if web_runner:
        try:
            await web_runner.cleanup()
            logger.info("Web server stopped")
        except Exception as e:
            logger.exception("Error stopping web server: %s", e)
        web_runner = None

# --- Состояния ---
class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_onlyfans = State()
    quiz_waiting_answer = State()
    objections_menu = State()


# --- Клавиатуры ---
btn_conditions = KeyboardButton("⭐Мне подходят условия⭐")
keyboard_conditions = ReplyKeyboardMarkup(resize_keyboard=True).add(btn_conditions)

btn_yes = KeyboardButton("Да")
btn_no = KeyboardButton("Нет")
keyboard_yes_no = ReplyKeyboardMarkup(resize_keyboard=True).add(btn_yes, btn_no)


# --- Хелперы по отправке медиа ---
def input_file_safe(path: Path):
    if path.exists():
        return InputFile(str(path))
    return None

async def send_photo_or_text(chat_id: int, image_name: str, caption: str):
    p = IMAGES_DIR / image_name
    f = input_file_safe(p)
    if f:
        await bot.send_photo(chat_id, photo=f, caption=caption, parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(chat_id, caption, parse_mode=ParseMode.HTML)


# --- Хендлер /start ---
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    # greeting with image if available
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
    if welcome_img.exists():
        await bot.send_photo(message.chat.id, photo=InputFile(str(welcome_img)), caption=caption, parse_mode=ParseMode.HTML)
    else:
        await message.answer("Добро пожаловать на обучение Eclipse Agency! 🌑\n\n" + caption, parse_mode=ParseMode.HTML)

    await bot.send_message(message.chat.id,
                           "Почему именно такие стартовые условия?\n\n"
                           "📈 Повышение процента — до 23% при выполнении KPI\n"
                           "👥 Роль Team Lead — +1% от заработка команды (3 человека)\n"
                           "🎯 Бонусы за достижения — выплаты за стабильность и инициативу\n"
                           "🚀 Карьерный рост — от оператора до администратора\n\n"
                           "Нажми кнопку ниже, если тебе подходят условия 👇",
                           reply_markup=keyboard_conditions)


# --- FSM: agree conditions ---
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

@dp.message_handler(state=Form.waiting_for_name, content_types=types.ContentTypes.TEXT)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(name=name)
    await message.answer(f"Красивое имя, {name}! 🌟\n\n{name}, ты знаком(-а) с работой на OnlyFans?",
                         reply_markup=keyboard_yes_no)
    await Form.waiting_for_onlyfans.set()

@dp.message_handler(state=Form.waiting_for_onlyfans, content_types=types.ContentTypes.TEXT)
async def process_onlyfans_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name", "друг")
    if message.text == "Да":
        await message.answer(f"Отлично, {name}! Тогда двигаться дальше будет проще ✅")
    elif message.text == "Нет":
        await message.answer(f"Ничего страшного, {name}, я всё объясню с нуля 😉")
    else:
        await message.answer("Пожалуйста, выбери: Да или Нет", reply_markup=keyboard_yes_no)
        return

    await state.finish()

    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("А как заработать?", callback_data="earn_money"))
    await bot.send_message(message.chat.id, "Теперь расскажу, как именно ты сможешь зарабатывать 💸", reply_markup=keyboard)


# --- Earn money flow ---
@dp.callback_query_handler(lambda c: c.data == "earn_money")
async def cb_earn_money(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text1 = (
        "Ещё со времён брачных агентств я научился мгновенно находить контакт и превращать любую деталь "
        "в точку опоры для продажи. Ты спросишь как? Всё просто:\n\n"
        "Узнал имя? — загуглил интересные факты.\n"
        "Ещё и фамилию? — нашёл фото, закинул шутку: «Это не ты гонял на байке в Бруклине?»\n"
        "Фан рассказал где живет? — изучаю местные фишки, подбираю тему для диалога.\n"
        "Фанат NBA? — спрашиваю про любимую команду и продолжаю разговор на знакомой волне.\n\n"
        "Любая мелочь — повод для сближения, если цель не просто продать, а завоевать доверие."
    )
    await bot.send_message(uid, text1)

    text2 = (
        "Ты будешь создавать сотни историй отношений между моделью и клиентом 🙌\n\n"
        "У каждого клиента свой интерес — твоя задача предложить то, от чего он не сможет отказаться.\n\n"
        "Формула проста:\nИнфо о фанате + верное предложение = прибыль 📈"
    )
    await bot.send_message(uid, text2)

    text3 = "Пиши клиентам каждый день, даже если они пока не готовы тратить. Когда деньги появятся — они вспомнят именно тебя ❤️‍🩹"
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Где и как искать клиентов ?", callback_data="find_clients"))
    await bot.send_message(uid, text3, reply_markup=kb)


# --- Find clients flow ---
@dp.callback_query_handler(lambda c: c.data == "find_clients")
async def cb_find_clients(cq: types.CallbackQuery):
    uid = cq.from_user.id
    # photo + caption
    caption1 = (
        "Представь, что ты на рыбалке: улов зависит от наживки. В нашем случае — это рассылка фанам.\n\n"
        "Фан уже видел сотни сообщений, сделай так, чтобы клюнул на твоё.\n\n"
        "Добавляй сленг, сокращай, меняй формулировки — главное, чтобы выглядело живо и по-своему."
    )
    await send_photo_or_text(uid, "fishing.jpg", caption1)

    text2 = (
        "Да, OnlyFans — платформа для откровенного контента, но рассылки не должны быть слишком прямыми или порнографичными 🔞\n\n"
        "Откровенный спам быстро убивает интерес. Клиенты заносят вас в список «ещё одной шлюхи» — а такие не цепляют и не вызывают желания платить 💸\n\n"
        "Работай тонко: лёгкая эротика, намёки, игра с воображением."
    )
    await bot.send_message(uid, text2)

    text3 = (
        "Мы используем 3 типа рассылок:\n\n"
        "✔️ VIP — персональные сообщения постоянным клиентам\n"
        "✔️ Онлайн — рассылка для тех, кто сейчас в сети\n"
        "✔️ Массовая — охват всех клиентов страницы, кроме VIP\n\n"
        "Каждый тип рассылки — это свой подход и шанс на продажу."
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Зачем нужны разные рассылки?", callback_data="diff_mailings"))
    await bot.send_message(uid, text3, reply_markup=kb)


# --- Diff mailings ---
@dp.callback_query_handler(lambda c: c.data == "diff_mailings")
async def cb_diff_mailings(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await send_photo_or_text(uid, "vip.jpg", "VIP-клиентам — только индивидуальные рассылки. Они платят за внимание, а не за шаблон.")
    await send_photo_or_text(uid, "online.jpg", "Если клиент сейчас онлайн — это лучший момент для рассылки. Шанс получить ответ выше.")
    await send_photo_or_text(uid, "mass.jpg", "Массовая рассылка — для всех. Пиши нейтрально и с лёгким флиртом.")
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("Я всё понял", callback_data="understood"),
        InlineKeyboardButton("Можно ещё информацию?", callback_data="understood")
    )
    await bot.send_message(uid, "Выберите:", reply_markup=kb)


# --- Understood -> continue ---
@dp.callback_query_handler(lambda c: c.data == "understood")
async def cb_understood(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await bot.send_message(uid, "🎯 Избегай банальных диалогов вроде 'Hi, how are u?'. Клиенты ценят оригинальность.")
    await bot.send_message(uid, "✅ Примеры нестандартных стартов:\n- Ого, это ты? Я тебя ждала!\n- Слушай, нужен совет! Красный или чёрный?\n- А ты когда-нибудь пробовал секс после вдоха гелия? 😉")
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Да", callback_data="questions_start"))
    await bot.send_message(uid, "Двигаемся дальше?", reply_markup=kb)


# --- Questions start (move to ПО / teamwork choice) ---
@dp.callback_query_handler(lambda c: c.data == "questions_start")
async def cb_questions_start(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await bot.send_message(uid, "Сейчас закрепим материал. Отвечай своими словами — не используй ИИ.")
    await bot.send_message(uid, "🙋 На что в первую очередь нужно опираться при общении с клиентами?")
    await bot.send_message(uid, "🙋 Можно ли в рассылках использовать слишком откровенные сообщения и почему?")
    await bot.send_message(uid, "✍️ Напиши персонализированное сообщение-рассылку клиенту: Саймон, у него 3-х летняя дочь, он любит баскетбол 🏀")

    photo = IMAGES_DIR / "teamwork.jpg"
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🌟ПО", callback_data="soft"),
        InlineKeyboardButton("🌟Командная Работа", callback_data="teamwork")
    )
    if photo.exists():
        await bot.send_photo(uid, photo=InputFile(str(photo)), caption="Теперь обсудим ПО и командную работу 🤖", reply_markup=kb)
    else:
        await bot.send_message(uid, "Теперь обсудим ПО и командную работу 🤖", reply_markup=kb)


# === ВТОРАЯ ЧАСТЬ: ПО и Командная работа ===

@dp.callback_query_handler(lambda c: c.data == "soft")
async def cb_soft(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "🟩 Для работы непосредственно на странице мы используем Onlymonster.\n\n"
        "Мы с этим браузером с самого начала — участвовали ещё в первых тестах, когда он был всего лишь расширением.\n\n"
        "Теперь это мощный инструмент, в который вложено всё, что нужно для комфортной и продуктивной работы.\n\n"
        "💻 Скачай: https://onlymonster.ai/downloads  (НЕ регистрируйся — мы отправим пригласительную ссылку после обучения)"
    )
    await bot.send_message(uid, text)
    # try to send video if exists
    video_path = IMAGES_DIR / "onlymonster_intro.mp4"
    if video_path.exists():
        await bot.send_video(uid, video=InputFile(str(video_path)), caption="Видео (8 минут) с основами работы в Onlymonster.")
    else:
        await bot.send_message(uid, "Видео с основами работы в Onlymonster (8 минут) — файл отсутствует в папке images/.")

    await bot.send_message(uid, "И вот тебе видео (на 8 минут) с основами работы в Onlymonster. Я знаю что многие не досмотрят, но досмотревшие будут иметь преимущество.")
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("А теперь поговорим о команде ?", callback_data="team_from_soft"))
    await bot.send_message(uid, "💸 Учет баланса — вторая ключевая задача оператора. Для работы нужен аккаунт Google.", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "team_from_soft")
async def cb_team_from_soft(cq: types.CallbackQuery):
    uid = cq.from_user.id
    photo = IMAGES_DIR / "team.jpg"
    caption = (
        "🤝 Командная работа — основа успеха.\n\n"
        "🔹 Доверие — выполняй обещания\n"
        "🔹 Общение — решай вопросы сразу\n"
        "🔹 Понимание ролей — знай обязанности\n"
        "🔹 Толерантность и совместное развитие\n"
        "🔹 Ответственность — отвечай за результат"
    )
    if photo.exists():
        await bot.send_photo(uid, photo=InputFile(str(photo)), caption=caption)
    else:
        await bot.send_message(uid, caption)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("⭐Что дальше?⭐", callback_data="what_next_after_soft"))
    await bot.send_message(uid, "Готовы продолжать?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "what_next_after_soft")
async def cb_what_next_after_soft(cq: types.CallbackQuery):
    uid = cq.from_user.id
    # same options as if user pressed teamwork first
    await teamwork_flow(uid)

@dp.callback_query_handler(lambda c: c.data == "teamwork")
async def cb_teamwork(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await teamwork_flow(uid)

async def teamwork_flow(uid: int):
    photo = IMAGES_DIR / "team.jpg"
    caption = (
        "🤝 Командная работа — основа успеха, особенно в нашей сфере.\n\n"
        "🔹 Доверие — выполняй обещания\n"
        "🔹 Общение — разговаривай с коллегами\n"
        "🔹 Понимание ролей — знай, кто за что отвечает\n"
        "🔹 Толерантность — уважай мнения\n"
        "🔹 Совместное развитие — делись опытом\n"
        "🔹 Ответственность — отвечай за результат"
    )
    if photo.exists():
        await bot.send_photo(uid, photo=InputFile(str(photo)), caption=caption)
    else:
        await bot.send_message(uid, caption)

    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Перейдем к ПО", callback_data="soft"))
    await bot.send_message(uid, "Перейти к ПО?", reply_markup=kb)


# === ТРЕТЬЯ ЧАСТЬ: Возражения, инструменты и финальный тест ===

# Menu for objections
@dp.callback_query_handler(lambda c: c.data == "start_objections")
async def cb_start_objections(cq: types.CallbackQuery):
    uid = cq.from_user.id
    await send_objections_menu(uid)

async def send_objections_menu(uid: int):
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
    await bot.send_message(uid, "🔥 Топ-5 возражений:\n1. Это дорого!\n2. Почему я должен верить тебе?\n3. А ты не обманешь меня?\n4. У меня всего лишь 10$...\n5. Я не хочу ничего покупать, я хочу найти любовь.\n\nВыбери пункт, чтобы получить инструменты и ответы:", reply_markup=kb)

# handle each objection callback
@dp.callback_query_handler(lambda c: c.data == "obj_expensive")
async def cb_obj_expensive(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "Если клиент пишет 'Это дорого' — чаще всего нет раппорта, доверия.\n\n"
        "Контент сам по себе не продаёт. Продаёт — описание и ощущение.\n\n"
        "Пример плохого ответа:\n"
        "Милый, мои два фото поднимут тебе настроение и не только 😏\n\n"
        "Пример сильного (персональный + сюжет):\n"
        "(Имя), на первом фото я буквально обнажилась не только телом, но и душой... ещё и в твоей любимой позе. Угадаешь какая?\n\n"
        "✅ Здесь: обращаемся по имени, подсказываем сюжет, возбуждаем фантазию, создаём ценность."
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Как предлагать варианты?", callback_data="obj_expensive_options"))
    await bot.send_message(uid, "Хочешь варианты и шаблоны?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_expensive_options")
async def cb_obj_expensive_options(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "💡 Как предлагать варианты:\n\n"
        "👉 2 фото + видео-дразнилка за $25\n"
        "👉 2–3 фото за $20\n\n"
        "Или мягкая провокация: 'Мне нравится с тобой общаться, поэтому дам выбор: что выбираешь?'"
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться в меню возражений", callback_data="start_objections"))
    await bot.send_message(uid, "Вернуться?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_trust")
async def cb_obj_trust(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "🧠 'Почему я должен верить тебе?'\n\n"
        "Не дави, не спорь. Варианты ответов:\n\n"
        "— 'По той же причине, по которой я доверяю тебе и верю, что наше общение останется между нами. Что ты думаешь об этом?'\n\n"
        "— 'Ты не доверяешь мне, потому что тебя кто-то обманывал ранее? Или ты просто торгуешься?'"
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться в меню возражений", callback_data="start_objections"))
    await bot.send_message(uid, "Вернуться?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_scam")
async def cb_obj_scam(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "💬 'А ты не обманешь меня? Мне часто показывают не то, что обещают.'\n\n"
        "Варианты ответов:\n\n"
        "1) Честность + логика:\n"
        "\"Можно я буду с тобой откровенной? Наше общение — как игра, в которой мы оба получаем эмоции и кайф. Зачем мне обманывать тебя ради $30?\" 😂\n\n"
        "2) Флирт + юмор:\n"
        "\"Ты не заметил, но я уже обманула тебя...\" — и дальше лёгкая игра."
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться в меню возражений", callback_data="start_objections"))
    await bot.send_message(uid, "Вернуться?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_10")
async def cb_obj_10(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "❗️ 'У меня всего 10$' — не злись и не унижай клиента.\n\n"
        "Вариант мягкой провокации:\n"
        "\"Мне приятно, что ты откровенный со мной. Могу я быть честной? Скажи, ты действительно думаешь, что делиться всем за $10 нормально?\""
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться в меню возражений", callback_data="start_objections"))
    await bot.send_message(uid, "Вернуться?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_love")
async def cb_obj_love(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "💌 'Я хочу найти любовь' — важный момент: никаких обещаний о реальной встрече.\n\n"
        "Ответ:\n"
        "\"Правильно ли я тебя понимаю, что на сайте, где мужчины покупают контент, ты хочешь найти любовь?\"\n\n"
        "Дальше мягко объяснить рамки: ваши отношения остаются виртуальными, и труд/время модели оплачиваются."
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться в меню возражений", callback_data="start_objections"))
    await bot.send_message(uid, "Вернуться?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_rules_platform")
async def cb_obj_rules_platform(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "🚫 Правила OnlyFans (основное):\n"
        "- Никаких лиц младше 18 лет\n"
        "- Никакого насилия/изнасилования/без согласия\n"
        "- Никакой зоофилии\n"
        "- Не публикуй чужие личные данные и т.д.\n\n"
        "Смотри на источник и помни об ограничениях."
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Правила агентства", callback_data="obj_rules_agency"))
    await bot.send_message(uid, "Перейти к правилам агентства?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_rules_agency")
async def cb_obj_rules_agency(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "Агентство ценит дисциплину. За нарушение — штрафы и возможное увольнение.\n"
        "Честность и уважение к делу — всегда в приоритете."
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Чек-лист и завершение", callback_data="obj_checklist"))
    await bot.send_message(uid, "Дальше?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_checklist")
async def cb_obj_checklist(cq: types.CallbackQuery):
    uid = cq.from_user.id
    text = (
        "🎉 Вводная часть завершена — осталось ознакомиться с чек-листом для смены.\n"
        "Чек-лист — базовые задачи на каждую смену (фиксировать баланс, работать рассылки, VIP, онлайн и массовая рассылки и т.д.)."
    )
    await bot.send_message(uid, text)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Пройти тест", callback_data="start_quiz"))
    await bot.send_message(uid, "Готов пройти тест?", reply_markup=kb)


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
    uid = cq.from_user.id
    user_quiz_data[uid] = {"q_index": 0, "answers": []}
    await bot.send_message(uid, "🔎 Тест начат. Отвечай честно, своими словами. Поехали!")
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
            f.write("Quiz results for user_id: {}\n\n".format(uid))
            for i, qa in enumerate(data["answers"], start=1):
                f.write(f"Q{i}: {qa['question']}\n")
                f.write(f"A{i}: {qa['answer']}\n\n")
        await bot.send_message(uid, "✅ Тест завершён! Спасибо за ответы.")
        await bot.send_message(uid, "Мы сохранили твои ответы. Сейчас — финальное сообщение.")
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


# --- Fallback handlers / small utilities ---
@dp.message_handler(commands=['menu'])
async def cmd_menu(message: types.Message):
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Меню возражений и тест", callback_data="start_objections"))
    await message.answer("Главное меню:", reply_markup=kb)

@dp.message_handler(lambda message: message.text and message.text.lower() in ["меню", "menu"])
async def text_menu(message: types.Message):
    await cmd_menu(message)

@dp.message_handler()
async def fallback(message: types.Message):
    # If user is in quiz state, message will be handled by that handler.
    await message.answer("Не распознал команду. Используй /start или /menu. Если хочешь пройти тест — нажми 'Пройти тест' в меню возражений.")


# === START / SHUTDOWN HOOKS FOR aiogram + aiohttp ===
async def on_startup(dp: Dispatcher):
    # Delete webhook if exists (prevents TerminatedByOtherGetUpdates)
    try:
        await bot.delete_webhook()
        logger.info("Webhook deleted (if existed).")
    except Exception as e:
        logger.warning("Failed deleting webhook: %s", e)

    # Start web server so Render sees open port
    try:
        await start_web_app()
    except Exception as e:
        logger.exception("Failed to start web app: %s", e)

async def on_shutdown(dp: Dispatcher):
    # stop web server
    try:
        await stop_web_app()
    except Exception:
        pass

    # close bot session
    try:
        await bot.session.close()
    except Exception:
        pass

# --- Запуск ---
if __name__ == '__main__':
    logger.info("Starting bot...")
    # Use on_startup/on_shutdown to run aiohttp web server concurrently with polling
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)