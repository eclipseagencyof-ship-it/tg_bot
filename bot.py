"""Eclipse recruitment questionnaire — Ukrainian, aiogram 3, SQLite-backed progress."""
import asyncio
import html
import logging
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (FSInputFile, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)

ROOT = Path(__file__).resolve().parent
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "8327257248").strip()
WELCOME_IMAGE = ROOT / "welcome.jpg"
DB_PATH = Path(os.environ.get("SESSION_DB", str(ROOT / "applications.sqlite3")))
router = Router()
locks = {}

SHIFTS = ("06:00–14:00", "14:00–22:00", "22:00–06:00")
YES_18, NO_18 = "✅ Так", "❌ Ні"
YES_WORK, NO_WORK = "✅ Так, є досвід", "🌱 Ні, досвіду ще немає"
YES_TRAINING, NO_TRAINING = "✅ Так", "⏳ Поки що ні"
SKIP_PHONE = "Продовжити без номера"


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER PRIMARY KEY, step TEXT NOT NULL,
            name TEXT DEFAULT '', adult TEXT DEFAULT '',
            experience TEXT DEFAULT '', experience_details TEXT DEFAULT '',
            shift TEXT DEFAULT '', salary TEXT DEFAULT '', training TEXT DEFAULT ''
        )""")


def load_session(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row is not None else None


def new_session(user_id):
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO sessions(user_id,step) VALUES (?,?)", (user_id, "name"))


def save_session(user_id, step, **updates):
    allowed = {"name", "adult", "experience", "experience_details", "shift", "salary", "training"}
    fields = {key: value for key, value in updates.items() if key in allowed}
    fields["step"] = step
    sql = ", ".join(f"{key}=?" for key in fields)
    with db() as conn:
        conn.execute(f"UPDATE sessions SET {sql} WHERE user_id=?", (*fields.values(), user_id))


def clear_session(user_id):
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def buttons(*labels):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label in labels],
        resize_keyboard=True, one_time_keyboard=True,
    )


def next_number(session, step):
    base = {"name": 1, "adult": 2, "experience": 3, "experience_details": 4,
            "shift": 5, "salary": 6, "training": 7, "contact": 8}
    number = base[step]
    if step in ("shift", "salary", "training", "contact") and session.get("experience") == "Ні":
        number -= 1
    return number


async def ask(message, session):
    step = session["step"]
    n = next_number(session, step)
    if step == "name":
        await message.answer(f"<b>{n}. 👤 Як тебе звати?</b>",
                             reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    elif step == "adult":
        await message.answer(f"<b>{n}. 🎂 Тобі вже виповнилося 18 років?</b>",
                             reply_markup=buttons(YES_18, NO_18), parse_mode="HTML")
    elif step == "experience":
        await message.answer(f"<b>{n}. 💼 Чи маєш досвід роботи в шлюбному агентстві?</b>",
                             reply_markup=buttons(YES_WORK, NO_WORK), parse_mode="HTML")
    elif step == "experience_details":
        await message.answer(f"<b>{n}. 🏢 У якому агентстві, на якій платформі та як довго ти працював(-ла)?</b>\n\n<i>Напиши все одним повідомленням.</i>",
                             reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    elif step == "shift":
        await message.answer(f"<b>{n}. 🕒 Яку зміну тобі зручно працювати?</b>\n\nОбери час нижче 👇",
                             reply_markup=buttons(*SHIFTS), parse_mode="HTML")
    elif step == "salary":
        await message.answer(f"<b>{n}. 💰 Яку зарплату на місяць ти очікуєш?</b>\n\n<i>Наприклад: 500 USD.</i>",
                             reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    elif step == "training":
        await message.answer(f"<b>{n}. 📚 Чи готовий(-а) ти розпочати навчання?</b>",
                             reply_markup=buttons(YES_TRAINING, NO_TRAINING), parse_mode="HTML")
    elif step == "contact":
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📱 Поділитися номером", request_contact=True)],
            [KeyboardButton(text=SKIP_PHONE)]], resize_keyboard=True, one_time_keyboard=True)
        await message.answer(
            f"<b>{n}. 📲 Як з тобою зв’язатися?</b>\n\n"
            "Можеш поділитися номером телефону або продовжити без нього. "
            "У другому випадку ми спробуємо зв’язатися через Telegram.\n\n"
            "<i>Номер побачить лише адміністратор для зв’язку щодо вакансії.</i>",
            reply_markup=kb, parse_mode="HTML")


@router.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    lock = locks.setdefault(uid, asyncio.Lock())
    async with lock:
        session = load_session(uid)
        if session is not None:
            await message.answer("💗 Твоя анкета вже розпочата. Продовжимо з того місця, де зупинилися!")
            await ask(message, session)
            return
        new_session(uid)
        greeting = (
            "💗 <b>Вітаємо в Eclipse!</b>\n\n"
            "Раді, що тебе зацікавила вакансія перекладача. "
            "Заповни коротку анкету — і наш адміністратор зможе з тобою зв’язатися. ✨"
        )
        if WELCOME_IMAGE.exists():
            try:
                await message.answer_photo(FSInputFile(WELCOME_IMAGE), caption=greeting, parse_mode="HTML")
            except Exception:
                logging.exception("Помилка надсилання вітального зображення")
                await message.answer(greeting, parse_mode="HTML")
        else:
            await message.answer(greeting, parse_mode="HTML")
        await ask(message, load_session(uid))


@router.message(Command("cancel"))
async def cancel(message: Message):
    clear_session(message.from_user.id)
    await message.answer("Анкету скасовано. Щоб почати заново, натисни /start.",
                         reply_markup=ReplyKeyboardRemove())


async def send_report(message: Message, bot: Bot, session, phone):
    user = message.from_user
    esc = lambda x: html.escape(str(x), quote=False)
    tg_name = f"@{user.username}" if user.username else "Не вказано"
    link = f'<a href="tg://user?id={user.id}">{esc(user.full_name)}</a>'
    report = (
        "💌 <b>ECLIPSE | НОВА АНКЕТА</b>\n━━━━━━━━━━━━\n\n"
        f"👤 <b>Ім’я:</b> {esc(session['name'])}\n"
        "🔞 <b>Вік 18+:</b> Так\n"
        f"💼 <b>Досвід:</b> {esc(session['experience'])}\n"
        f"🏢 <b>Агентство / платформа / стаж:</b> {esc(session['experience_details'])}\n"
        f"🕒 <b>Зміна:</b> {esc(session['shift'])}\n"
        f"💰 <b>Очікувана зарплата:</b> {esc(session['salary'])}\n"
        f"📚 <b>Готовність до навчання:</b> {esc(session['training'])}\n\n"
        f"📱 <b>Телефон:</b> {esc(phone)}\n"
        f"💬 <b>Telegram:</b> {esc(tg_name)}\n"
        f"🔗 <b>Профіль:</b> {link}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>"
    )
    try:
        await bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=report, parse_mode="HTML")
    except Exception:
        logging.exception("Помилка відправлення анкети адміністратору")
        await message.answer("⚠️ Не вдалося надіслати анкету. Спробуй ще раз трохи пізніше.")
        return False
    return True


@router.message(F.text | F.contact)
async def handle_answer(message: Message, bot: Bot):
    uid = message.from_user.id
    lock = locks.setdefault(uid, asyncio.Lock())
    async with lock:
        session = load_session(uid)
        if not session:
            await message.answer("Щоб заповнити анкету, натисни /start.")
            return
        step = session["step"]
        value = (message.text or "").strip()
        if step == "name":
            if not 2 <= len(value) <= 100:
                await message.answer("Напиши, будь ласка, своє ім’я (від 2 до 100 символів).")
                return
            save_session(uid, "adult", name=value)
        elif step == "adult":
            if value not in (YES_18, NO_18):
                await message.answer("Обери відповідь кнопкою нижче 👇")
                return
            if value == NO_18:
                clear_session(uid)
                await message.answer("💗 Дякуємо за інтерес! Зараз ми розглядаємо кандидатів від 18 років.",
                                     reply_markup=ReplyKeyboardRemove())
                return
            save_session(uid, "experience", adult="Так")
        elif step == "experience":
            if value not in (YES_WORK, NO_WORK):
                await message.answer("Обери, будь ласка, відповідь кнопкою 👇")
                return
            if value == YES_WORK:
                save_session(uid, "experience_details", experience="Так")
            else:
                save_session(uid, "shift", experience="Ні", experience_details="Без досвіду")
        elif step == "experience_details":
            if not value:
                await message.answer("Напиши агентство, платформу та тривалість роботи.")
                return
            save_session(uid, "shift", experience_details=value[:1000])
        elif step == "shift":
            if value not in SHIFTS:
                await message.answer("Обери зміну за допомогою кнопки 👇")
                return
            save_session(uid, "salary", shift=value)
        elif step == "salary":
            if not value:
                await message.answer("Напиши, будь ласка, очікувану зарплату.")
                return
            save_session(uid, "training", salary=value[:200])
        elif step == "training":
            if value not in (YES_TRAINING, NO_TRAINING):
                await message.answer("Обери варіант відповіді кнопкою 👇")
                return
            save_session(uid, "contact", training="Так" if value == YES_TRAINING else "Поки що ні")
        elif step == "contact":
            if message.contact:
                if message.contact.user_id != uid:
                    await message.answer("Поділися своїм номером або продовжуй без нього.")
                    return
                phone = message.contact.phone_number
            elif value == SKIP_PHONE:
                phone = "Не вказано"
            else:
                await message.answer("Натисни «Поділитися номером» або «Продовжити без номера» 👇")
                return
            if await send_report(message, bot, session, phone):
                clear_session(uid)
                await message.answer(
                    "🎉 <b>Дякуємо! Анкету надіслано.</b>\n\n"
                    "Адміністратор перегляне твої відповіді й зв’яжеться з тобою в Telegram. 💗\n\n"
                    "✨ <i>Команда Eclipse</i>",
                    reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
            return
        await ask(message, load_session(uid))


@router.message()
async def other(message: Message):
    await message.answer("Відповідай, будь ласка, текстом або кнопками анкети. Для початку — /start.")


async def main():
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        raise RuntimeError("Встанови BOT_TOKEN і ADMIN_CHAT_ID у Render → Environment")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
