#!/usr/bin/env bash
# Watchdog: следит, чтобы бот всегда был запущен (для систем без systemd)
# Запуск: nohup ./watchdog.sh > watchdog.log 2>&1 &

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$PROJECT_DIR/venv/bin/python"
BOT="$PROJECT_DIR/bot.py"
LOG="$PROJECT_DIR/bot.log"
CHECK_INTERVAL=30

is_running() {
    pgrep -f "python.*bot\.py" >/dev/null 2>&1
}

echo "$(date '+%F %T') watchdog запущен (pid $$), слежу за $BOT"
while true; do
    if ! is_running; then
        echo "$(date '+%F %T') бот не найден — запускаю..."
        cd "$PROJECT_DIR" || exit 1
        setsid "$PYTHON" "$BOT" >> "$LOG" 2>&1 < /dev/null &
        sleep 5
        if is_running; then
            echo "$(date '+%F %T') бот запущен успешно"
        else
            echo "$(date '+%F %T') ОШИБКА: бот не запустился, см. $LOG"
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
