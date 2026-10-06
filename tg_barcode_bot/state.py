"""Хранилище состояния: известные ШК и список подписчиков. Сохраняется в JSON-файл."""
import json
import os
import threading


class State:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.seen_barcodes: set[str] = set()
        self.subscribers: set[int] = set()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.seen_barcodes = set(data.get("seen_barcodes", []))
            self.subscribers = set(data.get("subscribers", []))
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
