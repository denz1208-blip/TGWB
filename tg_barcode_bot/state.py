"""Хранилище состояния с отдельным «аккаунтом» на каждого пользователя Telegram.

В state.json теперь лежит Notion-подобная структура:

{
  "version": 2,
  "allowed_users": [...],          # глобальный белый список (админы)
  "accounts": {
    "810321569": {                  # ключ — Telegram ID пользователя
      "username": "...",
      "employee_ids": [...],        # его список отслеживаемых ID сотрудников
      "seen_barcodes": [...],       # его уже известные ШК
      "subscribed_chats": [...],    # его чаты, куда слать уведомления
      "newest_notifications": {},   # его личная лента «Мои новые ШК»
      "last_lookup_id": "...",
      "sheet_url": "...",           # его личная Google-таблица (пусто = общая)
      "initialized": true,          # первый опрос уже сделан (старые ШК не шлём)
      "created_at": "..."
    }
  }
}

Старый state.json версии 1 (одни общие данные) при первом запуске автоматически
конвертируется: settings достаются админам из ALLOWED_USER_IDS.
"""
import datetime
import json
import os
import threading

import config


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class Account:
    """Личный аккаунт отслеживания одного пользователя Telegram."""

    def __init__(self, user_id: int, initial_employee_ids=None, username: str = ""):
        self.user_id: int = int(user_id)
        self.username: str = username or ""
        self.employee_ids: set[str] = {
            str(x) for x in (initial_employee_ids or ()) if str(x).strip()
        }
        self.seen_barcodes: set[str] = set()
        self.subscribed_chats: set[int] = set()
        self.newest_notifications: dict[str, dict] = {}
        self.last_lookup_id: str = ""
        self.sheet_url: str = ""  # пусто = использовать config.GOOGLE_SHEET_URL
        self.initialized: bool = False  # был ли уже первый опрос таблицы
        self.created_at: str = _now()

    # ----------------------------- Сериализация ------------------------------

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "employee_ids": sorted(self.employee_ids),
            "seen_barcodes": sorted(self.seen_barcodes),
            "subscribed_chats": sorted(self.subscribed_chats),
            "newest_notifications": self.newest_notifications,
            "last_lookup_id": self.last_lookup_id,
            "sheet_url": self.sheet_url,
            "initialized": self.initialized,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, user_id: int, data: dict) -> "Account":
        acc = cls(int(user_id), data.get("employee_ids", ()), data.get("username", ""))
        acc.seen_barcodes = {str(x) for x in data.get("seen_barcodes", [])}
        acc.subscribed_chats = {int(x) for x in data.get("subscribed_chats", [])}
        acc.newest_notifications = dict(data.get("newest_notifications", {}))
        acc.last_lookup_id = str(data.get("last_lookup_id", "") or "")
        acc.sheet_url = str(data.get("sheet_url", "") or "")
        acc.initialized = bool(data.get("initialized", acc.initialized))
        acc.created_at = str(data.get("created_at", "") or acc.created_at)
        return acc

    # ------------------------------ Подписки ---------------------------------

    def subscribe(self, chat_id: int) -> bool:
        chat_id = int(chat_id)
        if chat_id in self.subscribed_chats:
            return False
        self.subscribed_chats.add(chat_id)
        return True

    def unsubscribe(self, chat_id: int) -> bool:
        chat_id = int(chat_id)
        if chat_id not in self.subscribed_chats:
            return False
        self.subscribed_chats.discard(chat_id)
        return True

    def unsubscribe_all(self) -> int:
        """Выключить все уведомления пользователя. Возвращает число чатов."""
        n = len(self.subscribed_chats)
        self.subscribed_chats.clear()
        return n

    def is_subscribed(self, chat_id: int | None = None) -> bool:
        if chat_id is None:
            return bool(self.subscribed_chats)
        return int(chat_id) in self.subscribed_chats

    # -------------------------- ID сотрудников --------------------------------

    def add_employee_ids(self, ids) -> list[str]:
        added = []
        for x in ids:
            x = str(x).strip()
            if x and x not in self.employee_ids:
                self.employee_ids.add(x)
                added.append(x)
        return added

    def remove_employee_ids(self, ids) -> list[str]:
        removed = []
        for x in ids:
            x = str(x).strip()
            if x in self.employee_ids:
                self.employee_ids.discard(x)
                removed.append(x)
        return removed

    # ------------------------- ШК и уведомления --------------------------------

    def add_seen(self, barcode: str) -> None:
        self.seen_barcodes.add(barcode)

    def is_seen(self, barcode: str) -> bool:
        return barcode in self.seen_barcodes

    MAX_NOTIFICATIONS = 20

    def push_notification(self, barcode: str, row: dict) -> None:
        """Добавить отправленное уведомление в личную ленту (не более 20)."""
        self.newest_notifications[barcode] = row
        if len(self.newest_notifications) > self.MAX_NOTIFICATIONS:
            extra = len(self.newest_notifications) - self.MAX_NOTIFICATIONS
            for key in list(self.newest_notifications)[:extra]:
                self.newest_notifications.pop(key, None)

    def reset_tracking(self) -> None:
        """Сбросить известные ШК (например, при смене таблицы)."""
        self.seen_barcodes.clear()
        self.newest_notifications.clear()
        self.initialized = False


