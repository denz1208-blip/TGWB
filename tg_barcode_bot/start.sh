#!/usr/bin/env bash
# Простой запуск бота + watchdog на серверах без systemd
set -u
cd "$(dirname "$0")" || exit 1

# останавливаем старые процессы
pkill -f "python.*bot\.py" 2>/dev/null
pkill -f "watchdog\.sh" 2>/dev/null
sleep 1

nohup ./watchdog.sh >> watchdog.log 2>&1 &
echo "Watchdog запущен (pid $!). Бот стартует в течение ~5 секунд."
echo "Логи бота:    tail -f $(pwd)/bot.log"
echo "Логи watchdog: tail -f $(pwd)/watchdog.log"
echo "Остановка:     pkill -f 'watchdog\.sh' && pkill -f 'python.*bot\.py'"

# прописываем автозапуск при входе в shell, если cron/systemd нет
if ! grep -q "barcode-bot-autostart" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc <<'EOF'

# barcode-bot-autostart: автостарт бота при входе в shell
if [ -x /workspace/tg_barcode_bot/watchdog.sh ] && ! pgrep -f "watchdog\.sh" >/dev/null 2>&1; then
    nohup /workspace/tg_barcode_bot/watchdog.sh >> /workspace/tg_barcode_bot/watchdog.log 2>&1 &
fi
EOF
    echo "(в ~/.bashrc добавлен автозапуск watchdog при следующем входе в shell)"
fi
