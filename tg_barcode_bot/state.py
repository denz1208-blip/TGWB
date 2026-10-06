"""Хранилище состояния: известные ШК, подписчики и ID сотрудников (настраиваемые).

Сохраняется в JSON-файл. ID сотрудников можно менять прямо из Telegram
(/ids add, /ids remove) — значения из .env используются как стартовые,
а текущий список хранится здесь же.
"""
import json
import os
import threading


class State:
    def __init__(self, path: str, initial_employee_ids: set[str] | None = None):
        self.path = path
        self._lock = threading.Lock()
        self.seen_barcodes: set[str] = set()
        self.subscribers: set[int] = set()
        self.employee_ids: set[str] = set(initial_employee_ids or ())
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.seen_barcodes = set(data.get("seen_barcodes", []))
            self.subscribers = set(data.get("subscribers", []))
            if "employee_ids" in data:
                self.employee_ids = {str(x) for x in data["employee_ids"]}
        except (json.JSONDecodeError, OSError):
            # повреждённый файл — начинаем с чистого листа
            pass

    def save(self) -> None:
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "seen_barcodes": sorted(self.seen_barcodes),
                        "subscribers": sorted(self.subscribers),
                        "employee_ids": sorted(self.employee_ids),
                    },
                    f,
                    ensure_ascii=False,
                    indent=1,
                )
            os.replace(tmp, self.path)

    def add_seen(self, barcode: str) -> None:
        self.seen_barcodes.add(barcode)

    def is_seen(self, barcode: str) -> bool:
        return barcode in self.seen_barcodes

    def subscribe(self, chat_id: int) -> bool:
        """Возвращает True, если чат был добавлен (до этого его не было)."""
        if chat_id in self.subscribers:
            return False
        self.subscribers.add(chat_id)
        return True

    def unsubscribe(self, chat_id: int) -> bool:
        if chat_id not in self.subscribers:
            return False
        self.subscribers.discard(chat_id)
        return True

    # ---------------- ID сотрудников (настраиваемый фильтр) -----------------

    def add_employee_ids(self, ids: list[str]) -> list[str]:
        """Добавляет ID, возвращает список реально добавленных."""
        added = []
        for x in ids:
            if x and x not in self.employee_ids:
                self.employee_ids.add(x)
                added.append(x)
        return added

    def remove_employee_ids(self, ids: list[str]) -> list[str]:
        """Удаляет ID, возвращает список реально удалённых."""
        removed = []
        for x in ids:
            if x in self.employee_ids:
                self.employee_ids.discard(x)
                removed.append(x)
        return removed
