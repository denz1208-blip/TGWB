"""Чтение Google Таблицы по публичной ссылке (экспорт в CSV), без API-ключей."""
import csv
import io
import re

import aiohttp

# Регулярка для извлечения ID таблицы и gid из ссылки
_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
_GID_RE = re.compile(r"gid=(\d+)")


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


async def fetch_new_barcodes(session: aiohttp.ClientSession, sheet_url: str, barcode_column: str):
    """Возвращает множество непустых ШК из указанной колонки и словарь ШК -> данные строки."""
    rows = await fetch_rows(session, sheet_url)
    known: dict[str, dict] = {}
    for row in rows:
        code = row.get(barcode_column, "")
        if code:
            known[code] = row
    return known
