<div align="center">

# 🔎 TGWB — персональный Telegram-бот отслеживания ШК

**Каждый пользователь — со своим аккаунтом: свои ID сотрудников, свои уведомления, своя Google-таблица.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white)
![Version](https://img.shields.io/badge/version-3.0.0-brightgreen)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux&logoColor=black)
![Polling](https://img.shields.io/badge/mode-polling-important)

[📖 Установка на Linux](INSTALL_LINUX.md) · [🤖 README бота](tg_barcode_bot/README.md) · [📝 Коммит v3](https://github.com/denz1208-blip/TGWB/commit/eb59012e134b1e27573e7100d96508b4121e6975)

</div>

---

## ✨ Возможности

| Возможность | Описание |
|-------------|----------|
| 👤 Личный аккаунт | Создаётся автоматически при первом сообщении боту. Ключ — Telegram ID. |
| 🎯 Свои ID сотрудников | Каждый пользователь настраивает свой список фильтров. |
| 📬 Свои уведомления | Только ваши новые ШК, только с пустым статусом, только в ваши чаты. |
| 📄 Своя таблица | `/sheet <ссылка>` — персональная Google-таблица; `/sheet reset` — общая. |
| 🕓 Своя история | Команда «🆕 Мои новые ШК» показывает последние 20 ваших событий. |
| 🔐 Общий контроль доступа | `/access` и `/users` доступны только администраторам. |
| ⚙️ Без API-ключей | Таблица читается через публичный CSV-экспорт. |
| 🚀 Простой деплой | Одна команда `sudo ./install.sh` поднимает systemd-сервис. |

## 🚀 Быстрый старт на сервере

```bash
# 1. Клонировать репозиторий
sudo git clone https://github.com/denz1208-blip/TGWB.git /opt/TGWB_src

# 2. Настроить токен бота (получить у @BotFather)
sudo nano /opt/TGWB_src/tg_barcode_bot/.env

# 3. Установить и запустить как сервис
cd /opt/TGWB_src/tg_barcode_bot
sudo ./install.sh

# 4. Проверить
sudo systemctl status barcode-bot
journalctl -u barcode-bot -f
```

Полная пошаговая инструкция, настройки, обновление, бэкапы и устранение неполадок:
**[📖 INSTALL_LINUX.md](INSTALL_LINUX.md)**

## 🤖 Команды бота

| Команда | Что делает |
|---------|------------|
| `/start` | Открыть своё меню и создать аккаунт |
| `/status` | Состояние вашего аккаунта |
| `🆕 Мои новые ШК` | Последние 20 ваших уведомлений |
| `🔔 / 🔕` | Включить / выключить вашу рассылку |
| `🔎 Поиск по ID` | Последние 20 ШК сотрудника в вашей таблице |
| `👥 Отслеживание` | Ваш список ID сотрудников |
| `/ids clear` | Следить за всеми сотрудниками |
| `/sheet <ссылка>` | Задать свою Google-таблицу |
| `/sheet reset` | Вернуться к общей таблице |
| `/id` , `/help` , `/version` | ID, справка, версия и хеш кода |
| `/access ...` , `/users` | Доступ и список аккаунтов (админы) |

## 📁 Структура репозитория

```
TGWB/
├── README.md              # эта страница
├── INSTALL_LINUX.md       # подробная установка на Linux-сервер
└── tg_barcode_bot/
    ├── bot.py             # логика бота и мониторинг
    ├── state.py           # аккаунты пользователей (state.json v2)
    ├── sheet.py           # чтение Google Таблицы по CSV
    ├── config.py          # настройки из .env
    ├── requirements.txt
    ├── .env.example
    ├── barcode-bot.service
    └── install.sh / reinstall.sh / update.sh / watchdog.sh / start.sh
```

## 🔄 Обновление

```bash
cd /opt/tg_barcode_bot && sudo ./reinstall.sh
```

Скрипт подтянет свежий код, сохранит `.env` и `state.json` — аккаунты пользователей не потеряются. Старый `state.json` версии 1 конвертируется автоматически.

## ⚠️ Безопасность

- Никогда не публикуйте `.env` и токен бота; при утечке — `/revoke` у [@BotFather](https://t.me/BotFather);
- если GitHub-токен был показан в чате — отзовите его и создайте новый;
- `state.json` и `.env` добавлены в `.gitignore`.

---

<div align="center">

Сделано для удобной работы с новыми штрихкодами 💙  
[Открыть руководство по установке →](INSTALL_LINUX.md)

</div>
