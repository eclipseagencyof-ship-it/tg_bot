import logging
import os
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType, Message
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

# Настройки
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен.")

WEBHOOK_HOST = os.getenv("WEBHOOK_URL") or "https://heart-1-s96h.onrender.com"
WEBHOOK_PATH = "/webhook"  # Убедись, что в настройках вебхука нет дублирования пути
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

try:
    OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID"))
except (TypeError, ValueError):
    OWNER_CHAT_ID = 7136379834 
    logging.warning("OWNER_CHAT_ID не установлен или неверный. Уведомления не будут отправляться.")

kyiv_tz = pytz.timezone("Europe/Kyiv")

# Логирование с уровнем DEBUG для детального вывода
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

bot = Bot(token=API_TOKEN)
Bot.set_current(bot)

dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

# Клавиатура с кнопками Вход и Выход
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(KeyboardButton("+ Вход"), KeyboardButton("- Выход"))

work_sessions = {}
scheduled_jobs = {}
user_profiles = {}
user_progress = {}

screenshot_sequence = [
    "серии на онлайн",
    "серии чатов",
    "РП для цели Read",
    "РП для цели Favourites",
    "РП для цели Likes"
]

inbox_messages = [
    '📥 А теперь давай обработаем мужчин с Inbox:\n\nСкопируй письмо мужчины и задай ChatGPT такой вопрос:\n\n"Ответь на это письмо от (имя девушки), она очень заинтересована. Нужно удержать мужчину, получить ответ, завести на диалог."',
    '📥 А теперь давай обработаем мужчин с Inbox:\n\nЗадай ChatGPT такую команду:\n\n"(легкий флирт и искренность) Напиши письмо от девушки мужчине с элементами легкого флирта и искренности, где она говорит, что скучает, вспоминает что-то смешное или милое из их общения, рассказывает короткую забавную историю про себя, задает вопрос, чтобы узнать о нем больше, и приглашает к продолжению разговора."',
    '📥 А теперь давай обработаем мужчин с Inbox:\n\nЗадай ChatGPT такую команду:\n\n"(теплое, немного романтичное письмо) Напиши мужчине от девушки письмо с теплом и нежностью, в котором она признается, что скучает по нему, вспоминает приятные моменты общения, делится короткой историей о себе, задает вопрос, чтобы завязать диалог, и добавляет легкий флирт, чтобы вызвать улыбку."',
    '📥 А теперь давай обработаем мужчин с Inbox:\n\nЗадай ChatGPT такую команду:\n\n"Напиши мужчине письмо от девушки с сильной страстью и желанием. Пусть она откровенно признается, как сильно скучает, как часто его вспоминает с трепетом, расскажет что-то соблазнительное о себе, задаст вопрос, который пробуждает интерес и интригу, и добавит страстный флирт, чтобы разжечь в нем желание продолжить общение."'
]

async def continue_screenshot_sequence(user_id: str):
    try:
        count = user_profiles.get(user_id)
        progress = user_progress.get(user_id)

        logging.debug(f"continue_screenshot_sequence called for user {user_id}: count={count}, progress={progress}")

        if not count or not progress:
            logging.debug("No user profile count or progress found, stopping sequence.")
            return

        step = progress.get("step", 0)
        profile = progress.get("profile", 1)
        inbox_step = progress.get("inbox_step", 0)

        if step >= len(screenshot_sequence):
            await bot.send_message(user_id, "✅ Спасибо за рассылку, повторим через 120 мин.", reply_markup=keyboard)
            await bot.send_message(user_id, inbox_messages[inbox_step], reply_markup=keyboard)

            inbox_step = (inbox_step + 1) % len(inbox_messages)
            user_progress[user_id] = {"step": 0, "profile": 1, "inbox_step": inbox_step}
            logging.debug(f"User {user_id} inbox step updated to {inbox_step}, sequence reset.")
            return

        task = screenshot_sequence[step]
        await bot.send_message(user_id, f"📸 Сделайте скриншот запуска {task} через sender.service для анкеты {profile}", reply_markup=keyboard)
        logging.debug(f"Sent screenshot request to user {user_id}: task={task}, profile={profile}")

    except Exception as e:
        logging.error(f"Error in continue_screenshot_sequence for user {user_id}: {e}")

@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    logging.info(f"/start received from {message.from_user.id}")
    await message.answer("Привет! Нажми + Вход чтобы начать смену и - Выход чтобы закончить.", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "+ Вход")
async def check_in(message: types.Message):
    user_id = str(message.from_user.id)
    now = datetime.now(kyiv_tz)
    work_sessions[user_id] = {"start": now}
    logging.info(f"User {user_id} started work session at {now}")

    await message.answer(f"🟢 Вы начали смену в {now.strftime('%H:%M:%S')}.", reply_markup=keyboard)
    if OWNER_CHAT_ID:
        await bot.send_message(OWNER_CHAT_ID, f"👤 Пользователь {message.from_user.full_name} начал смену в {now.strftime('%H:%M:%S')}.")

    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("3"), KeyboardButton("4"))

    await message.answer("Сколько у вас активных анкет?", reply_markup=markup)

