import asyncio
import sys

from db import Database


async def main() -> None:
    if len(sys.argv) != 3:
        print("Использование: python setpass.py <никнейм> <новый пароль>")
        return
    nickname, password = sys.argv[1], sys.argv[2]
    if not 6 <= len(password) <= 64:
        print("Пароль должен быть от 6 до 64 символов.")
        return
    db = Database()
    user = await db.find_by_nickname(nickname)
    if not user:
        print(f"Пользователь {nickname} не найден.")
        return
    await db.patch_user(
        int(user["user_id"]),
        {"password": password, "password_hash": None, "password_salt": None},
    )
    print(f"OK: у {nickname} теперь открытый пароль: {password}")


asyncio.run(main())
