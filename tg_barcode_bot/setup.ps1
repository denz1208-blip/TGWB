param(
    [string]$TokenArg = '',
    [string]$SheetArg = ''
)

$ErrorActionPreference = 'Stop'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $dir '.env'

Write-Host '=== Настройка токена Telegram-бота ===' -ForegroundColor Cyan
Write-Host 'Токен можно получить у @BotFather командой /newbot'
if ($TokenArg) { $token = $TokenArg.Trim() } else { $token = (Read-Host 'Вставьте токен').Trim() }

if ($token -notmatch '^\d+:[A-Za-z0-9_-]+$') {
    Write-Host '❌ Это не похоже на токен бота. Ожидается вид: 123456789:AA...' -ForegroundColor Red
    exit 1
}

if ($SheetArg) { $sheet = $SheetArg.Trim() } else { $sheet = (Read-Host 'Ссылка на таблицу (Enter — оставить как есть)').Trim() }

$lines = @()
if (Test-Path $envPath) { $lines = @(Get-Content $envPath) }

function Set-EnvValue([string]$key, [string]$value, [string[]]$source) {
    $result = @()
    $done = $false
    foreach ($line in $source) {
        if ($line -like "$key=*") {
            if (-not $done) { $result += "$key=$value"; $done = $true }
        } else {
            $result += $line
        }
    }
    if (-not $done) { $result += "$key=$value" }
    return $result
}

$lines = Set-EnvValue 'BOT_TOKEN' $token $lines
if ($sheet -match '^https?://' -and $sheet -like '*/spreadsheets/d/*') {
    $lines = Set-EnvValue 'GOOGLE_SHEET_URL' $sheet $lines
    Write-Host '✅ Ссылка на таблицу сохранена' -ForegroundColor Green
}

[System.IO.File]::WriteAllLines($envPath, [string[]]$lines, [System.Text.UTF8Encoding]::new($false))

Write-Host "✅ Токен сохранён в $envPath" -ForegroundColor Green
Write-Host "   $($token.Substring(0, [Math]::Min(7, $token.Length)))...$($token.Substring([Math]::Max(0, $token.Length - 4)))" -ForegroundColor DarkGray
Write-Host 'Теперь запустите: python bot.py  (или установите на сервер: sudo ./install.sh)'
