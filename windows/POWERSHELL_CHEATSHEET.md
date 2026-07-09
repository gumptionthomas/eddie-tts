# PowerShell Cheat Sheet (for Unix people)

A translation guide for anyone comfortable in a Unix shell who now finds
themselves in Windows PowerShell.

**The one mental-model shift that matters:** PowerShell pipes **objects, not
text**. `ls | ...` passes file *objects* with properties (`.Name`, `.Length`,
`.LastWriteTime`), not lines you `grep`/`awk`. Once that clicks, the rest
follows — you filter and select on properties instead of parsing columns.

---

## Command translation

| Unix | PowerShell | Notes |
|---|---|---|
| `ls` | `ls` / `dir` / `Get-ChildItem` | `ls` is an alias |
| `ls -la` | `ls -Force` | `-Force` shows hidden/system |
| `cd -` | `cd -` | works in PS7+ |
| `pwd` | `pwd` / `Get-Location` | |
| `cat file` | `cat file` / `Get-Content` | |
| `head -20` | `Get-Content f -TotalCount 20` | or `... | select -First 20` |
| `tail -20` | `Get-Content f -Tail 20` | |
| `tail -f` | `Get-Content f -Wait -Tail 20` | live follow |
| `grep pat file` | `Select-String pat file` | alias `sls` |
| `grep -r pat` | `sls pat -Path * -Recurse` | prefer ripgrep (`rg`) if installed |
| `find . -name '*.py'` | `Get-ChildItem -Recurse -Filter *.py` | or `ls -r *.py` |
| `cp -r a b` | `Copy-Item a b -Recurse` | alias `cp` |
| `mv a b` | `Move-Item` / `mv` | |
| `rm -rf dir` | `Remove-Item dir -Recurse -Force` | alias `rm` (no `-rf` flag) |
| `mkdir -p a/b` | `mkdir a/b` | `-p` implicit / `New-Item -Force` |
| `touch f` | `New-Item f` | see caveat #5 below |
| `which cmd` | `Get-Command cmd` / `gcm` | `.Source` for the path |
| `env` | `Get-ChildItem Env:` / `ls env:` | |
| `export X=1` | `$env:X = "1"` | session-scoped |
| `X=1 cmd` | `$env:X='1'; cmd` | no inline prefix |
| `ps aux` | `Get-Process` / `ps` | |
| `kill PID` | `Stop-Process -Id PID` | |
| `cmd1 && cmd2` | `cmd1; if ($?) { cmd2 }` | `&&` / `||` only in PS7+ |
| `\` line-continue | `` ` `` (backtick) | ugly; prefer piping instead |
| `curl` | real: `curl.exe` | bare `curl` = `Invoke-WebRequest`! (gotcha #1) |

Aliases worth memorizing: `?` = `Where-Object`, `%` = `ForEach-Object`,
`sls` = `Select-String`, `gm` = `Get-Member`, `gcm` = `Get-Command`.

---

## The gotchas that will actually bite you

**1. `curl` is a lie.** In PowerShell, `curl` and `wget` are *aliases* for
`Invoke-WebRequest` — different syntax, extra latency. To use real curl, call it
explicitly as **`curl.exe`** (Windows ships genuine curl in System32).

**2. Quoting.** Single quotes = literal, double quotes = interpolated
(`"$var"`). To interpolate an expression, wrap it: `"$($obj.Property)"` — bare
`"$obj.Property"` gives the object's `ToString()` then literal `.Property`.

**3. `$?` is a boolean, not an exit code.** For the actual exit code of a native
`.exe`, use `$LASTEXITCODE`. `$?` just means "did the last thing succeed."

**4. Everything is an object — exploit it.** No more `awk '{print $2}'`:
```powershell
Get-Process | Where-Object CPU -gt 10 | Sort-Object CPU -Descending | Select-Object Name, CPU
ls | Where Name -like '*.wav' | Sort Length -Desc | Select -First 5
```
`Where-Object` = filter, `Select-Object` = pick columns/rows,
`ForEach-Object` = xargs / loop body.

**5. `touch` can truncate.** `New-Item file` fails if the file exists;
`New-Item file -Force` *empties* an existing file. Safe touch:
`if (-not (Test-Path f)) { New-Item f }`.

**6. Output redirection encoding.** `... > file.txt` writes **UTF-16** by
default (BOM + null bytes — breaks Unix tools). Use
`... | Out-File f -Encoding utf8` or `Set-Content -Encoding utf8`.

**7. Null device / discard.** `2>/dev/null` → `2>$null`; `/dev/null` → `$null`.

---

## Things that feel nice

- **Tab completion** is excellent — cmdlet names, parameters (`-Rec`→`-Recurse`),
  even enum values.
- **`Get-Help cmd -Examples`** / **`-Full`** — real man pages. Run `Update-Help`
  once first.
- **`cmd | Get-Member`** (`gm`) — introspect any object's properties/methods.
  Your discovery superpower.
- **`Get-Command *process*`** — fuzzy-find commands.
- Cmdlets are **`Verb-Noun`** and case-insensitive. Learn the verbs (`Get`,
  `Set`, `New`, `Remove`, `Start`, `Stop`, `Test`, `Invoke`) and you can guess
  most commands.

---

## For this project (Qwen3-TTS server)

**Run a script** — the `.\` prefix is required (PowerShell won't run scripts
from `.` implicitly). Run these from the repo root:
```powershell
.\windows\start_server.ps1     # start the server (foreground)
.\windows\stop_server.ps1      # kill the port-4123 listener + python main.py
```

**If scripts won't run** ("execution policy" error), either once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
or per-run: `powershell -ExecutionPolicy Bypass -File .\windows\start_server.ps1`

**Test the server** — use `curl.exe` (not the alias). Windows command-line JSON
quoting is painful, so for anything nontrivial put the body in a file:
```powershell
# inline (note the escaped quotes and backtick line-continues)
curl.exe -s -X POST http://localhost:4123/v1/audio/speech `
  -H "Content-Type: application/json" `
  -d '{\"input\":\"hello\",\"voice\":\"Ryan\",\"temperature\":0.3}' `
  --output test.wav

# cleaner: body from a file
curl.exe -s -X POST http://localhost:4123/v1/audio/speech `
  -H "Content-Type: application/json" -d '@body.json' --output test.wav
```

**Voice clone (multipart upload):**
```powershell
curl.exe -s -X POST http://localhost:4123/v1/audio/speech/upload `
  -F "input=Hello from a cloned voice." `
  -F "voice_file=@reference.wav" `
  -F "temperature=0.3" --output clone.wav
```
Note: the clone path takes **all** its style (timbre *and* delivery) from the
reference clip — there is no `instruct` channel. To change the mood, change the
reference clip. Match the reference's emotion/pace to what you want out.

**Voice design (describe a voice in words):**
```powershell
curl.exe -s -X POST http://localhost:4123/v1/audio/speech/design `
  -H "Content-Type: application/json" `
  -d '{\"input\":\"Hello there, welcome in.\",\"voice_description\":\"warm gravelly older man, unhurried\"}' `
  --output design.wav
```
This is the **style/instruction** lever the clone path lacks — the
`voice_description` genuinely steers timbre and delivery (e.g. "bright cheerful
young woman" vs "warm gravelly older man" produce dramatically different voices).
First call after a server restart lazy-loads the model (~a few seconds), then
it's warm.

### Three synthesis endpoints at a glance

| endpoint | picks the voice by | style control |
|---|---|---|
| `/v1/audio/speech` | built-in `voice` (Ryan, Vivian, …) | `instruct` + `temperature` |
| `/v1/audio/speech/upload` | your `voice_file` reference clip | reference clip only (no instruct) |
| `/v1/audio/speech/design` | `voice_description` text | the description itself + `temperature` |

`temperature` (all three) is a **run-to-run variability** knob, *not* an
expressiveness dial: low = steadier/more consistent, high = more varied. Same
voice, same words — it only nudges delivery. Default is 0.65. `seed` (all three)
makes a given run reproducible. For actual "flat vs dramatic" control, use
`instruct` (built-in voices) or `voice_description` (design), not temperature.

**Check what's on port 4123 / who's listening:**
```powershell
netstat -ano | Select-String ':4123'      # PID is the last column
Get-Process -Id <PID>                      # what that PID is
```

**Tail the server output** if you redirect it to a file:
```powershell
Get-Content server.log -Wait -Tail 40
```

**Play a generated WAV** without leaving the shell:
```powershell
(New-Object Media.SoundPlayer "test.wav").PlaySync()
# or just:  start test.wav   (opens the default player)
```

---

## LM Studio (local LLM server)

Runs an OpenAI-compatible server on this machine, LAN-reachable:
- local: `http://localhost:1234/v1`
- LAN:   `http://<your-lan-ip>:1234/v1`   (no API key; pass any dummy if a client insists)

```powershell
curl.exe -s http://localhost:1234/v1/models          # list loaded models
```

**Lock LM Studio's internet access** (blocks telemetry/updates/downloads, but NOT
the LAN server on :1234). Run from the repo root:
```powershell
.\windows\lmstudio-firewall.ps1 block     # arm — cut it off from the internet (one UAC prompt)
.\windows\lmstudio-firewall.ps1 allow     # temporarily let it out to download a model
.\windows\lmstudio-firewall.ps1 block     # ...then re-secure when the download's done
.\windows\lmstudio-firewall.ps1 status    # check state (read-only, no UAC)
```
Only outbound is blocked, so LAN clients keep reaching the models while it's armed.

LM Studio 0.4.x has **no** in-app auto-update toggle and no config lever — but the
block rule *is* the disable: update checks go out through `LM Studio.exe`, which
the rule blocks. The only exposure is while toggled to `allow` for a download, and
a staged update only installs on next restart. To avoid even that, download GGUFs
directly (`hf download ...`, a different exe the rule doesn't touch) into
`%USERPROFILE%\.lmstudio\models\<publisher>\<repo>\` and skip the in-app browser.
