import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import re
import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Message,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    ForeignKey,
    DateTime,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
)
from telethon.sessions import StringSession

load_dotenv()

# -------------------- Конфигурация --------------------
DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7973988177]
API_ID = 32480523
API_HASH = "147839735c9fa4e83451209e9b55cfc5"

# Московское время (UTC+3)
MSK_TZ = timezone(timedelta(hours=3))


def msk_now():
    """Текущее московское время"""
    return datetime.now(MSK_TZ)


# -------------------- Премиум эмодзи --------------------
EMOJI_SETTINGS = '5870982283724328568'
EMOJI_PROFILE = '5870994129244131212'
EMOJI_PEOPLE = '5870772616305839506'
EMOJI_USER_CHECK = '5891207662678317861'
EMOJI_USER_CROSS = '5893192487324880883'
EMOJI_FILE = '5870528606328852614'
EMOJI_SMILE = '5870764288364252592'
EMOJI_GROWTH = '5870930636742595124'
EMOJI_STATS = '5870921681735781843'
EMOJI_HOME = '5873147866364514353'
EMOJI_LOCK_CLOSED = '6037249452824072506'
EMOJI_LOCK_OPEN = '6037496202990194718'
EMOJI_MEGAPHONE = '6039422865189638057'
EMOJI_CHECK = '5870633910337015697'
EMOJI_CROSS = '5870657884844462243'
EMOJI_PENCIL = '5870676941614354370'
EMOJI_TRASH = '5870875489362513438'
EMOJI_DOWN = '5893057118545646106'
EMOJI_CLIP = '6039451237743595514'
EMOJI_LINK = '5769289093221454192'
EMOJI_INFO = '6028435952299413210'
EMOJI_BOT = '6030400221232501136'
EMOJI_EYE = '6037397706505195857'
EMOJI_EYE_HIDDEN = '6037243349675544634'
EMOJI_SEND = '5963103826075456248'
EMOJI_DOWNLOAD = '6039802767931871481'
EMOJI_BELL = '6039486778597970865'
EMOJI_GIFT = '6032644646587338669'
EMOJI_CLOCK = '5983150113483134607'
EMOJI_PARTY = '6041731551845159060'
EMOJI_FONT = '5870801517140775623'
EMOJI_WRITE = '5870753782874246579'
EMOJI_PHOTO = '6035128606563241721'
EMOJI_LOCATION = '6042011682497106307'
EMOJI_WALLET = '5769126056262898415'
EMOJI_BOX = '5884479287171485878'
EMOJI_CRYPTOBOT = '5260752406890711732'
EMOJI_CALENDAR = '5890937706803894250'
EMOJI_TAG = '5886285355279193209'
EMOJI_TIME_PAST = '5775896410780079073'
EMOJI_APPS = '5778672437122045013'
EMOJI_BRUSH = '6050679691004612757'
EMOJI_ADD_TEXT = '5771851822897566479'
EMOJI_RESIZE = '5778479949572738874'
EMOJI_MONEY = '5904462880941545555'
EMOJI_SEND_MONEY = '5890848474563352982'
EMOJI_RECEIVE_MONEY = '5879814368572478751'
EMOJI_CODE = '5940433880585605708'
EMOJI_LOADING = '5345906554510012647'
EMOJI_BACK = '5774022692642492953'
EMOJI_BROADCAST = '5370599459661045441'
EMOJI_SUBSCRIBE = '6039450962865688331'

# -------------------- Логирование --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# -------------------- База данных --------------------
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    hold_balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=msk_now)

    sales = relationship("Sale", back_populates="user")


class Country(Base):
    __tablename__ = "countries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    price = Column(Float, default=100.0)

    sales = relationship("Sale", back_populates="country")


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    phone_number = Column(String, nullable=False)
    status = Column(String, default="pending")
    session_string = Column(Text, nullable=True)
    created_at = Column(DateTime, default=msk_now)
    confirmed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sales")
    country = relationship("Country", back_populates="sales")


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String, nullable=False)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=msk_now)


# Удаляем старые таблицы и создаем новые
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)


