[中文](README.md) ｜ English

<div align="center">

<img src="assets/nmail-logo-160.png" width="80" alt="Nmail logo">

# Nmail

**An AI butler for your chaotic inbox — living on your own computer.**

Every account gathered into one inbox; AI sorts, archives, pre-drafts replies, and reports daily.<br>
You read, you edit, you decide — and **not a byte of your data ever leaves your machine**.

[![Release](https://img.shields.io/github/v/release/nathanpenny520/Nmail)](../../releases)
[![PyPI](https://img.shields.io/pypi/v/nmail-app)](https://pypi.org/project/nmail-app/)
[![License](https://img.shields.io/github/license/nathanpenny520/Nmail)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows_%7C_macOS_%7C_Linux-lightgrey)

<img src="assets/Nmail-demo.gif" alt="Nmail demo: multi-account inbox, AI butler executing tasks, approvals and organizing" width="880">

**AI does the chores; every send and every action still goes through you.**

</div>

---

## ✨ What it does for you

- 🤖 **An AI butler that actually works** — say "archive last week's marketing mail, then reply to Zhang for Thursday"; it searches, organizes, drafts and sends end to end. Unsure? It asks first. Writes go through approval cards, everything is logged and undoable.
- ✍️ **Drafts first — the send button is yours** — mail that needs a reply gets pre-drafted into a review queue; you tweak two words, give a nod, and only then it goes. AI wraps up automatically after you approve or reject.
- 📊 **A clear account, every day** — a daily digest at a fixed time: how many arrived, what matters, who is waiting for you. The butler sweeps the box on schedule, summarizes and pre-drafts replies; read the full text right from the notification.
- 📥 **All mailboxes, one inbox** — Gmail / Outlook / QQ / 163 and 20+ presets: type an address and you're in. Cross-account smart views, explorer-style folder management, and archiving that really moves mail on the server.
- 🔒 **Local-first, private by design** — the service binds to `127.0.0.1` only; mail, contacts and keys never touch a cloud, there is no account system and no telemetry. AI uses your own OpenAI-compatible key — point it at Ollama / LM Studio for 100% local inference.
- 🔌 **Open, automatable** — a local REST API plus the `nmail-cli` CLI: hook up iOS Shortcuts, Raycast, n8n; or install the whole mail skill into agents like Claude Code with one `npx skills add`.

## 👀 See it in action

<img src="assets/promo/nmail-demo-inbox.png" alt="Nmail main view: multi-account unified inbox with AI labels, folder tree, three-pane layout" width="880">

| AI butler | Daily digest |
|---|---|
| <img src="assets/promo/nmail-demo-assistant.png" alt="AI butler chat: one-sentence tasks, multi-step execution, approval before writes" width="430"> | <img src="assets/promo/nmail-demo-digest.png" alt="Daily digest: stat cards, 7-day chart, category breakdown, pending replies" width="430"> |
| It reports as it works; writes need your approval | Charts + AI summary — a whole day of mail at a glance |

## 🚀 Up and running in a minute

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (once — reopen your terminal afterwards):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

Then launch:

```bash
uvx --from nmail-app nmail
```

Your browser opens `http://127.0.0.1:8720`. This command **is the launcher** — run it every time (the package is cached; launches are near-instant from the second run). Upgrade with `uvx --refresh --from nmail-app nmail`.

**First-time setup (~5 minutes)**

1. **Add a mailbox**: Settings → Add account; the address alone matches your provider's servers. Gmail / Outlook authorize with one click via built-in public OAuth credentials; password-based accounts use an app-specific password.
2. **Configure AI**: Settings → AI configuration; add any OpenAI-compatible endpoint (Base URL + API key + model — DeepSeek, OpenRouter, local Ollama all work) and click "Test connection".

> Prefer a plain executable? Standalone binaries (Windows / macOS / Linux), winget, Homebrew, pip and running from source are all documented in **[docs/INSTALL.md](docs/INSTALL.md)**.

## 📚 Documentation

| Document | Contents |
|---|---|
| [Install & update](docs/INSTALL.md) | All install methods, first run, in-app updates, data location & backup, uninstall |
| [User guide](docs/%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md) (Chinese) | Tour, shortcuts, folders & archive, AI butler, compose & drafts, daily digest |
| [FAQ](docs/FAQ.md) (Chinese) | Install, network/proxy, app passwords, AI, sync |
| [Privacy & security](docs/%E9%9A%90%E7%A7%81%E4%B8%8E%E5%AE%89%E5%85%A8.md) (Chinese) | Where data lives, what leaves the machine, network & AI safety design |
| [OAuth2 guide](docs/OAuth2%20%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md) (Chinese) | Gmail / Outlook authorization: built-in credentials or your own OAuth app |
| [Agent integration](docs/Agent%E6%8E%A5%E5%85%A5%E6%8C%87%E5%8D%97.md) (Chinese) | Hand Nmail to Claude Code & co: one-click skill, `nmail-cli`, safety boundaries |
| [External API guide](docs/%E5%AF%B9%E5%A4%96API%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md) (Chinese) | Local API & `nmail-cli`: iOS Shortcuts, Raycast, n8n, tunnels |
| [Architecture](docs/ARCHITECTURE.md) | Modules, data model, sync pipeline, security model (developer) |
| [Changelog](docs/CHANGELOG.md) | Commit-level change log |

All docs also live in [docs/](docs/) and are mirrored on the website: <https://nmail.whizzzest.com/docs/>. The app UI and all docs are currently Chinese-only; English versions are planned.

## 🔒 Privacy, by design

- The mail store, index and secrets live in a local data directory ([location & backup](docs/INSTALL.md#数据位置备份与卸载)); upgrades and reinstalls never touch it.
- Exactly two explicit outbound calls: the AI endpoint you configure (mail body snippets; zero outbound when pointed at local Ollama) and an anonymous 24-hour update check (version number only, can be disabled).
- The server binds to `127.0.0.1` only, with no option to listen externally; HTML mail renders in a sanitized sandbox iframe and remote images are blocked by default to defeat tracking pixels.
- Full text: **[docs/隐私与安全.md](docs/%E9%9A%90%E7%A7%81%E4%B8%8E%E5%AE%89%E5%85%A8.md)** (Chinese).

## 🛠 Tech stack & development

Python 3.11+ · FastAPI · SQLite (WAL + FTS5) · APScheduler ｜ React 18 · Vite · TypeScript · Tailwind CSS · Tiptap · ECharts

<details>
<summary>Run from source (developers)</summary>

```bash
python -m venv .venv
pip install -r backend/requirements.txt       # Windows: .venv\Scripts\pip; macOS/Linux: source .venv/bin/activate first
cd frontend && npm install && npm run build && cd ..
python run.py                                 # start (opens your browser)
```

Backend hot reload, frontend dev server, packaging & release (`scripts/release.sh`): see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/RELEASE.md](docs/RELEASE.md).

</details>

## License

[MIT](LICENSE)
