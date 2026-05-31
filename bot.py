import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import re
import asyncio
import sys

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
    inspect,
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
import phonenumbers
from phonenumbers import geocoder

load_dotenv()

# -------------------- Конфигурация --------------------
DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7973988177]
API_ID = 32480523
API_HASH = "147839735c9fa4e83451209e9b55cfc5"

MSK_TZ = timezone(timedelta(hours=3))


def msk_now():
    return datetime.now(MSK_TZ)


COUNTRY_CODE_MAP = {
    "США": ["US"],
    "Россия": ["RU"],
    "Беларусь": ["BY"],
    "Украина": ["UA"],
    "Казахстан": ["KZ"],
    "Индия": ["IN"],
    "Испания": ["ES"],
    "Франция": ["FR"],
    "Италия": ["IT"],
    "Узбекистан": ["UZ"],
    "Мьянма": ["MM"],
    "Нигерия": ["NG"],
}

# -------------------- Премиум эмодзи ID --------------------
E_HOME = '5873147866364514353'
E_PROFILE = '5870994129244131212'
E_MONEY = '5904462880941545555'
E_SEND_MONEY = '5890848474563352982'
E_SETTINGS = '5870982283724328568'
E_STATS = '5870921681735781843'
E_BROADCAST = '5370599459661045441'
E_CROSS = '5870657884844462243'
E_CHECK = '5870633910337015697'
E_CLOCK = '5983150113483134607'
E_BACK = '5774022692642492953'
E_LOCATION = '6042011682497106307'
E_SEND = '5963103826075456248'
E_WRITE = '5870753782874246579'
E_LOCK_CLOSED = '6037249452824072506'
E_BOX = '5884479287171485878'
E_CRYPTOBOT = '5260752406890711732'
E_WALLET = '5769126056262898415'
E_RECEIVE_MONEY = '5879814368572478751'
E_PENCIL = '5870676941614354370'
E_PEOPLE = '5870772616305839506'
E_CALENDAR = '5890937706803894250'
E_LOADING = '5345906554510012647'
E_INFO = '6028435952299413210'
E_SMILE = '5870764288364252592'
E_PARTY = '6041731551845159060'

# -------------------- Логирование --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# -------------------- База данных --------------------
try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        logger.info("DB connected")
except Exception as e:
    logger.error(f"DB error: {e}")
    sys.exit(1)

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


inspector = inspect(engine)
existing_tables = inspector.get_table_names()

if "users" not in existing_tables:
    logger.info("Creating tables...")
    Base.metadata.create_all(engine)
    logger.info("Tables created")
else:
    logger.info("Tables exist")


def init_countries():
    db = SessionLocal()
    try:
        count = db.query(Country).count()
        if count == 0:
            countries = [
                "США", "Россия", "Беларусь", "Украина",
                "Казахстан", "Индия", "Испания", "Франция",
                "Италия", "Узбекистан", "Мьянма", "Нигерия"
            ]
            for country_name in countries:
                country = Country(name=country_name, price=100.0)
                db.add(country)
            db.commit()
            logger.info(f"Countries created: {len(countries)}")
        else:
            logger.info(f"Countries exist: {count}")
    except Exception as e:
        logger.error(f"Error creating countries: {e}")
        db.rollback()
    finally:
        db.close()


init_countries()

# -------------------- Инициализация бота --------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

pending_sales = {}


def get_country_from_phone(phone_number: str) -> Optional[str]:
    try:
        parsed = phonenumbers.parse(phone_number)
        country_code = geocoder.region_code_for_number(parsed)
        for country_name, codes in COUNTRY_CODE_MAP.items():
            if country_code in codes:
                return country_name
        return None
    except Exception as e:
        logger.error(f"Phone parse error {phone_number}: {e}")
        return None


# -------------------- Клавиатуры --------------------
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Продать аккаунт"),
                KeyboardButton(text="Профиль")
            ],
            [
                KeyboardButton(text="Вывод")
            ]
        ],
        resize_keyboard=True
    )


def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Настроить цены"),
                KeyboardButton(text="Статистика")
            ],
            [
                KeyboardButton(text="Рассылка"),
                KeyboardButton(text="Выйти из админки")
            ]
        ],
        resize_keyboard=True
    )


def get_countries_keyboard():
    db = SessionLocal()
    try:
        countries = db.query(Country).all()
        keyboard = []
        row = []
        for i, country in enumerate(countries):
            button = InlineKeyboardButton(
                text=country.name,
                callback_data=f"country_{country.id}",
                icon_custom_emoji_id=E_LOCATION
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
                icon_custom_emoji_id=E_BACK
            )
        ])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    finally:
        db.close()


