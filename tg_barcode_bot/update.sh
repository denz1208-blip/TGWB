#!/usr/bin/env bash
# Обновление бота из GitHub + перезапуск (для серверов без systemd)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$DIR")"   # репозиторий TGWB лежит на уровень выше

cd "$REPO_DIR"
echo "1) Скачиваю обновления из GitHub..."
git pull --ff-only origin main || git pull

# если .env в репозитории отсутствует — создаём из example
if [ ! -f "$DIR/.env" ] && [ -f "$DIR/.env.example" ]; then
    cp "$DIR/.env.example" "$DIR/.env"
    echo "!! Создан $DIR/.env из примера — заполните BOT_TOKEN и ссылку на таблицу!"
fi

echo "2) Проверяю зависимости..."
if [ ! -x "$DIR/venv/bin/python" ]; then
    python3 -m venv "$DIR/venv"
fi
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"

echo "3) Перезапускаю бота..."
pkill -f "watchdog\.sh" 2>/dev/null || true
pkill -f "python.*bot\.py" 2>/dev/null || true
sleep 1
"$DIR/start.sh"

echo "Готово. Логи: tail -f $DIR/bot.log"
