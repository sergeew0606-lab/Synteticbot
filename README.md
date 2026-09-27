# Synteticbot — регистрация с проверкой и базой Firebase

Бот: **@SynteticLegitBot**
Стек: Python 3.11 + aiogram 3, база — **Firebase Realtime Database** (бесплатный тариф Spark, закрыта от посторонних).

## Как работает регистрация

1. `/start` → гостю показывается «Здравствуй пользователь нашего клиента / сначала пройдите регистрацию…», уже зарегистрированному — «…сначала зайдите в аккаунт…»
2. Регистрация: никнейм → пароль (капчи больше нет)
3. После входа — меню: купить подписку (в разработке), активировать ключ, профиль, выход
4. Данные сохраняются в Firebase, повторная регистрация невозможна

Команды: `/start` `/register` `/login` `/profile` `/help`

Профиль (`/profile`) показывает никнейм, username, дату регистрации (с годом) и HWID. Telegram ID нигде не показывается.

## Сессия

- Сессия в аккаунте живёт **2 дня**: после этого бот сам выкидывает из аккаунта и просит войти заново (проверка, что это точно вы).

## Админ-панель

Доступна только с ID из `ADMIN_IDS` (по умолчанию `8711035827`) — другим пользователям она не видна.

- Создание ключа `XXXX-XXXX-XXXX-XXXX` (символы не повторяются, ключ уникален) со сроком: 1/7/14 дней, 1/6 месяцев, 1 год, навсегда, бета среднего/высшего уровня (бета и «навсегда» — до 31.12.2044)
- Список пользователей: блокировка / разблокировка

Подписка хранится в `users/<id>/subscription`, ключи — в `keys/<key>`.

## Настройка Firebase (5 минут)

1. Зайди на https://console.firebase.google.com → **Add project** (бесплатно, аналитику можно отключить)
2. В проекте: **Build → Realtime Database → Create database** → выбери регион → режим **test mode** (потом закроем)
3. Скопируй URL базы (вида `https://xxxx-default-rtdb.firebaseio.com`) → в `FIREBASE_DB_URL`
4. **Project settings → Service accounts → Database secrets** → скопируй секрет → в `FIREBASE_AUTH_SECRET`
5. Вернись в Realtime Database → **Rules** → вставь содержимое `firebase-rules.json` → **Publish**

Правила запрещают весь доступ по умолчанию: базу не прочитать ни по ссылке, ни анонимным ключом. Бот обращается по секретному ключу, который лежит только в `.env` (файл в `.gitignore`, в git не попадает).

Структура данных:
```
users/
  <telegram_id>/
    user_id, username, first_name, full_name, registered_at
```

## Запуск локально

```bash
pip install -r requirements.txt
python bot.py
```

## Хостинг 24/7 (бесплатно, Render)

1. Залей папку на GitHub (файл `.env` не коммитить)
2. https://render.com → **New → Web Service** → выбери репозиторий
3. Build command: `pip install -r requirements.txt`
   Start command: `python bot.py`
4. В **Environment** добавь: `BOT_TOKEN`, `FIREBASE_DB_URL`, `FIREBASE_AUTH_SECRET`
5. Deploy — бот работает круглосуточно

## Файлы

| Файл | Назначение |
|---|---|
| `bot.py` | логика бота и регистрация |
| `db.py` | работа с Firebase Realtime Database (REST API) |
| `config.py` | чтение `.env` |
| `firebase-rules.json` | правила доступа (закрыть базу для всех) |
| `.env` | секреты (не коммитить!) |