@dp.message_handler(lambda message: message.text in ["1", "2", "3", "4"])
async def set_profile_count(message: types.Message):
    user_id = str(message.from_user.id)
    count = int(message.text)
    user_profiles[user_id] = count
    user_progress[user_id] = {"step": 0, "profile": 1, "inbox_step": 0}
    logging.info(f"User {user_id} set profile count to {count}")

    await message.answer("Хорошо, начинаем процесс загрузки скриншотов.", reply_markup=keyboard)
    await continue_screenshot_sequence(user_id)

    # Управление задачами scheduler
    if user_id in scheduled_jobs:
        try:
            scheduler.remove_job(scheduled_jobs[user_id])
            logging.debug(f"Removed existing scheduled job for user {user_id}")
        except Exception as e:
            logging.error(f"Ошибка удаления задачи scheduler для user {user_id}: {e}")

    job = scheduler.add_job(
        continue_screenshot_sequence,
        'interval',
        minutes=120,
        args=[user_id],
        id=user_id,
        replace_existing=True
    )
    scheduled_jobs[user_id] = job.id
    logging.debug(f"Scheduled new job for user {user_id} every 120 minutes")

@dp.message_handler(lambda message: message.text == "- Выход")
async def check_out(message: types.Message):
    user_id = str(message.from_user.id)
    now = datetime.now(kyiv_tz)

    if user_id in work_sessions:
        start_time = work_sessions[user_id]["start"]
        duration = now - start_time
        del work_sessions[user_id]
        logging.info(f"User {user_id} ended work session, duration {duration}")

        if user_id in scheduled_jobs:
            try:
                scheduler.remove_job(scheduled_jobs[user_id])
                logging.debug(f"Removed scheduled job for user {user_id}")
            except Exception as e:
                logging.error(f"Ошибка удаления задачи scheduler при выходе для user {user_id}: {e}")
            scheduled_jobs.pop(user_id, None)

        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes = remainder // 60

        await message.answer(f"🔴 Вы завершили смену в {now.strftime('%H:%M:%S')}.", reply_markup=keyboard)
        if OWNER_CHAT_ID:
            await bot.send_message(OWNER_CHAT_ID,
                                   f"👤 Пользователь {message.from_user.full_name} завершил смену в {now.strftime('%H:%M:%S')}.\n⏱ Продолжительность: {int(hours)} ч {int(minutes)} мин.")
    else:
        await message.answer("❗ Вы ещё не начинали смену. Нажмите + Вход.", reply_markup=keyboard)

@dp.message_handler(content_types=ContentType.PHOTO)
async def handle_photo(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in work_sessions:
        try:
            # Пересылаем скриншот владельцу
            await bot.send_photo(
                chat_id=OWNER_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=f"📸 Скриншот от {message.from_user.full_name} ({user_id})"
            )
            await message.answer("Скриншот получен.", reply_markup=keyboard)
            logging.info(f"Received and forwarded photo from user {user_id}")

            # Обновляем прогресс
            if user_id in user_profiles and user_id in user_progress:
                progress = user_progress[user_id]
                profile = progress.get("profile", 1)
                count = user_profiles[user_id]

                if profile < count:
                    user_progress[user_id]["profile"] += 1
                else:
                    user_progress[user_id]["profile"] = 1
                    user_progress[user_id]["step"] = progress.get("step", 0) + 1

                logging.debug(f"User {user_id} progress updated to step {user_progress[user_id]['step']} profile {user_progress[user_id]['profile']}")
                await continue_screenshot_sequence(user_id)

        except Exception as e:
            logging.error(f"Ошибка при пересылке фото от user {user_id}: {e}")
            await message.answer("Ошибка при отправке скриншота.", reply_markup=keyboard)
    else:
        await message.answer("Вы не в активной смене. Нажмите + Вход.", reply_markup=keyboard)
        logging.debug(f"User {user_id} отправил фото вне активной смены.")

@dp.message_handler()
async def forward_all_messages(message: Message):
    try:
        await bot.forward_message(
            chat_id=OWNER_CHAT_ID,
            from_chat_id=message.from_user.id,
            message_id=message.message_id
        )
        logging.debug(f"Forwarded message {message.message_id} from user {message.from_user.id} to owner")
    except Exception as e:
        logging.error(f"Ошибка при пересылке сообщения: {e}")

# Обработчик корневого пути — для проверки сервиса
async def handle_root(request):
    return web.Response(text="OK")

# Обработчик вебхука Telegram
async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
        logging.debug(f"Webhook update received: {data}")
        update = types.Update.to_object(data)
        await dp.process_update(update)
    except Exception as e:
        logging.error(f"Ошибка обработки webhook: {e}")
        return web.Response(status=500, text="Internal Server Error")
    return web.Response(text="OK")

async def on_startup(app):
    logging.info("Starting webhook...")
    await bot.set_webhook(WEBHOOK_URL)
    scheduler.start()
    logging.info(f"Scheduler started and webhook set to {WEBHOOK_URL}")

async def on_shutdown(app):
    logging.info("Shutting down webhook and scheduler...")
    await bot.delete_webhook()
    scheduler.shutdown()
    # Закрываем сессию бота
    await bot.session.close()
    logging.info("Bot session closed.")

def main():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    logging.info(f"Starting web server on {WEBAPP_HOST}:{WEBAPP_PORT}")
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

if __name__ == '__main__':
    main()
