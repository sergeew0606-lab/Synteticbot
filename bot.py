import asyncio
import os
import random
import re
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)

import config
from db import Database
from security import verify_password

router = Router(name="app")
dp = Dispatcher()
_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def is_admin(user_id: int) -> bool:
    return config.is_admin(user_id)


GUEST_TEXT = (
    "Здравствуй пользователь нашего клиента\n"
    "сначала пройдите регистрацию чтоб пройти дальше"
)
MEMBER_TEXT = (
    "Здравствуй пользователь нашего клиента\n"
    "сначала зайдите в аккаунт чтоб пройти дальше"
)
MENU_TEXT = (
    "Здраствуй добро пожаловать в Syntetic Client | Legit 26.2 fabric\n"
    "что вы хотите сделать?"
)

NICKNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
KEY_RE = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
FOREVER_DATE = date(2044, 12, 31)
SESSION_DAYS = 2

DURATIONS: list[dict] = [
    {"label": "1 день", "kind": "paid", "days": 1},
    {"label": "7 дней", "kind": "paid", "days": 7},
    {"label": "14 дней", "kind": "paid", "days": 14},
    {"label": "1 месяц", "kind": "paid", "days": 30},
    {"label": "6 месяцев", "kind": "paid", "days": 180},
    {"label": "1 год", "kind": "paid", "days": 365},
    {"label": "навсегда", "kind": "forever", "days": None},
    {"label": "бета среднего уровня (навсегда)", "kind": "beta_mid", "days": None},
    {"label": "бета высшего уровня (навсегда)", "kind": "beta_high", "days": None},
]

# цены в Telegram Stars, соответствуют DURATIONS[0..7] (бета высшего уровня не продаётся)
STARS: list[int] = [5, 17, 30, 50, 89, 129, 179, 259]


class Registration(StatesGroup):
    nickname = State()
    password = State()


class Login(StatesGroup):
    nickname = State()
    password = State()


class CreateKey(StatesGroup):
    duration = State()


class ActivateKey(StatesGroup):
    key = State()


def guest_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📝 Регистрация")]],
        resize_keyboard=True,
    )


def login_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔑 Вход в аккаунт")]],
        resize_keyboard=True,
    )


def menu_keyboard(admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛒 Купить подписку"), KeyboardButton(text="🎟 Активировать ключ")],
        [KeyboardButton(text="📥 Скачать клиент"), KeyboardButton(text="👤 Профиль")],
    ]
    if admin:
        rows.append([KeyboardButton(text="🛠 Админ-панель"), KeyboardButton(text="🚪 Выйти")])
    else:
        rows.append([KeyboardButton(text="🚪 Выйти")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔑 Создать ключ"), KeyboardButton(text="🚫 Заблокировать")],
            [KeyboardButton(text="✅ Разблокировать"), KeyboardButton(text="📋 Пароли")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )


def durations_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=DURATIONS[0]["label"], callback_data="dur:0"),
         InlineKeyboardButton(text=DURATIONS[1]["label"], callback_data="dur:1")],
        [InlineKeyboardButton(text=DURATIONS[2]["label"], callback_data="dur:2"),
         InlineKeyboardButton(text=DURATIONS[3]["label"], callback_data="dur:3")],
        [InlineKeyboardButton(text=DURATIONS[4]["label"], callback_data="dur:4"),
         InlineKeyboardButton(text=DURATIONS[5]["label"], callback_data="dur:5")],
        [InlineKeyboardButton(text=DURATIONS[6]["label"], callback_data="dur:6")],
        [InlineKeyboardButton(text=DURATIONS[7]["label"], callback_data="dur:7")],
        [InlineKeyboardButton(text=DURATIONS[8]["label"], callback_data="dur:8")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_keyboard(users: dict, show_blocked: bool) -> InlineKeyboardMarkup:
    buttons = []
    for uid, u in sorted(users.items(), key=lambda kv: (kv[1] or {}).get("nickname") or ""):
        if not isinstance(u, dict):
            continue
        if bool(u.get("blocked")) != show_blocked:
            continue
        label = u.get("nickname") or str(uid)
        prefix = "🚫" if show_blocked else "🔸"
        cb = f"ubk:{uid}" if show_blocked else f"blk:{uid}"
        buttons.append(InlineKeyboardButton(text=f"{prefix} {label}", callback_data=cb))
    if not buttons:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="пусто", callback_data="adm:none")]]
        )
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_text(user: dict) -> str:
    sub = user.get("subscription")
    if not isinstance(sub, dict):
        return "подписка: нет"
    kind = sub.get("kind")
    until = None
    try:
        until = date.fromisoformat(sub.get("until"))
    except Exception:
        pass
    if kind == "beta_mid":
        return "подписка: бета среднего уровня (навсегда)"
    if kind == "beta_high":
        return "подписка: бета высшего уровня (навсегда)"
    if kind == "forever":
        return "подписка: навсегда"
    if until is None or until < date.today():
        return "подписка: нет"
    return f"подписка до: {until.strftime('%d.%m.%Y')}"


