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

load env

load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # full public URL e.g. https://app.onrender.com/webhook/
<TOKEN>
PORT = int(os.getenv("PORT", "10000"))

if not API_TOKEN:
raise RuntimeError("BOT_TOKEN not set in .env")
if not WEBHOOK_URL:
raise RuntimeError("WEBHOOK_URL not set in .env — required for webhook mode (Render)")

logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(name)

init bot & dispatcher

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

directories

IMAGES_DIR = Path("images")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

states

class Form(StatesGroup):
waiting_for_name = State()
waiting_for_onlyfans = State()
quiz_waiting_answer = State()

helper to create inline keyboards compact (row_width=2)

def make_kb(*rows):
"""
rows = list of tuples/lists of (text, callback_data)
returns InlineKeyboardMarkup with row_width=2
"""
kb = InlineKeyboardMarkup(row_width=2)
for row in rows:
# row can be sequence of pairs or a single pair
if all(isinstance(x, (list, tuple)) and len(x) == 2 for x in row):
buttons = [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
kb.row(*buttons)
else:
# fallback: treat row as list of pairs
buttons = [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
kb.row(*buttons)
return kb

def input_file_safe(path: Path):
if path.exists():
return InputFile(str(path))
return None

----------------- Handlers / Flows -----------------

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
    await bot.send_photo(chat_id=message.chat.id, photo=InputFile(str(welcome_img)),
                         caption=caption + "\n\n" + intro_text, parse_mode=ParseMode.HTML,
                         reply_markup=kb)
else:
    await bot.send_message(chat_id=message.chat.id, text=caption + "\n\n" + intro_text,
                           parse_mode=ParseMode.HTML, reply_markup=kb)

Agree conditions -> ask name

@dp.callback_query_handler(lambda c: c.data == "agree_conditions")
async def cb_agree_conditions(cq: types.CallbackQuery):
await cq.answer() # acknowledge callback
text = (
"❗️Обрати внимание: Условие ниже не распространяется на стажировочный период (7 дней)!\n\n"
"— Если ты решишь завершить сотрудничество, потребуется отработать не более 7 дней "
"с момента уведомления администратора.\n\n"
"Теперь давай начнём с простого — как тебя зовут?"
)
await bot.send_message(cq.from_user.id, text)
await Form.waiting_for_name.set()

receive name, ask about OnlyFans (using inline Yes/No)

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

# next button inline
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("А как заработать?", callback_data="earn_money"))
await bot.send_message(cq.from_user.id, "Теперь расскажу, как именно ты сможешь зарабатывать 💸", reply_markup=kb)

Earn money flow

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

Find clients flow (photo + text + button in same message where applicable)

@dp.callback_query_handler(lambda c: c.data == "find_clients")
async def cb_find_clients(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
caption1 = (
"Представь, что ты на рыбалке: улов зависит от наживки. У нас — это рассылка фанам.\n\n"
"Добавляй живость, сленг, индивидуальность, чтобы выделяться 👇"
)
photo = input_file_safe(IMAGES_DIR / "fishing.jpg")
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Зачем нужны разные рассылки?", callback_data="diff_mailings"))
if photo:
await bot.send_photo(uid, photo=photo, caption=caption1, reply_markup=kb)
else:
await bot.send_message(uid, caption1, reply_markup=kb)

Diff mailings — send 3 messages but each with its own inline buttons placed in same message where needed

@dp.callback_query_handler(lambda c: c.data == "diff_mailings")
async def cb_diff_mailings(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
await send_photo_with_buttons(uid, "vip.jpg", "VIP-клиентам — только индивидуальные рассылки. Они платят за внимание, а не за шаблон.",
[("Я всё понял", "understood"), ("Можно ещё информацию?", "understood")])
await send_photo_or_text_with_buttons(uid, "online.jpg", "Если клиент онлайн — идеальный момент для рассылки!", [])
await send_photo_or_text_with_buttons(uid, "mass.jpg", "Массовая рассылка — для всех. Пиши нейтрально, с лёгким флиртом 😉",
[("Я всё понял", "understood")])

@dp.callback_query_handler(lambda c: c.data == "understood")
async def cb_understood(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"🎯 Избегай банальных диалогов вроде 'Hi, how are u?'. Клиенты ценят оригинальность.\n\n"
"✅ Примеры нестандартных стартов:\n"
"- Ого, это ты? Я тебя ждала!\n"
"- Слушай, нужен совет! Красный или чёрный?\n"
"- А ты пробовал секс после вдоха гелия? 😉"
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Двигаемся дальше?", callback_data="questions_start"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "questions_start")
async def cb_questions_start(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
# ask knowledge checks
kb = InlineKeyboardMarkup(row_width=2).add(
InlineKeyboardButton("🌟ПО", callback_data="soft"),
InlineKeyboardButton("🌟Командная Работа", callback_data="teamwork")
)
photo = input_file_safe(IMAGES_DIR / "teamwork.jpg")
caption = "Теперь обсудим ПО и командную работу 🤖"
if photo:
await bot.send_photo(uid, photo=photo, caption=caption, reply_markup=kb)
else:
await bot.send_message(uid, caption, reply_markup=kb)

--- ПО (Onlymonster) flow ---

@dp.callback_query_handler(lambda c: c.data == "soft")
async def cb_soft(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"🟩 Для работы непосредственно на странице мы используем Onlymonster.\n\n"
"Мы с этим браузером с самого начала — участвовали ещё в первых тестах.\n\n"
"💻 Скачай: https://onlymonster.ai/downloads\n\n
"
"<b>ВАЖНО:</b> не регистрируйся — после обучения мы отправим пригласительную ссылку."
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("А теперь поговорим о команде ?", callback_data="team_from_soft"))
video = input_file_safe(IMAGES_DIR / "onlymonster_intro.mp4")
# send text+button in single message
await bot.send_message(uid, text, parse_mode=ParseMode.HTML, reply_markup=kb)
# then send video (if exists), also with caption as single block
if video:
kb2 = InlineKeyboardMarkup().add(InlineKeyboardButton("💸 Учет баланса — дальше", callback_data="balance_info"))
await bot.send_video(uid, video=video, caption="Видео (8 минут) с основами работы в Onlymonster.", reply_markup=kb2)
else:
await bot.send_message(uid, "Видео (8 минут) с основами работы в Onlymonster отсутствует в папке images/.",
reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("💸 Учет баланса — дальше", callback_data="balance_info")))

@dp.callback_query_handler(lambda c: c.data == "balance_info")
async def cb_balance_info(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"💸 Учет баланса — вторая ключевая задача оператора, наряду с продажами.\n\n"
"🟩 Мы используем Google Таблицы. Всё просто: в начале и в конце смены ты фиксируешь свой баланс.\n\n"
"Для работы понадобится аккаунт Google — это обязательное условие."
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("А теперь поговорим о команде ?", callback_data="team_from_soft"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "team_from_soft")
async def cb_team_from_soft(cq: types.CallbackQuery):
await cq.answer()
await teamwork_flow(cq.from_user.id, followup_button=True)

@dp.callback_query_handler(lambda c: c.data == "teamwork")
async def cb_teamwork(cq: types.CallbackQuery):
await cq.answer()
await teamwork_flow(cq.from_user.id, followup_button=False)

async def teamwork_flow(uid: int, followup_button: bool = False):
photo = input_file_safe(IMAGES_DIR / "team.jpg")
caption = (
"🤝 Командная работа — основа успеха, особенно в нашей сфере.\n\n"
"🔹 Доверие — выполняй обещания\n"
"🔹 Общение — разговаривай с коллегами\n"
"🔹 Понимание ролей — знай, кто за что отвечает\n"
"🔹 Толерантность — уважай чужие мнения\n"
"🔹 Совместное развитие — делись опытом\n"
"🔹 Ответственность — отвечай за результат"
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Перейдем к ПО", callback_data="soft"))
if photo:
await bot.send_photo(uid, photo=photo, caption=caption, reply_markup=kb if followup_button else kb)
else:
await bot.send_message(uid, caption, reply_markup=kb)

---------------- Objections / tools / quiz ----------------

@dp.callback_query_handler(lambda c: c.data == "start_objections")
async def cb_start_objections(cq: types.CallbackQuery):
await cq.answer()
await send_objections_menu(cq.from_user.id)

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
text = (
"🔥 Топ-5 возражений:\n"
"1. Это дорого!\n2. Почему я должен верить тебе?\n3. А ты не обманешь меня?\n4. У меня всего лишь 10$...\n5. Я не хочу ничего покупать, я хочу найти любовь.\n\n"
"Выбери пункт, чтобы получить инструменты и ответы:"
)
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_expensive")
async def cb_obj_expensive(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"Если клиент пишет 'Это дорого' — чаще всего нет раппорта, доверия.\n\n"
"Контент сам по себе не продаёт. Продаёт — описание и ощущение.\n\n"
"Пример слабого ответа:\nМилый, мои два фото поднимут тебе настроение и не только 😏\n\n"
"Пример сильного (персональный + сюжет):\n(Имя), на первом фото я буквально обнажилась не только телом, но и душой... ещё и в твоей любимой позе. Угадаешь какая?"
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Как предлагать варианты?", callback_data="obj_expensive_options"),
InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_expensive_options")
async def cb_obj_expensive_options(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"💡 Как предлагать варианты:\n\n"
"👉 2 фото + видео-дразнилка за $25\n"
"👉 2–3 фото за $20\n\n"
"Или мягкая провокация: 'Мне нравится с тобой общаться, поэтому дам выбор: что выбираешь?'"
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_trust")
async def cb_obj_trust(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"🧠 'Почему я должен верить тебе?'\n\n"
"Варианты ответов:\n"
"— 'По той же причине, по которой я доверяю тебе и верю, что наше общение останется между нами. Что ты думаешь об этом?'\n"
"— 'Ты не доверяешь мне, потому что тебя кто-то обманывал ранее? Или ты просто торгуешься?'"
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_scam")
async def cb_obj_scam(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"💬 'А ты не обманешь меня?'\n\n"
"1) Честность + логика:\n"
""Можно я буду с тобой откровенной? Наше общение — как игра, в которой мы оба получаем эмоции и кайф. Зачем мне обманывать тебя?" 😂\n\n"
"2) Флирт + юмор — лёгкая игра, возвращающая доверие."
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_10")
async def cb_obj_10(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"❗️ 'У меня всего 10$' — не злись и не унижай клиента.\n"
"Вариант мягкой провокации:\n"
""Мне приятно, что ты откровенный со мной. Могу я быть честной? Скажи, ты действительно думаешь, что делиться всем за $10 нормально?""
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_love")
async def cb_obj_love(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"💌 'Я хочу найти любовь' — объясняем рамки: ваши отношения остаются виртуальными, "
"и труд/время модели оплачиваются. Никаких обещаний о реальных встречах."
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_rules_platform")
async def cb_obj_rules_platform(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"🚫 Правила OnlyFans (основное):\n"
"- Никаких лиц младше 18 лет\n"
"- Никакого насилия/изнасилования/без согласия\n"
"- Никакой зоофилии\n"
"- Не публикуй чужие личные данные и т.д."
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Правила агентства", callback_data="obj_rules_agency"),
InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_rules_agency")
async def cb_obj_rules_agency(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"Агентство очень ценит усердных и дисциплинированных сотрудников.\n\n"
"За нарушение порядка и несоблюдение правил могут применяться штрафные санкции."
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Чек-лист", callback_data="obj_checklist"),
InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "obj_checklist")
async def cb_obj_checklist(cq: types.CallbackQuery):
await cq.answer()
uid = cq.from_user.id
text = (
"🎉 Вводная часть завершена — осталось ознакомиться с чек-листом для смены.\n\n"
"Чек-лист — базовые задачи, которые нужно выполнять на каждой смене."
)
kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Пройти тест", callback_data="start_quiz"),
InlineKeyboardButton("Вернуться", callback_data="start_objections"))
await bot.send_message(uid, text, reply_markup=kb)

---------------- QUIZ ----------------

QUIZ_QUESTIONS = [
"🙋 На что в первую очередь нужно опираться при общении с клиентами?",
"🙋 Можно ли в рассылках использовать слишком откровенные сообщения и почему?",
"✍️ Напиши персонализированное сообщение-рассылку клиенту. (Пример: Саймон, у него 3-х летняя дочь, и он увлекается баскетболом.)",
"После длительного общения ты отправил заблокированное видео, он пишет: 'Я думал ты покажешь мне бесплатно...' — как ответишь?",
"VIP 100-500$ не открыл платное видео, пишет: 'У меня нет денег' — что ответишь?",
"VIP 500-1000$ купил видео за $80 и просит бесплатное — как ответишь?",
"Клиент: 'Я получу деньги через несколько дней, покажешь бесплатно?' — что ответишь?",
"Клиент: 'Как дела?' — какой ответ, чтобы диалог не застрял?",
"Новый клиент открыл заблокированное видео и недоволен — хочет возврат. Как сохранить лояльность?",
"Клиент хочет видео, которое модель не делает — как перенаправить на покупку другого контента?",
"Новый клиент сразу требует самый откровенный контент — как ответишь?"
]

user_quiz_data = {} # uid -> {"q_index": int, "answers": []}

@dp.callback_query_handler(lambda c: c.data == "start_quiz")
async def cb_start_quiz(cq: types.CallbackQuery):
await cq.answer()
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
        "Напиши рекрутеру, который передал тебе ссылку на бот (либо @loco_hr), и он направит тебя к администратору."
    )
    await bot.send_message(uid, final_text)
    user_quiz_data.pop(uid, None)

---------------- utilities ----------------

async def send_photo_with_buttons(uid: int, image_name: str, caption: str, buttons: list):
"""
buttons: list of (text, callback)
sends photo with caption and inline buttons (if image exists), otherwise sends text with buttons
"""
photo = input_file_safe(IMAGES_DIR / image_name)
kb = InlineKeyboardMarkup(row_width=2)
for t, c in buttons:
kb.add(InlineKeyboardButton(t, callback_data=c))
if photo:
await bot.send_photo(uid, photo=photo, caption=caption, reply_markup=kb if buttons else None)
else:
await bot.send_message(uid, caption, reply_markup=kb if buttons else None)

async def send_photo_or_text_with_buttons(uid: int, image_name: str, caption: str, buttons: list):
"""Similar helper for text+buttons or photo+buttons in single message"""
await send_photo_with_buttons(uid, image_name, caption, buttons)

fallback

@dp.message_handler()
async def fallback(message: types.Message):
await message.answer("Не распознал команду. Используй /start. Для меню нажми кнопку в стартовом сообщении.")

---------------- webhook startup/shutdown ----------------

async def on_startup(dp: Dispatcher):
# ensure no previous webhook
try:
await bot.delete_webhook()
logger.info("Deleted old webhook (if existed).")
except Exception:
logger.exception("Error deleting webhook (ignored).")

# set new webhook
# WEBHOOK_URL must be full URL that Telegram will post to
await bot.set_webhook(WEBHOOK_URL)
logger.info(f"Webhook set to {WEBHOOK_URL}")


async def on_shutdown(dp: Dispatcher):
logger.info("Shutting down, removing webhook")
try:
await bot.delete_webhook()
except Exception:
logger.exception("Error deleting webhook during shutdown")
await bot.session.close()

if name == "main":
logger.info("Starting webhook (Render mode).")
# webhook_path is extracted from WEBHOOK_URL; aiogram will route posts to that path
# Provide webhook_path param consistent with WEBHOOK_URL; simplest is to pass full path from URL:
# Extract path portion for webhook_path param:
from urllib.parse import urlparse
parsed = urlparse(WEBHOOK_URL)
webhook_path = parsed.path # e.g. /webhook/<token>
# aiogram expects path without domain; use webhook_path
executor.start_webhook(
dispatcher=dp,
webhook_path=webhook_path,
on_startup=on_startup,
on_shutdown=on_shutdown,
host="0.0.0.0",
port=PORT,
)
:::