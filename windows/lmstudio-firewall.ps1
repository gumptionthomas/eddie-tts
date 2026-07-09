# Toggle LM Studio's internet access via a named outbound firewall rule.
# (Optional companion tool -- handy if you run a local LM Studio LLM alongside this
# TTS server and want to keep it off the internet.)
#
#   .\lmstudio-firewall.ps1 block    # cut LM Studio off from the internet (telemetry/updates/downloads)
#   .\lmstudio-firewall.ps1 allow    # temporarily let it out (e.g. to download a model)
#   .\lmstudio-firewall.ps1 status   # show current state
#
# This only blocks OUTBOUND (app-initiated) connections. It does NOT affect a
# local LLM server on :1234 -- replies to inbound requests and loopback are
# unaffected, so other machines can still reach your models while blocked.
#
# The rule is created on first `block`, then just enabled/disabled thereafter
# (never deleted), so toggling is instant. Self-elevates via UAC as needed.

param(
    [Parameter(Position = 0)]
    [ValidateSet("block", "allow", "status")]
    [string]$Action = "status"
)

$RuleName = "LM Studio - Block Outbound (toggle)"
# Default LM Studio install location; override with $env:LMSTUDIO_EXE if yours differs.
$Exe = if ($env:LMSTUDIO_EXE) { $env:LMSTUDIO_EXE } `
       else { Join-Path $env:LOCALAPPDATA "Programs\LM Studio\LM Studio.exe" }

# --- self-elevate (firewall changes require admin) ---
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin -and $Action -ne "status") {
    Write-Host "Elevating (UAC prompt)..."
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" $Action"
    return
}

$rule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue

switch ($Action) {
    "block" {
        if (-not $rule) {
            if (-not (Test-Path $Exe)) {
                Write-Warning "LM Studio exe not found at: $Exe  (set `$env:LMSTUDIO_EXE to override)"
            }
            New-NetFirewallRule -DisplayName $RuleName -Direction Outbound `
                -Program $Exe -Action Block -Profile Any -Enabled True | Out-Null
            Write-Host "Created + ENABLED block rule. LM Studio is now cut off from the internet."
        } else {
            Enable-NetFirewallRule -DisplayName $RuleName
            Write-Host "ENABLED block rule. LM Studio is now cut off from the internet."
        }
    }
    "allow" {
        if (-not $rule) {
            Write-Host "No block rule exists yet -- LM Studio already has full internet access."
        } else {
            Disable-NetFirewallRule -DisplayName $RuleName
            Write-Host "DISABLED block rule. LM Studio can reach the internet (download your models,"
            Write-Host "then run '.\lmstudio-firewall.ps1 block' again to re-secure it)."
        }
    }
    "status" {
        if (-not $rule) {
            Write-Host "No block rule exists. LM Studio has full internet access (default)."
        } else {
            $state = if ($rule.Enabled -eq "True") { "BLOCKED (no internet)" } else { "ALLOWED (rule disabled)" }
            Write-Host "Rule exists. LM Studio outbound: $state"
        }
    }
}

if ($isAdmin -and $Action -ne "status") {
    Write-Host ""
    Read-Host "Press Enter to close"   # keep the elevated window open so you can read the result
}