def profile_text(user: dict) -> str:
    registered = user.get("registered_at") or ""
    reg_disp = "—"
    try:
        reg_disp = datetime.fromisoformat(registered.replace("Z", "+00:00")).strftime("%d.%m.%Y")
    except Exception:
        pass
    username = user.get("username")
    hwid = user.get("hwid")
    lines = [
        "👤 Профиль",
        "",
        f"никнейм: {user.get('nickname') or '—'}",
        f"UID: {user.get('uid')}" if user.get("uid") else "UID: —",
        f"username: @{username}" if username else "username: нет",
        f"дата регистрации: {reg_disp}",
    ]
    if user.get("password"):
        lines.append(f"пароль: {user.get('password')}")
    lines.append(f"HWID: {hwid}" if hwid else "HWID: нет")
    subscription = user.get("subscription")
    role = None
    if isinstance(subscription, dict):
        role = {
            "beta_mid": "бета среднего уровня",
            "beta_high": "бета высшего уровня",
        }.get(subscription.get("kind"))
    if role:
        lines.append(f"роль: {role}")
    lines.append("")
    lines.append(subscription_text(user))
    return "\n".join(lines)


def _session_expired(user: dict) -> bool:
    login_at = user.get("login_at")
    if not login_at:
        return False
    try:
        ts = datetime.fromisoformat(login_at.replace("Z", "+00:00"))
    except Exception:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts > timedelta(days=SESSION_DAYS)


async def should_stop(message: Message) -> bool:
    db = get_db()
    user = await db.get_user(message.from_user.id)
    if not user:
        return False
    if user.get("blocked"):
        await message.answer("⛔ Вы заблокированы.")
        return True
    if user.get("logged_in"):
        if _session_expired(user):
            await db.patch_user(message.from_user.id, {"logged_in": False, "login_at": None})
            await message.answer(
                f"⏳ Прошло {SESSION_DAYS} дня — сессия сброшена.\n"
                "Войдите в аккаунт заново, чтобы мы убедились, что это вы.",
                reply_markup=login_keyboard(),
            )
            return True
        await db.patch_user(
            message.from_user.id, {"login_at": datetime.now(timezone.utc).isoformat()}
        )
    return False


async def is_blocked(message: Message) -> bool:
    return await should_stop(message)


def generate_key(existing: set[str]) -> str:
    while True:
        chars = random.sample(KEY_ALPHABET, 16)
        key = "-".join("".join(chars[i : i + 4]) for i in range(0, 16, 4))
        if key not in existing:
            return key


async def next_uid() -> int:
    return (await get_db().count_users()) + 1


async def backfill_uids() -> None:
    db = get_db()
    users = await db.list_users()
    missing = [
        (int(raw_id), u)
        for raw_id, u in users.items()
        if isinstance(u, dict) and not u.get("uid") and str(raw_id).lstrip("-").isdigit()
    ]
    if not missing:
        return
    used = [int(u.get("uid")) for u in users.values() if isinstance(u, dict) and u.get("uid")]
    counter = max(used) if used else 0
    missing.sort(key=lambda kv: kv[1].get("registered_at") or "")
    for raw_id, _user in missing:
        counter += 1
        await db.patch_user(raw_id, {"uid": counter})
    print(f"backfill: назначен UID для {len(missing)} аккаунтов")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if await should_stop(message):
        return
    user = await get_db().get_user(message.from_user.id)
    if not user:
        await message.answer(GUEST_TEXT, reply_markup=guest_keyboard())
        return
    if not user.get("logged_in"):
        await message.answer(MEMBER_TEXT, reply_markup=login_keyboard())
        return
    await message.answer(MENU_TEXT, reply_markup=menu_keyboard(is_admin(message.from_user.id)))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "/start — главное меню\n"
        "/register — регистрация\n"
        "/profile — твой профиль\n"
        "/help — эта справка"
    )