def init_countries():
    db = SessionLocal()
    try:
        if db.query(Country).count() == 0:
            countries = [
                "США", "Россия", "Беларусь", "Украина",
                "Казахстан", "Индия", "Испания", "Франция",
                "Италия", "Узбекистан", "Мьянма", "Нигерия"
            ]
            for country_name in countries:
                country = Country(name=country_name, price=100.0)
                db.add(country)
            db.commit()
            logger.info(f"Страны успешно созданы")
    finally:
        db.close()


init_countries()

# -------------------- Инициализация бота --------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Временное хранилище
pending_sales = {}


# -------------------- Клавиатуры --------------------
def get_main_keyboard():
    """Главная клавиатура с премиум эмодзи"""
    keyboard = {
        "keyboard": [
            [
                {
                    "text": "Продать аккаунт",
                    "icon_custom_emoji_id": EMOJI_MONEY
                },
                {
                    "text": "Профиль",
                    "icon_custom_emoji_id": EMOJI_PROFILE
                }
            ],
            [
                {
                    "text": "Вывод",
                    "icon_custom_emoji_id": EMOJI_SEND_MONEY
                }
            ]
        ],
        "resize_keyboard": True
    }
    return keyboard


def get_admin_keyboard():
    """Клавиатура администратора с премиум эмодзи"""
    keyboard = {
        "keyboard": [
            [
                {
                    "text": "Настроить цены",
                    "icon_custom_emoji_id": EMOJI_SETTINGS
                },
                {
                    "text": "Статистика",
                    "icon_custom_emoji_id": EMOJI_STATS
                }
            ],
            [
                {
                    "text": "Рассылка",
                    "icon_custom_emoji_id": EMOJI_BROADCAST
                },
                {
                    "text": "Выйти из админки",
                    "icon_custom_emoji_id": EMOJI_CROSS
                }
            ]
        ],
        "resize_keyboard": True
    }
    return keyboard


def get_countries_keyboard():
    """Клавиатура выбора страны"""
    db = SessionLocal()
    try:
        countries = db.query(Country).all()
        keyboard = []
        row = []
        for i, country in enumerate(countries):
            button = InlineKeyboardButton(
                text=f"{country.name}",
                callback_data=f"country_{country.id}",
                icon_custom_emoji_id=EMOJI_LOCATION
            )
            row.append(button)
            if (i + 1) % 3 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([
            InlineKeyboardButton(
                text="Назад",
                callback_data="back_to_main",
                icon_custom_emoji_id=EMOJI_BACK
            )
        ])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    finally:
        db.close()


