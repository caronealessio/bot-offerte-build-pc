# Esegue il bot una volta e salva il log in logs\ (usato dall'Utilità di pianificazione).
# Uso manuale:  powershell -ExecutionPolicy Bypass -File esegui-bot.ps1 [--dry-run]
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ("bot_{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

# senza token il bot segnerebbe gli annunci come "visti" senza inviarli: meglio non partire
if ($args -notcontains '--dry-run' -and -not $env:TELEGRAM_TOKEN -and
    -not (Select-String -Path (Join-Path $root '.env') -Pattern '^TELEGRAM_TOKEN=.+' -Quiet -ErrorAction SilentlyContinue)) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') STOP: manca TELEGRAM_TOKEN nel file .env" | Out-File $log -Append -Encoding utf8
    exit 1
}

$env:PYTHONIOENCODING = 'utf-8'
Set-Location (Join-Path $root 'bot-annunci-pc')
"===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" | Out-File $log -Append -Encoding utf8
& $py -m bot.main @args 2>&1 | ForEach-Object { "$_" } | Out-File $log -Append -Encoding utf8
"exit $LASTEXITCODE" | Out-File $log -Append -Encoding utf8

# conserva solo gli ultimi 14 giorni di log
Get-ChildItem $logs -Filter 'bot_*.log' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Force