# ------------------------- регистрация -------------------------

@router.message(Command("register"))
@router.message(F.text == "📝 Регистрация")
async def start_registration(message: Message, state: FSMContext) -> None:
    if await is_blocked(message):
        return
    if await get_db().get_user(message.from_user.id):
        await message.answer("Ты уже зарегистрирован ✅")
        return
    await state.set_state(Registration.nickname)
    await message.answer("Придумай никнейм:\n3–32 символа, только латиница, цифры и _")


@router.message(Registration.nickname, F.text)
async def got_nickname(message: Message, state: FSMContext) -> None:
    nickname = message.text.strip()
    if not NICKNAME_RE.fullmatch(nickname):
        await message.answer(
            "Никнейм не подходит. Нужно 3–32 символа: латиница, цифры, _. Попробуй ещё раз."
        )
        return
    if await get_db().find_by_nickname(nickname):
        await message.answer("Этот никнейм уже занят. Придумай другой.")
        return
    await state.update_data(nickname=nickname)
    await state.set_state(Registration.password)
    await message.answer(
        "Придумай пароль:\nот 6 до 64 символов, только английские символы (латиница, цифры, символы).\n\n"
        "⚠️ Отправь его одним сообщением — я сразу удалю его из чата, "
        "в базе будет храниться как есть, чтобы можно было восстановить аккаунт."
    )


@router.message(Registration.password, F.text)
async def got_password(message: Message, state: FSMContext) -> None:
    password = message.text
    if not 6 <= len(password) <= 64:
        await message.answer("Пароль должен быть от 6 до 64 символов. Попробуй ещё раз.")
        return
    if not all(" " <= ch <= "~" for ch in password):
        await message.answer(
            "Пароль должен быть на английском (латиница, цифры и символы), без русских букв. Попробуй ещё раз."
        )
        return
    data = await state.get_data()
    try:
        await message.delete()
    except Exception:
        pass

    uid_number = await next_uid()
    await get_db().create_user(
        user_id=message.from_user.id,
        nickname=data["nickname"],
        password=password,
        uid=uid_number,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    await state.clear()
    await message.answer(
        f"Готово! Аккаунт создан ✅\n"
        f"Никнейм: {data['nickname']}\n"
        f"UID: {uid_number}\n"
        f"Пароль: {password}\n\n"
        "Сохрани его — с ним можно восстановить доступ к аккаунту.",
        reply_markup=menu_keyboard(is_admin(message.from_user.id)),
    )
    await message.answer(MENU_TEXT)


# ------------------------- вход в аккаунт -------------------------

@router.message(Command("login"))
@router.message(F.text == "🔑 Вход в аккаунт")
async def start_login(message: Message, state: FSMContext) -> None:
    if await is_blocked(message):
        return
    user = await get_db().get_user(message.from_user.id)
    if not user:
        await message.answer(GUEST_TEXT, reply_markup=guest_keyboard())
        return
    if user.get("logged_in"):
        await message.answer(MENU_TEXT, reply_markup=menu_keyboard(is_admin(message.from_user.id)))
        return
    await state.set_state(Login.nickname)
    await message.answer("Введи свой никнейм:")


@router.message(Login.nickname, F.text)
async def login_nickname(message: Message, state: FSMContext) -> None:
    nickname = message.text.strip()
    user = await get_db().find_by_nickname(nickname)
    if not user or user.get("user_id") != message.from_user.id:
        await message.answer("Аккаунт с таким никнеймом не найден. Попробуй ещё раз.")
        return
    await state.set_state(Login.password)
    await message.answer("Введи пароль:")


@router.message(Login.password, F.text)
async def login_password(message: Message, state: FSMContext) -> None:
    password = message.text
    try:
        await message.delete()
    except Exception:
        pass
    user = await get_db().get_user(message.from_user.id)
    if not user:
        await message.answer("Аккаунт не найден. Пройди регистрацию.", reply_markup=guest_keyboard())
        return
    stored = user.get("password")
    if stored is not None:
        correct = stored == password
    else:
        correct = verify_password(
            password, user.get("password_hash", ""), user.get("password_salt", "")
        )
    if not correct:
        await message.answer("Неверный пароль. Попробуй ещё раз.")
        return
    await get_db().patch_user(
        message.from_user.id,
        {"logged_in": True, "login_at": datetime.now(timezone.utc).isoformat()},
    )
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=menu_keyboard(is_admin(message.from_user.id)))


