# Nmail

English ｜ [中文](README.zh-CN.md)

An AI-powered local email client that brings all your accounts together · local-first · private by design · MIT open source.

You read, write, and make the calls; AI sorts your mail, filters the noise, pre-drafts replies, and reports to you daily. All data stays on your machine, and AI uses your own OpenAI-compatible API key (point it at Ollama / LM Studio for 100% local inference). Mail flows over standard IMAP/SMTP — Nmail runs no mail service of its own. Gmail and Outlook no longer accept plain passwords, so Nmail ships built-in public credentials for one-click OAuth2 authorization (you can also register your own OAuth app — see [docs/OAuth2 使用指南.md](docs/OAuth2%20使用指南.md)).

> Roadmap: [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md) · v0.4 redesign (current mainline): [docs/REDESIGN_PLAN.md](docs/REDESIGN_PLAN.md). **Install, first run & updates: [docs/INSTALL.md](docs/INSTALL.md)**. More docs (user guide, FAQ, external API, privacy & security) live in [docs/](docs/), mirrored on the website at <https://nmail.whizzzest.com/docs/>. The app UI and all docs are currently Chinese-only; English versions are planned. Status: **v0.4.0 released** — the AI-butler agent overhaul is complete (native tool calling, resumable long tasks, human-aligned toolset, Claude-style progress folding), plus cross-session memory, a daily AI morning brief, wrap-up summaries on budget exhaustion, clarification prompts, built-in workflow skills, and a CLI agent channel (`nmail-cli agent ask`).

## Quick start

Three ways to get started:

**① Single-file executable (zero dependencies — download and run)**

Download the file for your platform from [Releases](../../releases) and double-click; your browser opens automatically: Windows `nmail-windows-x64.exe` ｜ macOS (Apple Silicon) `nmail-macos-arm64` ｜ Linux `nmail-linux-x64`.
Windows can also install via winget (once the manifest review is approved): `winget install nathanpenny520.Nmail`;
macOS (Apple Silicon) via Homebrew: `brew tap nathanpenny520/nmail https://github.com/nathanpenny520/homebrew-nmail && brew install nmail`.

- Windows may show a SmartScreen prompt (unsigned build): click "More info → Run anyway"
- macOS: right-click → Open on first run (not notarized); Linux: `chmod +x nmail-linux-x64`, then run it

**② One command (PyPI + uv — recommended for daily use)**

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uvx --from nmail-app nmail
```

uv prepares the Python runtime for you — no manual Python / Node setup. Alternatively, `pip install nmail-app` and run `nmail` (the PyPI distribution is named `nmail-app` — `nmail` was already taken by another project; the product and command names are unchanged).

**③ From source (development)**

Requires Python 3.11+ and Node.js 18+.

```bash
# 1. Backend dependencies
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r backend/requirements.txt
# macOS / Linux:
# source .venv/bin/activate && pip install -r backend/requirements.txt

# 2. Build the frontend
cd frontend && npm install && npm run build && cd ..

# 3. Start (opens your browser automatically)
python run.py
```

Then open http://127.0.0.1:8720 (if the port is taken, the app falls back to the next one — check the console output). First-time setup takes about 5 minutes: **① Add a mailbox** — Settings → Add account; the address alone matches your provider's servers (password-based accounts use an app-specific password; Gmail/Outlook use one-click OAuth via "Authorize login"). **② Configure AI** — Settings → AI configuration; add a profile (Base URL + API key + model name; save multiple profiles and switch anytime), then click "Test connection". Details in [docs/INSTALL.md](docs/INSTALL.md).

## Building it yourself

```bash
bash scripts/sync_frontend.sh                       # build the frontend and bundle it into the Python package
.venv/Scripts/pip install pyinstaller               # only needed for packaging (macOS/Linux: .venv/bin/)
.venv/Scripts/pyinstaller nmail.spec                # produces the dist/nmail single file (nmail.exe on Windows)
```

Or build just a wheel: `pip wheel . -w dist`. Once published to PyPI, users can run `uvx --from nmail-app nmail`. Pushing a `v*` tag triggers CI (`.github/workflows/release.yml`) to publish the wheel and three-platform binaries — and, with the `HOMEBREW_TAP_TOKEN` secret configured, sync the Homebrew tap automatically.

**Releases are one command**: `bash scripts/release.sh 0.2.0` (bumps the version, tags, watches CI, opens the winget version PR, and triggers a rebuild of the website). Full manual: [docs/RELEASE.md](docs/RELEASE.md).

## Updates

- **In-app check** (on by default; disable under Settings → General): an anonymous version comparison against GitHub every 24 hours; new releases appear in the notification center, and you can also check manually from the settings page. Only the version number is sent — no local data leaves your machine.
- **Upgrading per channel**: Windows `winget upgrade nathanpenny520.Nmail` ｜ macOS `brew upgrade nmail` ｜ PyPI `uv tool upgrade nmail-app` or `pip install -U nmail-app` ｜ single-file: download the new build and replace the old one.
- Upgrading never touches your data: the mail store / secrets / settings live in a separate data directory, and the first launch of a new version runs database migrations automatically.

## Development mode

```bash
# Backend hot reload (Windows; macOS/Linux use .venv/bin/python, or activate the venv and run `python`)
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8720

# Frontend dev server (/api is proxied to 8720)
cd frontend && npm run dev   # http://localhost:5173
```

## Data & privacy

- The data directory follows each platform's standard location (Windows: `%LOCALAPPDATA%\Nmail` ｜ macOS: `~/Library/Application Support/Nmail` ｜ Linux: `~/.local/share/Nmail`); override with the `NMAIL_DATA_DIR` environment variable.
- `nmail.db`: mail store and full-text index (SQLite, WAL + FTS5); `secrets.json`: AI API keys, mailbox passwords / OAuth tokens, and other secrets.
- The server binds to `127.0.0.1` only, with no option to listen externally. AI API keys and mailbox credentials are stored only in the local `secrets.json` — the settings UI shows exactly what's stored (masked by default). When a cloud AI endpoint is configured, email bodies are sent to that endpoint; point it at a local endpoint (Ollama etc.) and nothing leaves your machine. More in [docs/隐私与安全.md](docs/隐私与安全.md).

## Tech stack

Python 3.11+ · FastAPI · SQLite (WAL + FTS5) · APScheduler ｜ React 18 · Vite · TypeScript · Tailwind CSS · Tiptap (compose editor) · ECharts (digest visualizations)

## License

[MIT](LICENSE)
