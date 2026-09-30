from datetime import datetime, timezone

import httpx

import config


class Database:
    def __init__(self) -> None:
        if not config.FIREBASE_DB_URL or not config.FIREBASE_AUTH_SECRET:
            raise RuntimeError("FIREBASE_DB_URL и FIREBASE_AUTH_SECRET не заданы в .env")
        self._root = config.FIREBASE_DB_URL.rstrip("/")
        self._base = self._root + "/users"
        self._secret = config.FIREBASE_AUTH_SECRET

    def _url(self, path: str = "") -> str:
        return f"{self._base}{path}.json?auth={self._secret}"

    def _keys_url(self, path: str = "") -> str:
        return f"{self._root}/keys{path}.json?auth={self._secret}"

    def _loader_url(self) -> str:
        return f"{self._root}/loader.json?auth={self._secret}"

    async def get_loader(self) -> dict | None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self._loader_url())
            resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None

    async def set_loader(self, payload: dict) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(self._loader_url(), json=payload)
            resp.raise_for_status()

    async def get_user(self, user_id: int) -> dict | None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self._url(f"/{user_id}"))
            resp.raise_for_status()
        return resp.json()

    async def create_user(
        self,
        user_id: int,
        nickname: str,
        password: str,
        uid: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> dict:
        payload = {
            "user_id": user_id,
            "nickname": nickname,
            "password": password,
            "uid": uid,
            "username": username,
            "first_name": first_name,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "logged_in": True,
            "login_at": datetime.now(timezone.utc).isoformat(),
            "blocked": False,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.put(self._url(f"/{user_id}"), json=payload)
            resp.raise_for_status()
        return resp.json()

    async def patch_user(self, user_id: int, patch: dict) -> dict | None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(self._url(f"/{user_id}"), json=patch)
            resp.raise_for_status()
        return resp.json()

    async def list_users(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self._url())
            resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    async def set_hwid(self, user_id: int, hwid: str) -> None:
        await self.patch_user(user_id, {"hwid": hwid})

    async def find_by_nickname(self, nickname: str) -> dict | None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self._base}.json",
                params={
                    "auth": self._secret,
                    "orderBy": '"nickname"',
                    "equalTo": f'"{nickname}"',
                    "limitToFirst": "1",
                },
            )
            resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data:
            return next(iter(data.values()))
        return None

    async def count_users(self) -> int:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self._url() + "&shallow=true")
            resp.raise_for_status()
        data = resp.json()
        return len(data) if isinstance(data, dict) else 0

    async def list_keys(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self._keys_url())
            resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    async def get_key(self, key: str) -> dict | None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self._keys_url(f"/{key}"))
            resp.raise_for_status()
        return resp.json()

    async def save_key(self, key: str, payload: dict) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.put(self._keys_url(f"/{key}"), json=payload)
            resp.raise_for_status()

    async def consume_key(self, key: str, user_id: int) -> None:
        await self._patch_key(key, {"used_by": user_id, "used_at": datetime.now(timezone.utc).isoformat()})

    async def _patch_key(self, key: str, patch: dict) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(self._keys_url(f"/{key}"), json=patch)
            resp.raise_for_status()
