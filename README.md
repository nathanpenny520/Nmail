# Nmail

English ｜ [中文](README.zh-CN.md)

An AI-powered local email client that brings all your accounts together · local-first · private by design · MIT open source.

<p align="center">
  <img src="assets/Nmail-demo.gif" alt="Nmail demo" width="760">
</p>

You read, write, and make the calls; AI sorts your mail, filters the noise, pre-drafts replies, and reports to you daily. All data stays on your machine, and AI uses your own OpenAI-compatible API key (point it at Ollama / LM Studio for 100% local inference). Mail flows over standard IMAP/SMTP — Nmail runs no mail service of its own. Gmail and Outlook no longer accept plain passwords, so Nmail ships built-in public credentials for one-click OAuth2 authorization (you can also register your own OAuth app — see [docs/OAuth2 使用指南.md](docs/OAuth2%20使用指南.md)).

> **Install, first run & updates: [docs/INSTALL.md](docs/INSTALL.md)**. More docs (user guide, FAQ, external API, privacy & security) live in [docs/](docs/), mirrored on the website at <https://nmail.whizzzest.com/docs/>. Current release: **v0.4.x** (see [docs/CHANGELOG.md](docs/CHANGELOG.md)). The app UI and all docs are currently Chinese-only; English versions are planned.

## Quick start

**① Single-file executable (zero dependencies — download and run)**

Download the file for your platform from [Releases](../../releases) and double-click; your browser opens automatically: Windows `nmail-windows-x64.exe` ｜ macOS (Apple Silicon) `nmail-macos-arm64` ｜ Linux `nmail-linux-x64`. Windows can also install via winget (once the manifest review is approved): `winget install nathanpenny520.Nmail`; macOS (Apple Silicon) via Homebrew (always use the fully qualified name — Homebrew core has an unrelated same-name formula): `brew tap nathanpenny520/nmail https://github.com/nathanpenny520/homebrew-nmail && brew trust nathanpenny520/nmail && brew install nathanpenny520/nmail/nmail`.

- Windows may show a SmartScreen prompt (unsigned build): click "More info → Run anyway"
- macOS: right-click → Open on first run (not notarized); Linux: `chmod +x nmail-linux-x64`, then run it

**② One command (PyPI + uv — recommended for daily use)**

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uvx --from nmail-app nmail
```

This command *is* the launcher — you run it every time you open Nmail: re-run it to start again (the package is cached; launches are near-instant from the second run), and upgrade with `uvx --refresh --from nmail-app nmail`. Alternatively, install it permanently with `uv tool install nmail-app` (then just type `nmail` anywhere; upgrade with `uv tool upgrade nmail-app`) or use `pip install nmail-app` (the PyPI distribution is named `nmail-app` — `nmail` was already taken by another project; the product and command names are unchanged).

## First-time setup (about 5 minutes)

1. **Add a mailbox**: Settings → Add account; the address alone matches your provider's servers (password-based accounts use an app-specific password; Gmail/Outlook use one-click OAuth via "Authorize login").
2. **Configure AI**: Settings → AI configuration; add a profile (Base URL + API key + model name; save multiple profiles and switch anytime), then click "Test connection".

Then open http://127.0.0.1:8720 (the port falls back to the next one automatically — check the console output). Details in [docs/INSTALL.md](docs/INSTALL.md).

## Updates

- **In-app check** (on by default; disable under Settings → General): an anonymous version comparison against GitHub every 24 hours (only the version number is sent — no local data leaves your machine); new releases appear in the notification center, and you can also check manually from the settings page.
- **Upgrade per channel**: uvx `uvx --refresh --from nmail-app nmail` ｜ resident install `uv tool upgrade nmail-app` ｜ pip `pip install -U nmail-app` ｜ Windows `winget upgrade nathanpenny520.Nmail` ｜ macOS `brew upgrade nathanpenny520/nmail/nmail` ｜ single-file: download the new build and replace the old one.
- **Upgrades never touch your data**: the mail store / secrets / settings live in a separate data directory, and the first launch of a new version runs database migrations automatically.

## Development

Requires Python 3.11+ and Node.js 18+.

```bash
# Run from source
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r backend/requirements.txt
# macOS / Linux:
# source .venv/bin/activate && pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
python run.py                    # start (opens your browser automatically)

# Backend hot reload (Windows; macOS/Linux use .venv/bin/python, or activate the venv and run `python`)
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8720

# Frontend dev server (/api is proxied to 8720)
cd frontend && npm run dev       # http://localhost:5173
```

Packaging & release in one command: `bash scripts/release.sh <version>` (full manual: [docs/RELEASE.md](docs/RELEASE.md)).

## Data & privacy

- The data directory follows each platform's standard location (Windows: `%LOCALAPPDATA%\Nmail` ｜ macOS: `~/Library/Application Support/Nmail` ｜ Linux: `~/.local/share/Nmail`), override with the `NMAIL_DATA_DIR` environment variable; `nmail.db` holds the mail store and full-text index (SQLite, WAL + FTS5), and `secrets.json` stores the AI API keys and mailbox passwords / OAuth tokens.
- The server binds to `127.0.0.1` only, with no option to listen externally; secrets live only in the local `secrets.json`, and the settings UI shows exactly what's stored (masked by default). When a cloud AI endpoint is configured, email bodies are sent to that endpoint; point it at a local endpoint (Ollama etc.) and nothing leaves your machine. More in [docs/隐私与安全.md](docs/隐私与安全.md).

## Tech stack

Python 3.11+ · FastAPI · SQLite (WAL + FTS5) · APScheduler ｜ React 18 · Vite · TypeScript · Tailwind CSS · Tiptap (compose editor) · ECharts (digest visualizations)

## License

[MIT](LICENSE)
