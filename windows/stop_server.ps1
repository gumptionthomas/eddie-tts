# Stops the Qwen3-TTS server: kills whatever is listening on port 4123
# plus any python process running main.py (covers the parent+worker pair).
$port = 4123
$killed = @()
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop; $killed += $_ } catch {} }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'main\.py' } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $killed += $_.ProcessId } catch {} }
if ($killed.Count) { Write-Host "Stopped PID(s): $(( $killed | Sort-Object -Unique ) -join ', ')" }
else { Write-Host "No server was running on port $port." }