def get_withdraw_keyboard():
    """Клавиатура вывода средств"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="Crypto Bot (мин. 30₽)",
                callback_data="withdraw_crypto",
                icon_custom_emoji_id=EMOJI_CRYPTOBOT
            )
        ],
        [
            InlineKeyboardButton(
                text="Tonkeeper (мин. 30₽)",
                callback_data="withdraw_tonkeeper",
                icon_custom_emoji_id=EMOJI_WALLET
            )
        ],
        [
            InlineKeyboardButton(
                text="СБП (мин. 150₽)",
                callback_data="withdraw_sbp",
                icon_custom_emoji_id=EMOJI_RECEIVE_MONEY
            )
        ],
        [
            InlineKeyboardButton(
                text="Карта (мин. 150₽)",
                callback_data="withdraw_card",
                icon_custom_emoji_id=EMOJI_MONEY
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data="back_to_main",
                icon_custom_emoji_id=EMOJI_BACK
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_profile_keyboard():
    """Клавиатура профиля"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="Мои продажи",
                callback_data="my_sales",
                icon_custom_emoji_id=EMOJI_BOX
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data="back_to_main",
                icon_custom_emoji_id=EMOJI_BACK
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_sell_keyboard(country_id):
    """Клавиатура для продажи аккаунта"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="Продать аккаунт",
                callback_data=f"sell_{country_id}",
                icon_custom_emoji_id=EMOJI_MONEY
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data="back_to_countries",
                icon_custom_emoji_id=EMOJI_BACK
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# -------------------- Обработчики команд --------------------
@router.message(Command("start"))
async def cmd_start(message: Message):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username
            )
            db.add(user)
            db.commit()
            logger.info(f"Новый пользователь: {message.from_user.id} (@{message.from_user.username})")

        await message.answer(
            f"<b><tg-emoji emoji-id='{EMOJI_HOME}'>🏠</tg-emoji> Главное меню</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    finally:
        db.close()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(
            f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> У вас нет доступа к админ-панели</b>",
            parse_mode=ParseMode.HTML
        )
        return

    await message.answer(
        f"<b><tg-emoji emoji-id='{EMOJI_SETTINGS}'>⚙️</tg-emoji> Админ-панель</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_keyboard()
    )


# -------------------- Обработчики кнопок главного меню --------------------
@router.message(F.text == "Продать аккаунт")
async def sell_account(message: Message):
    await message.answer(
        f"<b><tg-emoji emoji-id='{EMOJI_LOCATION}'>📍</tg-emoji> Выберите страну аккаунта:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_countries_keyboard()
    )


@router.message(F.text == "Профиль")
async def profile(message: Message):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            return

        profile_text = (
            f"<b><tg-emoji emoji-id='{EMOJI_PROFILE}'>👤</tg-emoji> Профиль</b>\n\n"
            f"<b>Username:</b> @{user.username or 'Нет'}\n"
            f"<b>ID:</b> {user.telegram_id}\n"
            f"<b>Баланс:</b> {user.balance:.2f}₽ (доступно для вывода: {user.balance:.2f}₽)\n"
            f"<b>Холд:</b> {user.hold_balance:.2f}₽"
        )

        await message.answer(
            profile_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_profile_keyboard()
        )
    finally:
        db.close()


@router.message(F.text == "Вывод")
async def withdraw(message: Message):
    await message.answer(
        f"<b><tg-emoji emoji-id='{EMOJI_SEND_MONEY}'>💸</tg-emoji> Выберите способ вывода:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_withdraw_keyboard()
    )


# -------------------- Обработчики админ-панели --------------------
@router.message(F.text == "Настроить цены")
async def admin_prices(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    # Отмечаем что админ хочет выбрать страну для изменения цены
    pending_sales[message.from_user.id] = {"action": "set_price_select"}

    await message.answer(
        f"<b><tg-emoji emoji-id='{EMOJI_PENCIL}'>✏️</tg-emoji> Выберите страну для изменения цены:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_countries_keyboard()
    )


@router.message(F.text == "Статистика")
async def admin_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    db = SessionLocal()
    try:
        total_users = db.query(User).count()

        now = msk_now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = today_start.replace(day=1)

        sales_today = db.query(Sale).filter(Sale.created_at >= today_start).count()
        sales_week = db.query(Sale).filter(Sale.created_at >= week_start).count()
        sales_month = db.query(Sale).filter(Sale.created_at >= month_start).count()

        stats_text = (
            f"<b><tg-emoji emoji-id='{EMOJI_STATS}'>📊</tg-emoji> Статистика</b>\n\n"
            f"<b><tg-emoji emoji-id='{EMOJI_PEOPLE}'>👥</tg-emoji> Всего пользователей:</b> {total_users}\n\n"
            f"<b><tg-emoji emoji-id='{EMOJI_CALENDAR}'>📅</tg-emoji> Продажи (МСК):</b>\n"
            f"<b>Сегодня:</b> {sales_today}\n"
            f"<b>Неделя:</b> {sales_week}\n"
            f"<b>Месяц:</b> {sales_month}"
        )

        await message.answer(
            stats_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
    finally:
        db.close()


@router.message(F.text == "Рассылка")
async def admin_broadcast_start(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer(
        f"<b><tg-emoji emoji-id='{EMOJI_BROADCAST}'>📢</tg-emoji> Отправьте текст сообщения для рассылки:</b>",
        parse_mode=ParseMode.HTML
    )

    pending_sales[message.from_user.id] = {"action": "broadcast"}


@router.message(F.text == "Выйти из админки")
async def admin_exit(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    if message.from_user.id in pending_sales:
        del pending_sales[message.from_user.id]

    await message.answer(
        f"<b><tg-emoji emoji-id='{EMOJI_HOME}'>🏠</tg-emoji> Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


# -------------------- Обработчики callback_query --------------------
@router.callback_query(F.data.startswith("country_"))
async def country_selected(callback: CallbackQuery):
    country_id = int(callback.data.split("_")[1])

    db = SessionLocal()
    try:
        country = db.query(Country).filter(Country.id == country_id).first()
        if not country:
            await callback.answer("Страна не найдена", show_alert=True)
            return

        # Если админ выбирает страну для изменения цены
        if callback.from_user.id in ADMIN_IDS and callback.from_user.id in pending_sales:
            if pending_sales[callback.from_user.id].get("action") == "set_price_select":
                pending_sales[callback.from_user.id] = {
                    "action": "set_price",
                    "country_id": country_id
                }
                await callback.message.edit_text(
                    f"<b><tg-emoji emoji-id='{EMOJI_PENCIL}'>✏️</tg-emoji> Введите новую цену для {country.name} (текущая: {country.price:.2f}₽):</b>",
                    parse_mode=ParseMode.HTML
                )
                await callback.answer()
                return

        await callback.message.edit_text(
            f"<b><tg-emoji emoji-id='{EMOJI_LOCATION}'>📍</tg-emoji> Цена скупки для {country.name}: {country.price:.2f}₽</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_sell_keyboard(country_id)
        )
        await callback.answer()
    finally:
        db.close()


@router.callback_query(F.data == "back_to_countries")
async def back_to_countries(callback: CallbackQuery):
    await callback.message.edit_text(
        f"<b><tg-emoji emoji-id='{EMOJI_LOCATION}'>📍</tg-emoji> Выберите страну аккаунта:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_countries_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        f"<b><tg-emoji emoji-id='{EMOJI_HOME}'>🏠</tg-emoji> Главное меню</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "my_sales")
async def my_sales(callback: CallbackQuery):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        sales = db.query(Sale).filter(Sale.user_id == user.id).order_by(Sale.created_at.desc()).limit(10).all()

        if not sales:
            await callback.message.edit_text(
                f"<b><tg-emoji emoji-id='{EMOJI_BOX}'>📦</tg-emoji> У вас пока нет продаж</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_profile_keyboard()
            )
            return

        sales_text = f"<b><tg-emoji emoji-id='{EMOJI_BOX}'>📦</tg-emoji> История продаж (МСК):</b>\n\n"
        for sale in sales:
            status_map = {
                "pending": f"<tg-emoji emoji-id='{EMOJI_CLOCK}'>⏰</tg-emoji> Ожидает",
                "confirmed": f"<tg-emoji emoji-id='{EMOJI_CHECK}'>✅</tg-emoji> Подтверждена",
                "rejected": f"<tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Отклонена"
            }
            status_text = status_map.get(sale.status, sale.status)

            country = db.query(Country).filter(Country.id == sale.country_id).first()
            country_name = country.name if country else "Неизвестно"

            # Форматируем дату в МСК
            sale_date = sale.created_at.strftime('%d.%m.%Y %H:%M') if sale.created_at else "Н/Д"

            sales_text += (
                f"<b>Дата:</b> {sale_date}\n"
                f"<b>Страна:</b> {country_name}\n"
                f"<b>Статус:</b> {status_text}\n"
                f"<b>Номер:</b> {sale.phone_number}\n"
                f"────────────────\n"
            )

        await callback.message.edit_text(
            sales_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_profile_keyboard()
        )
    finally:
        db.close()
    await callback.answer()


@router.callback_query(F.data.startswith("sell_"))
async def sell_account_start(callback: CallbackQuery):
    country_id = int(callback.data.split("_")[1])

    pending_sales[callback.from_user.id] = {
        "action": "sell",
        "country_id": country_id,
        "step": "phone"
    }

    await callback.message.edit_text(
        f"<b><tg-emoji emoji-id='{EMOJI_WRITE}'>✍️</tg-emoji> Введите номер телефона аккаунта (в формате +7...):</b>",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("withdraw_"))
async def withdraw_method(callback: CallbackQuery):
    method = callback.data.split("_")[1]

    method_names = {
        "crypto": "Crypto Bot",
        "tonkeeper": "Tonkeeper",
        "sbp": "СБП",
        "card": "Карта"
    }

    method_name = method_names.get(method, method)

    await callback.message.edit_text(
        f"<b><tg-emoji emoji-id='{EMOJI_SEND_MONEY}'>💸</tg-emoji> Для вывода средств ({method_name}) свяжитесь с администратором: @v3estnikov</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_withdraw_keyboard()
    )
    await callback.answer()


# -------------------- Обработка текстовых сообщений --------------------
@router.message(F.text)
async def handle_messages(message: Message):
    user_id = message.from_user.id

    # Обработка рассылки
    if user_id in ADMIN_IDS and user_id in pending_sales and pending_sales[user_id].get("action") == "broadcast":
        await handle_broadcast(message)
        return

    # Обработка установки цены
    if user_id in ADMIN_IDS and user_id in pending_sales and pending_sales[user_id].get("action") == "set_price":
        await handle_set_price(message)
        return

    # Обработка продажи аккаунта
    if user_id in pending_sales and pending_sales[user_id].get("action") == "sell":
        await handle_sell_process(message)
        return


async def handle_sell_process(message: Message):
    user_id = message.from_user.id
    sale_data = pending_sales.get(user_id)

    if not sale_data:
        return

    if sale_data["step"] == "phone":
        phone = message.text.strip()

        if not re.match(r'^\+\d{7,15}$', phone):
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Неверный формат номера. Введите номер в формате +7...</b>",
                parse_mode=ParseMode.HTML
            )
            return

        sale_data["phone"] = phone
        sale_data["step"] = "code"

        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            sent_code = await client.send_code_request(phone)
            sale_data["client"] = client
            sale_data["phone_code_hash"] = sent_code.phone_code_hash

            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_SEND}'>📤</tg-emoji> Код подтверждения отправлен на номер {phone}. Введите полученный код:</b>",
                parse_mode=ParseMode.HTML
            )
        except FloodWaitError as e:
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_CLOCK}'>⏰</tg-emoji> Слишком много попыток. Подождите {e.seconds} секунд.</b>",
                parse_mode=ParseMode.HTML
            )
            del pending_sales[user_id]
        except Exception as e:
            logger.error(f"Ошибка отправки кода: {e}")
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Ошибка отправки кода. Проверьте номер.</b>",
                parse_mode=ParseMode.HTML
            )
            del pending_sales[user_id]

    elif sale_data["step"] == "code":
        code = message.text.strip()
        client = sale_data.get("client")
        phone_code_hash = sale_data.get("phone_code_hash")
        phone = sale_data.get("phone")

        if not client or not phone_code_hash:
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Ошибка сессии. Начните заново.</b>",
                parse_mode=ParseMode.HTML
            )
            del pending_sales[user_id]
            return

        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)

            session_string = StringSession.save(client.session)

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.telegram_id == user_id).first()
                country_id = sale_data["country_id"]
                country = db.query(Country).filter(Country.id == country_id).first()

                sale = Sale(
                    user_id=user.id,
                    country_id=country_id,
                    phone_number=phone,
                    status="pending",
                    session_string=session_string
                )
                db.add(sale)

                user.hold_balance += country.price
                db.commit()

                await message.answer(
                    f"<b><tg-emoji emoji-id='{EMOJI_CHECK}'>✅</tg-emoji> Аккаунт принят! Средства будут зачислены на баланс через 24 часа после проверки.</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_main_keyboard()
                )

                threading.Thread(
                    target=check_account_after_24h,
                    args=(sale.id, user.telegram_id),
                    daemon=True
                ).start()

                logger.info(f"Продажа #{sale.id} создана пользователем {user_id} в {msk_now()}")

            finally:
                db.close()
                await client.disconnect()

        except SessionPasswordNeededError:
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_LOCK_CLOSED}'>🔒</tg-emoji> Аккаунт имеет двухфакторную аутентификацию и не может быть принят.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )
            await client.disconnect()

        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Неверный или просроченный код. Попробуйте снова.</b>",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Ошибка проверки аккаунта.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )
            await client.disconnect()

        finally:
            if user_id in pending_sales:
                del pending_sales[user_id]


async def handle_broadcast(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    broadcast_text = message.html_text if message.html_text else message.text

    db = SessionLocal()
    try:
        users = db.query(User).all()
        success = 0
        failed = 0

        await message.answer(
            f"<b><tg-emoji emoji-id='{EMOJI_LOADING}'>🔄</tg-emoji> Начинаю рассылку...</b>",
            parse_mode=ParseMode.HTML
        )

        for user in users:
            try:
                await bot.send_message(
                    user.telegram_id,
                    broadcast_text,
                    parse_mode=ParseMode.HTML
                )
                success += 1
                await asyncio.sleep(0.05)  # Задержка чтобы не превысить лимиты
            except Exception as e:
                logger.error(f"Ошибка отправки пользователю {user.telegram_id}: {e}")
                failed += 1

        await message.answer(
            f"<b><tg-emoji emoji-id='{EMOJI_CHECK}'>✅</tg-emoji> Рассылка завершена!</b>\n"
            f"<b>Успешно:</b> {success}\n"
            f"<b>Неудачно:</b> {failed}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_keyboard()
        )
    finally:
        db.close()

    if message.from_user.id in pending_sales:
        del pending_sales[message.from_user.id]


async def handle_set_price(message: Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    sale_data = pending_sales.get(user_id)
    if not sale_data or sale_data.get("action") != "set_price":
        return

    try:
        new_price = float(message.text.strip().replace(",", "."))
        if new_price <= 0:
            await message.answer(
                f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Цена должна быть положительным числом.</b>",
                parse_mode=ParseMode.HTML
            )
            return

        country_id = sale_data.get("country_id")
        db = SessionLocal()
        try:
            country = db.query(Country).filter(Country.id == country_id).first()
            if country:
                country.price = new_price
                db.commit()
                await message.answer(
                    f"<b><tg-emoji emoji-id='{EMOJI_CHECK}'>✅</tg-emoji> Цена для {country.name} обновлена: {new_price:.2f}₽</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_keyboard()
                )
                logger.info(f"Админ {user_id} изменил цену для {country.name} на {new_price}₽")
        finally:
            db.close()

    except ValueError:
        await message.answer(
            f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Введите корректное число.</b>",
            parse_mode=ParseMode.HTML
        )
    finally:
        if user_id in pending_sales:
            del pending_sales[user_id]


def check_account_after_24h(sale_id: int, telegram_id: int):
    """Фоновая проверка аккаунта через 24 часа"""
    logger.info(f"Запущена проверка для продажи #{sale_id} через 24 часа (МСК: {msk_now()})")
    time.sleep(86400)  # 24 часа

    db = SessionLocal()
    try:
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not sale or not user:
            logger.error(f"Продажа #{sale_id} или пользователь {telegram_id} не найдены")
            return

        if sale.status != "pending":
            logger.info(f"Продажа #{sale_id} уже обработана (статус: {sale.status})")
            return

        logger.info(f"Проверка аккаунта #{sale_id} в {msk_now()}")

        try:
            client = TelegramClient(StringSession(sale.session_string), API_ID, API_HASH)
            client.connect()

            if client.is_user_authorized():
                # Аккаунт валиден
                sale.status = "confirmed"
                sale.confirmed_at = msk_now()

                country = db.query(Country).filter(Country.id == sale.country_id).first()
                amount = country.price if country else 100.0

                user.hold_balance -= amount
                user.balance += amount

                db.commit()

                logger.info(f"Продажа #{sale_id} подтверждена. Пользователь {telegram_id} получил {amount}₽")

                try:
                    bot.send_message(
                        telegram_id,
                        f"<b><tg-emoji emoji-id='{EMOJI_CHECK}'>✅</tg-emoji> Аккаунт проверен и подтвержден!</b>\n"
                        f"<b>На баланс зачислено:</b> {amount:.2f}₽\n"
                        f"<b>Текущий баланс:</b> {user.balance:.2f}₽",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {telegram_id}: {e}")

            else:
                # Аккаунт невалиден
                sale.status = "rejected"
                country = db.query(Country).filter(Country.id == sale.country_id).first()
                amount = country.price if country else 100.0
                user.hold_balance -= amount

                db.commit()

                logger.info(f"Продажа #{sale_id} отклонена. Аккаунт невалиден")

                try:
                    bot.send_message(
                        telegram_id,
                        f"<b><tg-emoji emoji-id='{EMOJI_CROSS}'>❌</tg-emoji> Аккаунт не прошел проверку. Средства не зачислены.</b>",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {telegram_id}: {e}")

            client.disconnect()

        except Exception as e:
            logger.error(f"Ошибка проверки аккаунта #{sale_id}: {e}")
            sale.status = "rejected"
            country = db.query(Country).filter(Country.id == sale.country_id).first()
            amount = country.price if country else 100.0
            user.hold_balance -= amount
            db.commit()

    except Exception as e:
        logger.error(f"Ошибка в фоновой проверке: {e}")
    finally:
        db.close()


# -------------------- Запуск бота --------------------
async def main():
    logger.info(f"Бот запущен в {msk_now()} МСК")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
