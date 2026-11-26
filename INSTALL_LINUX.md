<div align="center">

# 📖 Установка TGWB на Linux-сервер

**Полная инструкция: от чистого VPS до работающего бота с автозапуском.**

[⬅️ На главную](README.md) · [🤖 README бота](tg_barcode_bot/README.md)

</div>

---

## 0. Что понадобится

| Требование | Комментарий |
|------------|-------------|
| VPS/VDS с Ubuntu 22.04/24.04 или Debian 11/12 | Подойдёт любой хостинг с root-доступом |
| Python 3.10+ | Ставится автоматически через `apt` |
| Токен Telegram-бота | Получить у [@BotFather](https://t.me/BotFather) |
| Google-таблица | Доступ «**Все, у кого есть ссылка — просмотрщик**» |
| Исходящий интернет | `api.telegram.org` и `docs.google.com` |
| Домен и открытые порты | ❌ **Не нужны** — бот работает через polling |

> Бот использует обычный `getUpdates`, поэтому вебхук, HTTPS и домен настраивать не нужно.

---

## 1. Получить токен бота

1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Придумайте имя и username, скопируйте выданный токен вида `123456789:AA...`.
3. Если токен уже был где-то опубликован — сделайте `/revoke` и используйте новый.

Токен понадобится на шаге 4.

---

## 2. Подготовить сервер

Подключитесь по SSH и обновите систему:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git ca-certificates curl
python3 --version   # должна быть 3.10 или новее
```

---

## 3. Скачать код

```bash
sudo git clone https://github.com/denz1208-blip/TGWB.git /opt/TGWB_src
cd /opt/TGWB_src/tg_barcode_bot
ls -la
```

Если репозиторий приватный:

```bash
sudo GITHUB_TOKEN=ghp_... git clone \
  https://ghp_...@github.com/denz1208-blip/TGWB.git /opt/TGWB_src
```

> ⚠️ Не сохраняйте токен в истории команд постоянного пользователя. Для сервера лучше
> положить его в `/etc/barcode-bot-token` (см. раздел «Обновление»).

---

## 4. Добавить токен — файл редактировать НЕ нужно

Просто запустите:

```bash
cd /opt/TGWB_src/tg_barcode_bot
sudo ./setup.sh
```

Скрипт сам спросит токен (и, по желанию, ссылку на таблицу), создаст файл `.env`
и выведет его скрытый вид. Можно и одной командой, без вопросов:

```bash
sudo ./setup.sh "123456789:AA..." "https://docs.google.com/spreadsheets/d/.../edit?gid=0#gid=0"
```

> На локальном Windows-компьютере запустите `setup.bat` — он делает то же самое.

Если сервис уже установлен, `setup.sh` перезапустит его автоматически.

### Что именно он делает

- записывает `BOT_TOKEN` в `/opt/tg_barcode_bot/.env` (если бот уже стоит) или рядом со скриптом;
- не стирает остальные настройки, если `.env` уже был;
- ставит права `600` на файл с секретом.

### Дополнительно (менять не обязательно)

Все прочие настройки уже имеют значения по умолчанию в `config.py`:

| Переменная | Что задаёт | По умолчанию |
|------------|------------|--------------|
| `GOOGLE_SHEET_URL` | Общая таблица | ссылка из репозитория |
| `POLL_INTERVAL` | Период проверки, сек | `60` |
| `BARCODE_COLUMN` / `STATUS_COLUMN` / `EMPLOYEE_ID_COLUMN` | Имена колонок | `ШК` / `Статус` / `ID` |
| `TARGET_EMPLOYEE_IDS` | Стартовые ID новых аккаунтов | `5978877` |
| `ALLOWED_USER_IDS` | Админы; пусто = доступ всем | пусто |

Если захотите что-то поменять, используйте тот же `setup.sh` или добавьте строку
в `/opt/tg_barcode_bot/.env` вручную и перезапустите сервис.

Советы:

- сначала оставьте доступ открытым, напишите боту `/id`, узнайте свой ID и только
  потом задайте `ALLOWED_USER_IDS=<ваш ID>`;
- таблица должна быть открыта: «Все, у кого есть ссылка» → **Просмотрщик**.

---

## 5. Установить и запустить сервис

```bash
cd /opt/TGWB_src/tg_barcode_bot
sudo ./install.sh
```

Скрипт сделает всё сам:

1. Установит недостающие пакеты Python.
2. Скопирует файлы в `/opt/tg_barcode_bot`.
3. Создаст виртуальное окружение `venv` и поставит `requirements.txt`.
4. Создаст systemd-юнит `barcode-bot` с автозапуском и перезапуском при падении.
5. Запустит бота.

Если бот уже был установлен, `install.sh` **сохранит текущий `.env`** из `/opt/tg_barcode_bot`.

---

## 6. Проверить работу

```bash
sudo systemctl status barcode-bot --no-pager
journalctl -u barcode-bot -f
```

Ожидаемая строка в логе:

```
Бот запущен. Версия: 3.3.2 (код: xxxxxxx). Аккаунтов: 0. Интервал: 60 сек.
```

Управление сервисом:

```bash
sudo systemctl restart barcode-bot   # перезапуск
sudo systemctl stop barcode-bot      # остановка
sudo systemctl enable barcode-bot    # включить автозапуск
sudo systemctl disable barcode-bot   # выключить автозапуск
journalctl -u barcode-bot -n 100     # последние логи
```

---

## 7. Настроить бота в Telegram

1. Найдите своего бота по username и отправьте `/start`.
2. `/status` — проверьте свой аккаунт (ID, список ID сотрудников, таблица, подписка).
3. `/id` — ваш Telegram ID (для `ALLOWED_USER_IDS`).
4. `🔔 Включить` — включить уведомления.
5. Отправьте ID сотрудника из таблицы (например, `112946`) или `+112946` — добавить в свой список.
6. `/stats` (кнопка «📊 Статистика») — сколько новых ШК было за день и сколько осталось со статусом «В работе» (точное совпадение).
7. Кнопка «📋 В работе» — список заявок со статусом «В работе» и их «Решение по заявке».
8. `/sheet <ссылка>` — если нужна своя таблица; `/sheet reset` — вернуться к общей.
9. `/access add <Telegram ID>` — разрешить другим пользователям (только для админов).
10. `/users` — посмотреть все созданные аккаунты.

**Как работают уведомления:** первое обращение к таблице просто запоминает текущие ШК —
старые строки не рассылаются. Далее приходят только новые ШК с пустым статусом и от ваших ID.

---

## 8. Обновление бота

```bash
cd /opt/tg_barcode_bot
sudo ./reinstall.sh
```

Скрипт:

- скачивает свежий код с GitHub в `/opt/TGWB_src`;
- сохраняет и возвращает `state.json` (аккаунты пользователей);
- сохраняет `.env`;
- обновляет `venv` и перезапускает сервис.

Проверка версии: отправьте боту `/version`.

Для приватного репозитория положите токен в файл:

```bash
echo "ghp_..." | sudo tee /etc/barcode-bot-token
sudo chmod 600 /etc/barcode-bot-token
sudo ./reinstall.sh
```

Альтернатива без GitHub — скопировать файлы со своего компьютера:

```powershell
scp bot.py config.py state.py sheet.py README.md root@АДРЕС_СЕРВЕРА:/opt/tg_barcode_bot/
```

затем на сервере:

```bash
sudo systemctl restart barcode-bot
```

---

## 9. Бэкап и восстановление

```bash
sudo mkdir -p /root/tgwb-backup
sudo cp /opt/tg_barcode_bot/state.json /root/tgwb-backup/state-$(date +%F).json
sudo cp /opt/tg_barcode_bot/.env      /root/tgwb-backup/env-$(date +%F)
```

Автоматически раз в день (cron):

```bash
sudo crontab -e
```

```
0 3 * * * cp /opt/tg_barcode_bot/state.json /root/tgwb-backup/state-$(date +\%F).json
```

Восстановление:

```bash
sudo systemctl stop barcode-bot
sudo cp /root/tgwb-backup/state-2026-11-21.json /opt/tg_barcode_bot/state.json
sudo systemctl start barcode-bot
```

---

## 10. Устранение неполадок

| Симптом | Причина и решение |
|---------|-------------------|
| `BOT_TOKEN не задан` в логе | Заполните `BOT_TOKEN` в `/opt/tg_barcode_bot/.env`, затем `systemctl restart barcode-bot` |
| `401 Unauthorized` в логе | Токен отозван — получите новый у @BotFather (`/revoke`) и обновите `.env` |
| Бот не отвечает | Проверьте `systemctl status`, интернет и нет ли второго процесса: `pkill -f bot.py`, затем перезапуск |
| `getUpdates conflict` | Запущена вторая копия бота — оставьте только systemd-сервис |
| «Google вернул статус 403/404» | Таблица не открыта по ссылке — включите «Все, у кого есть ссылка — просмотрщик» |
| Новые ШК не приходят | Проверьте: подписка `🔔`, пустая колонка `Статус`, ваш ID в списке, `POLL_INTERVAL` |
| Пришли старые ШК заново | Потерян `state.json` — восстановите из бэкапа |
| Всё смешалось после обновления | Старый `state.json` v1 конвертируется автоматически; проверьте `/status` у каждого пользователя |

---

## 11. Удаление

```bash
sudo systemctl disable --now barcode-bot
sudo rm -f /etc/systemd/system/barcode-bot.service
sudo systemctl daemon-reload
sudo rm -rf /opt/tg_barcode_bot /opt/TGWB_src /etc/barcode-bot-token
```

---

## 12. Безопасность

- Храните `.env` и `state.json` вне публичного доступа; они добавлены в `.gitignore`.
- Ограничьте доступ через `ALLOWED_USER_IDS` и `/access`.
- После публикации токенов в чате/репозитории отзовите их:
  Telegram — `/revoke` у [@BotFather](https://t.me/BotFather), GitHub — Settings → Developer settings.
- Регулярно обновляйте систему: `sudo apt update && sudo apt upgrade -y`.
- Делайте бэкапы `state.json` — там все аккаунты пользователей.

---

<div align="center">

[⬅️ Вернуться на главную](README.md)

</div>