# ------------------------- меню -------------------------

def buy_keyboard() -> InlineKeyboardMarkup:
    pairs = [(0, 1), (2, 3), (4, 5)]
    rows = [
        [
            InlineKeyboardButton(
                text=f"{DURATIONS[i]['label']} — {STARS[i]} ⭐", callback_data=f"buy:{i}"
            ),
            InlineKeyboardButton(
                text=f"{DURATIONS[j]['label']} — {STARS[j]} ⭐", callback_data=f"buy:{j}"
            ),
        ]
        for i, j in pairs
    ]
    for i in (6, 7):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{DURATIONS[i]['label']} — {STARS[i]} ⭐", callback_data=f"buy:{i}"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "🛒 Купить подписку")
@router.message(F.text == "🛒 Купить подписку (в разработке)")
async def buy_subscription(message: Message) -> None:
    if await is_blocked(message):
        return
    user = await get_db().get_user(message.from_user.id)
    if not user:
        await message.answer(GUEST_TEXT, reply_markup=guest_keyboard())
        return
    if not user.get("logged_in"):
        await message.answer(MEMBER_TEXT, reply_markup=login_keyboard())
        return
    await message.answer(
        "Оплата — Telegram Stars ⭐\nПосле оплаты бот сразу выдаст ключ.",
        reply_markup=buy_keyboard(),
    )


@router.callback_query(F.data.startswith("buy:"))
async def buy_callback(call: CallbackQuery) -> None:
    user = await get_db().get_user(call.from_user.id)
    if user and user.get("blocked"):
        await call.answer("Вы заблокированы", show_alert=True)
        return
    if not user or not user.get("logged_in"):
        await call.answer("Сначала войди в аккаунт", show_alert=True)
        return
    index = int(call.data.split(":")[1])
    if index < 0 or index >= len(STARS):
        await call.answer("Нет такого товара", show_alert=True)
        return
    duration = DURATIONS[index]
    await call.message.answer_invoice(
        title=f"Подписка: {duration['label']}",
        description=f"Syntetic Client | Legit 26.2 fabric — {duration['label']}",
        payload=f"buy:{index}",
        currency="XTR",
        prices=[LabeledPrice(label=duration["label"], amount=STARS[index])],
    )
    await call.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    try:
        index = int(str(query.payload).split(":")[1])
        valid = 0 <= index < len(STARS)
    except Exception:
        valid = False
    if valid:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Ошибка в заказе. Попробуй ещё раз.")


@router.message(F.successful_payment)
async def on_paid(message: Message) -> None:
    payment = message.successful_payment
    try:
        index = int(str(payment.payload).split(":")[1])
        duration = DURATIONS[index]
        stars = STARS[index]
    except Exception:
        await message.answer("Ошибка оплаты. Напиши админу.")
        return

    existing = set((await get_db().list_keys()).keys())
    key = generate_key(existing)
    if duration["days"] is None:
        until = FOREVER_DATE
    else:
        until = date.today() + timedelta(days=duration["days"])
    await get_db().save_key(
        key,
        {
            "key": key,
            "kind": duration["kind"],
            "label": duration["label"],
            "days": duration["days"],
            "until": until.isoformat(),
            "created_at": datetime.now().isoformat(),
            "used_by": None,
            "buyer": message.from_user.id,
            "stars": stars,
            "charge_id": payment.telegram_payment_charge_id,
        },
    )
    await message.answer(
        f"Оплачено: {stars} ⭐ ✅\n"
        f"Подписка: {duration['label']}\n\n"
        f"Твой ключ:\n{key}\n\n"
        "Активируй его кнопкой «🎟 Активировать ключ» — отсчёт начнётся с момента активации."
    )


def find_client_file() -> str | None:
    if config.CLIENT_FILE and os.path.isfile(config.CLIENT_FILE):
        return config.CLIENT_FILE
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client")
    if os.path.isdir(folder):
        files = [
            os.path.join(folder, name)
            for name in sorted(os.listdir(folder))
            if os.path.isfile(os.path.join(folder, name)) and not name.startswith(".")
        ]
        if files:
            return files[0]
    return None


