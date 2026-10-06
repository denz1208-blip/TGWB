# 🔎 Telegram-бот: отслеживание новых ШК в Google Таблице

Бот периодически опрашивает публичную Google Таблицу (через CSV-экспорт, **без API-ключей**)
и рассылает подписчикам сообщения о новых штрихкодах (ШК).

Работает на Linux (проверено на Python 3.10+).

## Структура

```
tg_barcode_bot/
├── bot.py               # основной скрипт бота (aiogram 3)
├── sheet.py             # чтение Google Таблицы по публичной ссылке
├── state.py             # хранение известных ШК и подписчиков (state.json)
├── config.py            # настройки из .env
├── requirements.txt
├── .env.example         # шаблон настроек
└── barcode-bot.service  # unit-файл systemd для автозапуска
```

## Принцип работы

1. При первом запуске бот запоминает **все текущие ШК** таблицы как «известные» (старые не рассылаются).
2. Каждые `POLL_INTERVAL` секунд скачивает таблицу через `export?format=csv&gid=...`.
3. Сравнивает с сохранённым списком (`state.json`) и присылает всем подписчикам новые ШК
   вместе с данными строки (дата, ID, ФИО, статус).
4. Пользователи управляют подпиской командами.

## Команды бота

| Команда  | Действие                     |
|----------|------------------------------|
| `/start` | включить уведомления         |
| `/stop`  | выключить уведомления        |
| `/status`| статус подписки и счётчики   |
| `/help`  | справка                      |

Подписаться могут любые чаты/группы, куда написан `/start` — удобно для группового использования.

## Установка и запуск (Linux)

### 1. Получите токен бота
Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → скопируйте токен.

### 2. Настройте окружение

```bash
cd tg_barcode_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env          # вставьте BOT_TOKEN
```

> ⚠️ Таблица должна иметь доступ «Все, у кого есть ссылка — просмотрщик»,
> иначе бот не сможет её скачать. Ваша таблица уже открыта — проверять не нужно.

### 3. Запуск вручную (для проверки)

```bash
python bot.py
```

Затем найдите бота в Telegram и отправьте `/start`.

### 4. Автозапуск через systemd (продакшн) — одна команда

Токен бота уже вшит в `config.py` и `.env`, настраивать ничего не нужно:

```bash
sudo ./install.sh
```

Скрипт сам: установит зависимости, скопирует проект в `/opt/tg_barcode_bot`,
создаст venv, зарегистрирует сервис `barcode-bot` с автозапуском при загрузке
и перезапуском при падении, затем запустит бота.

Управление:
```bash
sudo systemctl status barcode-bot    # состояние
sudo systemctl restart barcode-bot   # перезапуск
sudo systemctl stop barcode-bot      # остановка
journalctl -u barcode-bot -f         # живые логи
```

<details>
<summary>Ручная установка (альтернатива)</summary>

```bash
sudo mkdir -p /opt/tg_barcode_bot
sudo cp -r . /opt/tg_barcode_bot
cd /opt/tg_barcode_bot
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
sudo sed -i "s|^User=.*|User=$(whoami)|" barcode-bot.service
sudo cp barcode-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now barcode-bot
journalctl -u barcode-bot -f
```
</details>

## Настройки (.env)

| Переменная         | Описание                                   | По умолчанию |
|--------------------|--------------------------------------------|--------------|
| `BOT_TOKEN`        | токен от @BotFather                        | — (обязательно) |
| `GOOGLE_SHEET_URL` | ссылка на таблицу                          | ссылка из задачи |
| `POLL_INTERVAL`    | период опроса, сек                         | 60 |
| `BARCODE_COLUMN`   | имя колонки со ШК                          | `ШК` |
| `STATE_FILE`       | путь к файлу состояния                     | `state.json` |

## Возможные доработки

- Уведомления об **изменении статуса** существующих ШК (сейчас шлются только новые).
- Голосовой/кнопки-инлайн вместо команд.
- Переход на Google Sheets API (service account), если закроете общий доступ к таблице.