class State:
    def __init__(self, path: str, initial_employee_ids=None):
        self.path = path
        self.initial_employee_ids = set(initial_employee_ids or ())
        self._lock = threading.Lock()
        # Глобальный белый список. Пусто = доступ разрешён всем.
        self.allowed_users: set[int] = set()
        # Личные аккаунты: Telegram ID -> Account
        self.accounts: dict[int, Account] = {}
        self._load()

    # ------------------------------- Загрузка ---------------------------------

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return  # повреждённый файл — начинаем с чистого листа

        self.allowed_users = {int(x) for x in data.get("allowed_users", [])}

        raw_accounts = data.get("accounts")
        if isinstance(raw_accounts, dict):
            for uid_str, adata in raw_accounts.items():
                try:
                    uid = int(uid_str)
                    self.accounts[uid] = Account.from_dict(uid, adata)
                except (ValueError, TypeError, AttributeError):
                    continue
            return

        # Миграция со старого формата (один общий аккаунт для всех).
        self._migrate_legacy(data)

    def _migrate_legacy(self, data: dict) -> None:
        legacy_chats = {int(x) for x in data.get("subscribers", [])}
        owners = set(config.ALLOWED_USER_IDS) | self.allowed_users
        if not owners and len(legacy_chats) == 1:
            # Один подписчик и нет админов — почти наверняка это владелец бота.
            owners = set(legacy_chats)
        if not owners:
            # Нет известных администраторов — старые настройки некому приписать.
            # Новые аккаунты создадутся с чистого листа при первом /start.
            return
        legacy_seen = {str(x) for x in data.get("seen_barcodes", [])}
        legacy_ids = {str(x) for x in data.get("employee_ids", [])}
        legacy_last = str(data.get("last_lookup_id", "") or "")
        legacy_notes = dict(data.get("newest_notifications", {}))

        for uid in owners:
            acc = self.get_account(uid)
            acc.employee_ids = set(legacy_ids) or set(self.initial_employee_ids)
            acc.seen_barcodes = set(legacy_seen)
            acc.newest_notifications = dict(legacy_notes)
            acc.last_lookup_id = legacy_last
            # В старом формате chat.id личного чата совпадает с user_id.
            acc.subscribed_chats = (
                {uid} if uid in legacy_chats else
                (set(legacy_chats) if len(owners) == 1 else set())
            )
            acc.initialized = bool(legacy_seen)
        self.save()

    # ------------------------------- Аккаунты ---------------------------------

    def get_account(self, user_id: int | None, username: str = "") -> Account:
        """Вернуть аккаунт пользователя, создав при первом обращении."""
        uid = int(user_id or 0)
        acc = self.accounts.get(uid)
        if acc is None:
            acc = Account(uid, self.initial_employee_ids, username)
            self.accounts[uid] = acc
            self.save()
        elif username and acc.username != username:
            acc.username = username
            self.save()
        return acc

    def all_accounts(self) -> list[Account]:
        return list(self.accounts.values())

    # ------------------------- Белый список (админы) --------------------------

    def admin_ids(self) -> set[int]:
        return set(config.ALLOWED_USER_IDS) | self.allowed_users

    def allowed_ids(self) -> set[int]:
        return self.admin_ids()

    def is_allowed(self, user_id: int | None) -> bool:
        lst = self.allowed_ids()
        if not lst:
            return True
        return user_id is not None and int(user_id) in lst

    def add_allowed(self, ids) -> list[int]:
        added = []
        for x in ids:
            x = int(x)
            if x and x not in self.allowed_users:
                self.allowed_users.add(x)
                added.append(x)
        return added

    def remove_allowed(self, ids) -> list[int]:
        removed = []
        for x in ids:
            x = int(x)
            if x in self.allowed_users:
                self.allowed_users.discard(x)
                removed.append(x)
        return removed

    def clear_allowed(self) -> None:
        self.allowed_users.clear()

    # ------------------------------- Сохранение -------------------------------

    def save(self) -> None:
        payload = {
            "version": 2,
            "allowed_users": sorted(self.allowed_users),
            "accounts": {
                str(uid): acc.to_dict()
                for uid, acc in sorted(self.accounts.items())
            },
        }
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