@router.message(F.text == "📥 Скачать клиент")
async def download_client(message: Message) -> None:
    if await is_blocked(message):
        return
    if not await get_db().get_user(message.from_user.id):
        await message.answer(GUEST_TEXT, reply_markup=guest_keyboard())
        return
    path = find_client_file()
    if not path:
        await message.answer("Файл клиента ещё не добавлен.")
        return
    size = os.path.getsize(path)
    mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d.%m.%Y %H:%M")
    await message.answer_document(
        FSInputFile(path),
        caption=f"Syntetic Client | Legit 26.2 fabric\nSynteticLoader.exe • {size} байт • сборка {mtime}",
    )


@router.message(F.text == "👤 Профиль")
@router.message(Command("profile"))
@router.message(Command("me"))
async def cmd_profile(message: Message) -> None:
    if await is_blocked(message):
        return
    user = await get_db().get_user(message.from_user.id)
    if not user:
        await message.answer(GUEST_TEXT, reply_markup=guest_keyboard())
        return
    await message.answer(profile_text(user))


@router.message(F.text == "🚪 Выйти")
async def logout(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await get_db().get_user(message.from_user.id)
    if user:
        await get_db().patch_user(message.from_user.id, {"logged_in": False, "login_at": None})
    await message.answer(MEMBER_TEXT, reply_markup=login_keyboard())


# ------------------------- ключи -------------------------

@router.message(F.text == "🎟 Активировать ключ")
async def start_activate(message: Message, state: FSMContext) -> None:
    if await is_blocked(message):
        return
    if not await get_db().get_user(message.from_user.id):
        await message.answer(GUEST_TEXT, reply_markup=guest_keyboard())
        return
    await state.set_state(ActivateKey.key)
    await message.answer("Пришли ключ вида XXXX-XXXX-XXXX-XXXX:")


@router.message(ActivateKey.key, F.text)
async def got_key(message: Message, state: FSMContext) -> None:
    key = message.text.strip().upper()
    if not KEY_RE.match(key):
        await message.answer("Неверный формат ключа. Нужно: XXXX-XXXX-XXXX-XXXX")
        return
    record = await get_db().get_key(key)
    if not isinstance(record, dict):
        await message.answer("Такого ключа не существует ❌")
        return
    if record.get("used_by") is not None:
        await message.answer("Этот ключ уже был использован ❌")
        return

    if record.get("days") is not None:
        base = date.today()
        user_rec = await get_db().get_user(message.from_user.id)
        cur = ((user_rec or {}).get("subscription") or {}).get("until")
        try:
            cur_date = date.fromisoformat(cur)
            if cur_date > base:
                base = cur_date
        except Exception:
            pass
        if base >= FOREVER_DATE:
            until = FOREVER_DATE
        else:
            until = base + timedelta(days=int(record["days"]))
    else:
        try:
            until = date.fromisoformat(record.get("until"))
        except Exception:
            until = FOREVER_DATE

    subscription = {
        "kind": record.get("kind"),
        "label": record.get("label"),
        "until": until.isoformat(),
    }
    await get_db().patch_user(message.from_user.id, {"subscription": subscription})
    await get_db().consume_key(key, message.from_user.id)
    await state.clear()

    user = await get_db().get_user(message.from_user.id)
    await message.answer(
        "✅ Ключ активирован!\n" + subscription_text(user),
        reply_markup=menu_keyboard(is_admin(message.from_user.id)),
    )


# ------------------------- админ-панель -------------------------

@router.message(F.text == "🛠 Админ-панель")
@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer("Не понял команду. Нажми /start.", reply_markup=menu_keyboard())
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_keyboard())


@router.message(F.text == "🔙 Назад")
async def admin_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer("Не понял команду. Нажми /start.", reply_markup=menu_keyboard())
        return
    await message.answer(MENU_TEXT, reply_markup=menu_keyboard(admin=True))


@router.message(F.text == "🔑 Создать ключ")
async def create_key_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.set_state(CreateKey.duration)
    await message.answer("Выбери срок действия ключа:", reply_markup=durations_keyboard())


