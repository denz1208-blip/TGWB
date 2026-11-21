"""Чтение Google Таблицы по публичной ссылке (экспорт в CSV), без API-ключей."""
import csv
import io
import re
from urllib.parse import urlparse

import aiohttp

# Регулярка для извлечения ID таблицы и gid из ссылки
_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
_GID_RE = re.compile(r"gid=(\d+)")


def normalize_sheet_url(sheet_url: str) -> str:
    """Проверить и нормализовать ссылку на Google-таблицу пользователя."""
    url = (sheet_url or "").strip()
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError("Нужна ссылка, начинающаяся с https://")
    host = (urlparse(url).hostname or "").lower()
    if host != "docs.google.com" and not host.endswith(".docs.google.com"):
        raise ValueError("Разрешены только ссылки docs.google.com")
    if not _SHEET_ID_RE.search(url):
        raise ValueError("Не похоже на ссылку Google Таблицы (/spreadsheets/d/...)")
    return url


def build_csv_export_url(sheet_url: str) -> str:
    """Превращает обычную ссылку на таблицу в ссылку на CSV-экспорт конкретного листа."""
    m = _SHEET_ID_RE.search(sheet_url)
    if not m:
        raise ValueError(f"Не удалось распознать ссылку на Google Таблицу: {sheet_url}")
    sheet_id = m.group(1)
    gid_match = _GID_RE.search(sheet_url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


async def fetch_rows(session: aiohttp.ClientSession, sheet_url: str) -> list[dict[str, str]]:
    """Скачивает таблицу как CSV и возвращает список строк-словарей (ключи — заголовки колонок)."""
    url = build_csv_export_url(sheet_url)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise RuntimeError(
                f"Google вернул статус {resp.status}. "
                "Проверьте, что таблица открыта по ссылке ('Все, у кого есть ссылка')."
            )
        text = await resp.text()

    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        # очищаем ключи/значения от BOM и пробелов
        clean = {(k or "").strip().lstrip("\ufeff"): (v or "").strip() for k, v in row.items()}
        rows.append(clean)
    return rows


async def fetch_barcodes(
    session: aiohttp.ClientSession,
    sheet_url: str,
    barcode_column: str,
    status_column: str = "",
    employee_id_column: str = "",
    target_employee_ids: set[str] | None = None,
) -> dict[str, dict]:
    """Возвращает словарь ШК -> данные строки с учётом фильтров.

    Фильтры (применяются к строкам таблицы):
      * строка должна иметь непустой ШК;
      * если задан ``status_column`` — колонка статуса должна быть ПУСТОЙ;
      * если заданы ``employee_id_column`` и непустой ``target_employee_ids`` —
        ID сотрудника в строке должен входить в список (пустой список = без фильтра).
    """
    rows = await fetch_rows(session, sheet_url)
    result: dict[str, dict] = {}
    for row in rows:
        code = row.get(barcode_column, "")
        if not code:
            continue
        # Фильтр по пустому статусу
        if status_column and row.get(status_column, "").strip():
            continue
        # Фильтр по ID сотрудника
        if target_employee_ids and employee_id_column:
            emp_id = row.get(employee_id_column, "").strip()
            if emp_id not in target_employee_ids:
                continue
        result[code] = row
    return result


async def fetch_barcodes_by_employee(
    session: aiohttp.ClientSession,
    sheet_url: str,
    barcode_column: str,
    employee_id_column: str,
    employee_id: str,
) -> list[dict]:
    """Возвращает ВСЕ строки таблицы для указанного ID сотрудника (без фильтра по статусу).

    Каждый элемент — dict с полями: barcode, date, status, decision, name.
    Отсортировано по дате создания (сначала новые); даты парсятся наудачу,
    нераспознанные остаются в исходном порядке.
    """
    rows = await fetch_rows(session, sheet_url)
    found = []
    for row in rows:
        if row.get(employee_id_column, "").strip() != employee_id:
            continue
        code = row.get(barcode_column, "")
        if not code:
            continue
        found.append(
            {
                "barcode": code,
                "date": row.get("Дата создания", ""),
                "status": row.get("Статус", ""),
                "decision": row.get("Решение по заявке", ""),
                "name": row.get("ФИО", ""),
            }
        )

    import datetime as _dt

    def _parse_date(s: str):
        s = (s or "").strip()
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                return _dt.datetime.strptime(s, fmt)
            except ValueError:
                pass
        return None

    parsed = [(_parse_date(x["date"]), x) for x in found]
    with_dates = sorted(
        (p for p in parsed if p[0] is not None), key=lambda p: p[0], reverse=True
    )
    without = [x for d, x in parsed if d is None]
    return [x for _, x in with_dates] + without


# Совместимость со старым именем
fetch_new_barcodes = fetch_barcodes