def get_withdraw_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(
                text="Crypto Bot (мин. 30₽)",
                callback_data="withdraw_crypto",
                icon_custom_emoji_id=E_CRYPTOBOT
            )
        ],
        [
            InlineKeyboardButton(
                text="Tonkeeper (мин. 30₽)",
                callback_data="withdraw_tonkeeper",
                icon_custom_emoji_id=E_WALLET
            )
        ],
        [
            InlineKeyboardButton(
                text="СБП (мин. 150₽)",
                callback_data="withdraw_sbp",
                icon_custom_emoji_id=E_RECEIVE_MONEY
            )
        ],
        [
            InlineKeyboardButton(
                text="Карта (мин. 150₽)",
                callback_data="withdraw_card",
                icon_custom_emoji_id=E_MONEY
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data="back_to_main",
                icon_custom_emoji_id=E_BACK
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_profile_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(
                text="Мои продажи",
                callback_data="my_sales",
                icon_custom_emoji_id=E_BOX
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data="back_to_main",
                icon_custom_emoji_id=E_BACK
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_sell_keyboard(country_id):
    keyboard = [
        [
            InlineKeyboardButton(
                text="Продать аккаунт",
                callback_data=f"sell_{country_id}",
                icon_custom_emoji_id=E_MONEY
            )
        ],
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data="back_to_countries",
                icon_custom_emoji_id=E_BACK
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# -------------------- Обработчики команд --------------------
@router.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"/start from {message.from_user.id}")
    
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
            logger.info(f"New user: {message.from_user.id}")

        await message.answer(
            f'<b><tg-emoji emoji-id="{E_HOME}">🏠</tg-emoji> Главное меню</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in /start: {e}")
    finally:
        db.close()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(
            f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Нет доступа</b>',
            parse_mode=ParseMode.HTML
        )
        return

    await message.answer(
        f'<b><tg-emoji emoji-id="{E_SETTINGS}">⚙️</tg-emoji> Админ-панель</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_keyboard()
    )


@router.message(F.text == "Продать аккаунт")
async def sell_account(message: Message):
    await message.answer(
        f'<b><tg-emoji emoji-id="{E_LOCATION}">📍</tg-emoji> Выберите страну аккаунта:</b>',
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
            f'<b><tg-emoji emoji-id="{E_PROFILE}">👤</tg-emoji> Профиль</b>\n\n'
            f'<b>Username:</b> @{user.username or "Нет"}\n'
            f'<b>ID:</b> {user.telegram_id}\n'
            f'<b>Баланс:</b> {user.balance:.2f}₽\n'
            f'<b>Холд:</b> {user.hold_balance:.2f}₽'
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
        f'<b><tg-emoji emoji-id="{E_SEND_MONEY}">💸</tg-emoji> Выберите способ вывода:</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_withdraw_keyboard()
    )


@router.message(F.text == "Настроить цены")
async def admin_prices(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    pending_sales[message.from_user.id] = {"action": "set_price_select"}

    await message.answer(
        f'<b><tg-emoji emoji-id="{E_PENCIL}">✏️</tg-emoji> Выберите страну для изменения цены:</b>',
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
            f'<b><tg-emoji emoji-id="{E_STATS}">📊</tg-emoji> Статистика</b>\n\n'
            f'<b><tg-emoji emoji-id="{E_PEOPLE}">👥</tg-emoji> Пользователей:</b> {total_users}\n\n'
            f'<b><tg-emoji emoji-id="{E_CALENDAR}">📅</tg-emoji> Продажи (МСК):</b>\n'
            f'<b>Сегодня:</b> {sales_today}\n'
            f'<b>Неделя:</b> {sales_week}\n'
            f'<b>Месяц:</b> {sales_month}'
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
        f'<b><tg-emoji emoji-id="{E_BROADCAST}">📢</tg-emoji> Отправьте текст для рассылки:</b>',
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
        f'<b><tg-emoji emoji-id="{E_HOME}">🏠</tg-emoji> Главное меню</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


# -------------------- Callback handlers --------------------
@router.callback_query(F.data.startswith("country_"))
async def country_selected(callback: CallbackQuery):
    country_id = int(callback.data.split("_")[1])

    db = SessionLocal()
    try:
        country = db.query(Country).filter(Country.id == country_id).first()
        if not country:
            await callback.answer("Страна не найдена", show_alert=True)
            return

        if callback.from_user.id in ADMIN_IDS and callback.from_user.id in pending_sales:
            if pending_sales[callback.from_user.id].get("action") == "set_price_select":
                pending_sales[callback.from_user.id] = {
                    "action": "set_price",
                    "country_id": country_id
                }
                await callback.message.edit_text(
                    f'<b><tg-emoji emoji-id="{E_PENCIL}">✏️</tg-emoji> Новая цена для {country.name} (текущая: {country.price:.2f}₽):</b>',
                    parse_mode=ParseMode.HTML
                )
                await callback.answer()
                return

        await callback.message.edit_text(
            f'<b><tg-emoji emoji-id="{E_LOCATION}">📍</tg-emoji> Цена для {country.name}: {country.price:.2f}₽</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=get_sell_keyboard(country_id)
        )
        await callback.answer()
    finally:
        db.close()


@router.callback_query(F.data == "back_to_countries")
async def back_to_countries(callback: CallbackQuery):
    await callback.message.edit_text(
        f'<b><tg-emoji emoji-id="{E_LOCATION}">📍</tg-emoji> Выберите страну:</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_countries_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        f'<b><tg-emoji emoji-id="{E_HOME}">🏠</tg-emoji> Главное меню</b>',
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
            await callback.answer("Не найдено", show_alert=True)
            return

        sales = db.query(Sale).filter(Sale.user_id == user.id).order_by(Sale.created_at.desc()).limit(10).all()

        if not sales:
            await callback.message.edit_text(
                f'<b><tg-emoji emoji-id="{E_BOX}">📦</tg-emoji> Нет продаж</b>',
                parse_mode=ParseMode.HTML,
                reply_markup=get_profile_keyboard()
            )
            return

        sales_text = f'<b><tg-emoji emoji-id="{E_BOX}">📦</tg-emoji> История продаж:</b>\n\n'
        for sale in sales:
            status_emoji = {
                "pending": f'<tg-emoji emoji-id="{E_CLOCK}">⏰</tg-emoji>',
                "confirmed": f'<tg-emoji emoji-id="{E_CHECK}">✅</tg-emoji>',
                "rejected": f'<tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji>'
            }
            status_text = status_emoji.get(sale.status, sale.status)

            country = db.query(Country).filter(Country.id == sale.country_id).first()
            country_name = country.name if country else "Неизвестно"

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
        f'<b><tg-emoji emoji-id="{E_WRITE}">✍️</tg-emoji> Введите номер телефона (+7...):</b>',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("withdraw_"))
async def withdraw_method(callback: CallbackQuery):
    await callback.message.edit_text(
        f'<b><tg-emoji emoji-id="{E_SEND_MONEY}">💸</tg-emoji> Для вывода свяжитесь с @v3estnikov</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_withdraw_keyboard()
    )
    await callback.answer()


# -------------------- Text handlers --------------------
@router.message()
async def handle_messages(message: Message):
    user_id = message.from_user.id

    if user_id in ADMIN_IDS and user_id in pending_sales:
        if pending_sales[user_id].get("action") == "broadcast":
            await handle_broadcast(message)
            return
        elif pending_sales[user_id].get("action") == "set_price":
            await handle_set_price(message)
            return

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
                f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Неверный формат. Введите +7...</b>',
                parse_mode=ParseMode.HTML
            )
            return

        detected_country = get_country_from_phone(phone)
        
        if not detected_country:
            await message.answer(
                f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Не удалось определить страну</b>',
                parse_mode=ParseMode.HTML
            )
            return

        db = SessionLocal()
        try:
            country_id = sale_data["country_id"]
            selected_country = db.query(Country).filter(Country.id == country_id).first()
            
            if not selected_country:
                await message.answer(
                    f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Ошибка: страна не найдена</b>',
                    parse_mode=ParseMode.HTML
                )
                del pending_sales[user_id]
                return

            if detected_country != selected_country.name:
                await message.answer(
                    f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Номер не соответствует стране!</b>\n\n'
                    f'<b>Выбрана:</b> {selected_country.name}\n'
                    f'<b>Определена:</b> {detected_country}\n\n'
                    f'Выберите правильную страну.',
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_countries_keyboard()
                )
                del pending_sales[user_id]
                return

        finally:
            db.close()

        sale_data["phone"] = phone
        sale_data["step"] = "code"

        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            sent_code = await client.send_code_request(phone)
            sale_data["client"] = client
            sale_data["phone_code_hash"] = sent_code.phone_code_hash

            await message.answer(
                f'<b><tg-emoji emoji-id="{E_CHECK}">✅</tg-emoji> Страна: {detected_country}</b>\n'
                f'<b><tg-emoji emoji-id="{E_SEND}">📤</tg-emoji> Код отправлен на {phone}. Введите код:</b>',
                parse_mode=ParseMode.HTML
            )
        except FloodWaitError as e:
            await message.answer(
                f'<b><tg-emoji emoji-id="{E_CLOCK}">⏰</tg-emoji> Подождите {e.seconds} сек.</b>',
                parse_mode=ParseMode.HTML
            )
            del pending_sales[user_id]
        except Exception as e:
            logger.error(f"Send code error: {e}")
            await message.answer(
                f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Ошибка отправки кода</b>',
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
                f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Ошибка сессии</b>',
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
                    f'<b><tg-emoji emoji-id="{E_CHECK}">✅</tg-emoji> Аккаунт принят! Средства через 24 часа.</b>',
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_main_keyboard()
                )

                threading.Thread(
                    target=check_account_after_24h,
                    args=(sale.id, user.telegram_id),
                    daemon=True
                ).start()

            finally:
                db.close()
                await client.disconnect()

        except SessionPasswordNeededError:
            await message.answer(
                f'<b><tg-emoji emoji-id="{E_LOCK_CLOSED}">🔒</tg-emoji> 2FA аккаунт не принимается</b>',
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )
            await client.disconnect()

        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            await message.answer(
                f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Неверный код</b>',
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Auth error: {e}")
            await message.answer(
                f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Ошибка проверки</b>',
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
            f'<b><tg-emoji emoji-id="{E_LOADING}">🔄</tg-emoji> Рассылка...</b>',
            parse_mode=ParseMode.HTML
        )

        for user in users:
            try:
                await bot.send_message(user.telegram_id, broadcast_text, parse_mode=ParseMode.HTML)
                success += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Send error {user.telegram_id}: {e}")
                failed += 1

        await message.answer(
            f'<b><tg-emoji emoji-id="{E_CHECK}">✅</tg-emoji> Готово!</b>\n'
            f'<b>Успешно:</b> {success}\n'
            f'<b>Ошибок:</b> {failed}',
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
                f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Цена > 0</b>',
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
                    f'<b><tg-emoji emoji-id="{E_CHECK}">✅</tg-emoji> Цена {country.name}: {new_price:.2f}₽</b>',
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_keyboard()
                )
        finally:
            db.close()

    except ValueError:
        await message.answer(
            f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Введите число</b>',
            parse_mode=ParseMode.HTML
        )
    finally:
        if user_id in pending_sales:
            del pending_sales[user_id]


def check_account_after_24h(sale_id: int, telegram_id: int):
    logger.info(f"24h check started for sale #{sale_id}")
    time.sleep(86400)

    db = SessionLocal()
    try:
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not sale or not user or sale.status != "pending":
            return

        try:
            client = TelegramClient(StringSession(sale.session_string), API_ID, API_HASH)
            client.connect()

            if client.is_user_authorized():
                sale.status = "confirmed"
                sale.confirmed_at = msk_now()

                country = db.query(Country).filter(Country.id == sale.country_id).first()
                amount = country.price if country else 100.0

                user.hold_balance -= amount
                user.balance += amount
                db.commit()

                try:
                    bot.send_message(
                        telegram_id,
                        f'<b><tg-emoji emoji-id="{E_CHECK}">✅</tg-emoji> Аккаунт подтвержден!</b>\n'
                        f'<b>Зачислено:</b> {amount:.2f}₽\n'
                        f'<b>Баланс:</b> {user.balance:.2f}₽',
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass

            else:
                sale.status = "rejected"
                country = db.query(Country).filter(Country.id == sale.country_id).first()
                amount = country.price if country else 100.0
                user.hold_balance -= amount
                db.commit()

                try:
                    bot.send_message(
                        telegram_id,
                        f'<b><tg-emoji emoji-id="{E_CROSS}">❌</tg-emoji> Аккаунт не прошел проверку</b>',
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass

            client.disconnect()

        except Exception as e:
            logger.error(f"Check error #{sale_id}: {e}")
            sale.status = "rejected"
            country = db.query(Country).filter(Country.id == sale.country_id).first()
            amount = country.price if country else 100.0
            user.hold_balance -= amount
            db.commit()

    finally:
        db.close()


# -------------------- Запуск --------------------
async def main():
    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