@router.callback_query(F.data.startswith("dur:"))
async def create_key_duration(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    index = int(call.data.split(":")[1])
    duration = DURATIONS[index]

    existing = set((await get_db().list_keys()).keys())
    key = generate_key(existing)

    if duration["days"] is None:
        until = FOREVER_DATE
    else:
        until = date.today() + timedelta(days=duration["days"])

    await get_db().save_key(
        key,
        {
            "key": key,
            "kind": duration["kind"],
            "label": duration["label"],
            "days": duration["days"],
            "until": until.isoformat(),
            "created_at": datetime.now().isoformat(),
            "used_by": None,
        },
    )
    await state.clear()

    if duration["days"] is None:
        term = f"навсегда (до {FOREVER_DATE.strftime('%d.%m.%Y')})"
    else:
        term = f"{duration['label']} — отсчёт с момента активации"
    text = (
        "🔑 Ключ создан\n\n"
        f"{key}\n\n"
        f"Срок: {duration['label']}\n"
        f"{term}\n"
        "Ключ начинает работать, когда его активируют."
    )
    await call.message.edit_text(text, reply_markup=None)
    await call.answer("Готово")


@router.message(F.text.in_({"🚫 Заблокировать", "🚫 Заблокировать пользователя"}))
async def block_list(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    users = await get_db().list_users()
    await message.answer(
        "Кого блокируем? (нажми на пользователя)",
        reply_markup=users_keyboard(users, show_blocked=False),
    )


@router.message(F.text.in_({"✅ Разблокировать", "✅ Разблокировать пользователя"}))
async def unblock_list(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    users = await get_db().list_users()
    await message.answer(
        "Кого разблокируем?",
        reply_markup=users_keyboard(users, show_blocked=True),
    )


@router.message(F.text == "📋 Пароли")
async def admin_passwords(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    users = await get_db().list_users()
    if not users:
        await message.answer("Пользователей нет.")
        return
    items = []
    for uid, u in sorted(users.items(), key=lambda kv: (kv[1] or {}).get("nickname") or ""):
        if not isinstance(u, dict):
            continue
        pwd = u.get("password") or "(старый аккаунт, пароль неизвестен)"
        items.append(f"{u.get('nickname') or uid}: {pwd}")
    for i in range(0, len(items), 8):
        chunk = items[i : i + 8]
        title = "📋 Пароли" if i == 0 else "📋 Пароли (продолжение)"
        await message.answer(f"{title}:\n" + "\n".join(chunk))


async def refresh_user_list(message: Message, show_blocked: bool) -> None:
    users = await get_db().list_users()
    text = "Список заблокированных:" if show_blocked else "Список пользователей:"
    try:
        await message.edit_text(text, reply_markup=users_keyboard(users, show_blocked))
    except Exception:
        await message.answer(text, reply_markup=users_keyboard(users, show_blocked))


@router.callback_query(F.data.startswith("blk:"))
async def cb_block(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    if uid in config.ADMIN_IDS:
        await call.answer("Админа заблокировать нельзя", show_alert=True)
        return
    await get_db().patch_user(uid, {"blocked": True, "logged_in": False})
    await call.answer("Заблокирован")
    await refresh_user_list(call.message, show_blocked=False)


@router.callback_query(F.data.startswith("ubk:"))
async def cb_unblock(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    await get_db().patch_user(uid, {"blocked": False})
    await call.answer("Разблокирован")
    await refresh_user_list(call.message, show_blocked=True)


@router.callback_query(F.data == "adm:none")
async def cb_none(call: CallbackQuery) -> None:
    await call.answer("Пусто")


@router.message(Command("count"))
async def cmd_count(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Не понял команду. Нажми /start.")
        return
    await message.answer(f"Всего зарегистрировано: {await get_db().count_users()}")


@router.message(F.text)
async def unknown_text(message: Message) -> None:
    user = await get_db().get_user(message.from_user.id)
    if not user:
        markup = guest_keyboard()
    elif user.get("logged_in"):
        markup = menu_keyboard(is_admin(message.from_user.id))
    else:
        markup = login_keyboard()
    await message.answer("Не понял команду. Нажми /start.", reply_markup=markup)


async def main() -> None:
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp.include_router(router)
    try:
        await backfill_uids()
    except Exception as exc:
        print(f"backfill error: {exc}")
    print("Bot started, polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
