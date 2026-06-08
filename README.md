# Project Camelot

A distributed home compute system controlled entirely through Telegram. Send a message from your phone, execute a script on a GPU machine halfway across the house, get the output back — all over an encrypted mesh network.

Built on two repurposed consumer machines with no cloud dependency.

---

## What it does

- Execute Python scripts remotely on a GPU machine via Telegram
- Browse and navigate the remote filesystem from your phone
- Monitor system health on a low-power e-ink display
- Queue and confirm jobs with a two-step dispatch flow
- Archive job history automatically to a NAS partition
- Alert you if the system goes silent for too long

---

## Architecture

Two nodes connected over a Tailscale mesh VPN:

**Node 1 — Lenovo G460 (Debian 12, 4GB RAM)**
Always-on server. Runs the Telegram bot, PostgreSQL database, Samba file share, and e-ink HUD server. This is the brain — it receives commands and orchestrates everything else.

**Node 2 — Asus TUF F15 (Windows 11, RTX 4060)**
GPU compute node. Receives jobs via SSH, executes Python scripts, streams output back. Hosts Ollama for local LLM inference.

**Storage — 1TB external HDD**
Partitioned into three: 128GB Linux root for Node 1, 200GB NAS shared over Samba, 600GB Windows storage for Node 2.

```
Your Phone (Telegram)
        |
        v
   Bedivere (Bot)
        |
   Camelot (DB)
        |
        +---> Gawain (SSH) ---> Lancelot (GPU)
        |
   Fleet HUD (HTTP) ---> Kindle (e-ink display)
```

---

## Components

### Bedivere — Telegram Bot
The command interface. Accepts commands from an authorized Telegram user, logs everything to the database, and dispatches jobs to the execution engine.

Commands: `/start`, `/ping`, `/status`, `/ls`, `/cd`, `/mkdir`, `/run`, `/confirm`, `/cancel`

Security: user whitelist, script whitelist, queue limit of 3 concurrent jobs, two-step confirmation for script execution, dead man's switch that alerts if the system is silent for 6+ hours.

### Camelot — PostgreSQL Database
Stores job history, execution queue, system logs, and ML checkpoints. Uses JSONB columns for flexible document-style payloads without a separate NoSQL service.

Retention policy: records untouched for 14 days are summarized and archived as weekly JSON files to the NAS partition. Hot data stays in the DB; cold data is compressed and cleared.

### Gawain — SSH Execution Engine
Connects to the GPU node over Tailscale via SSH and executes whitelisted Python scripts. Streams stdout and stderr back to Bedivere, which relays them to Telegram.

### Fleet HUD — System Dashboard
A Python script reads live metrics via psutil, queries the database for recent activity, and regenerates a single HTML file every 30 seconds. A minimal HTTP server serves it on the local network. Designed for an e-ink Kindle browser — high contrast, no animations, meta-refresh only.

Displays: CPU usage, RAM, disk, temperature, uptime, network traffic, service liveness, recent command log.

---

## Stack

| Component | Technology |
|-----------|-----------|
| OS (Node 1) | Debian 12 |
| OS (Node 2) | Windows 11 |
| Database | PostgreSQL 15 + JSONB |
| Bot framework | python-telegram-bot 22 |
| SSH execution | Paramiko |
| VPN mesh | Tailscale |
| Metrics | psutil |
| File sharing | Samba |
| LLM inference | Ollama (qwen3:8b, phi3:mini) |
| Archival | anacron + custom Python |

---

## Why not MongoDB, TinyDB, or SQLite?

MongoDB requires AVX instruction support, which the Lenovo G460's i5 M460 does not have. TinyDB is not suitable for concurrent access from a long-running service. SQLite lacks the JSONB flexibility needed for variable job payloads.

PostgreSQL with JSONB gives relational integrity for structured data (jobs, queue, logs) and document flexibility for payload columns — without running a separate NoSQL service on a RAM-constrained machine.

---

## Setup

### Prerequisites

Node 1 (Linux):
- Debian 12
- Python 3.11+
- PostgreSQL 15
- Tailscale
- Samba

Node 2 (Windows):
- Python 3.12
- OpenSSH Server (Windows optional feature)
- Tailscale
- Ollama

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/camelot.git
cd camelot

# Install dependencies
pip install python-telegram-bot psycopg2-binary paramiko psutil

# Copy config template and fill in your values
cp config.example.py config.py
nano config.py
```

### Database setup

```sql
CREATE USER artoria WITH PASSWORD 'yourpassword';
CREATE DATABASE camelot OWNER artoria;
\c camelot
CREATE TABLE jobs (id SERIAL PRIMARY KEY, created_at TIMESTAMP DEFAULT NOW(), status VARCHAR(20) DEFAULT 'queued', node VARCHAR(20), script_name TEXT, payload JSONB, result JSONB, error TEXT, last_accessed TIMESTAMP DEFAULT NOW());
CREATE TABLE queue (id SERIAL PRIMARY KEY, job_id INTEGER REFERENCES jobs(id), priority INTEGER DEFAULT 0, queued_at TIMESTAMP DEFAULT NOW());
CREATE TABLE logs (id SERIAL PRIMARY KEY, ts TIMESTAMP DEFAULT NOW(), level VARCHAR(10), source VARCHAR(30), message TEXT, meta JSONB, last_accessed TIMESTAMP DEFAULT NOW());
CREATE TABLE checkpoints (id SERIAL PRIMARY KEY, job_id INTEGER REFERENCES jobs(id), created_at TIMESTAMP DEFAULT NOW(), label TEXT, state JSONB, last_accessed TIMESTAMP DEFAULT NOW());
```

### Running Bedivere

```bash
# Run manually
python3 bedivere.py

# Or install as a systemd service
sudo cp bedivere.service /etc/systemd/system/
sudo systemctl enable bedivere
sudo systemctl start bedivere
```

---

## Configuration

Copy `config.example.py` to `config.py` and fill in:

```python
BOT_TOKEN = ""           # From @BotFather on Telegram
DB_PASSWORD = ""         # PostgreSQL password
LANCELOT_IP = ""         # Tailscale IP of GPU node
AUTHORIZED_USERS = []    # Your Telegram user ID (from @userinfobot)
WHITELIST = []           # Absolute paths of scripts allowed to run
```

`config.py` is gitignored. Never commit it.

---

## A note on the naming

Every component in this project is named after a character from Arthurian legend, specifically as interpreted in the visual novel Fate/Stay Night.

This is not decoration. The names were chosen to make the architecture memorable and to give each component a clear identity:

- **Artoria** — the always-on server, named after Artoria Pendragon (Saber). The foundation that holds everything together.
- **Lancelot** — the GPU compute node. The most powerful knight, called upon for heavy work.
- **Bedivere** — the Telegram bot. In legend, Bedivere was the loyal messenger and last knight standing — the one who carried out Arthur's final command. Here, he relays every order from the Fleet Admiral to the fleet.
- **Gawain** — the SSH execution engine. The knight who rides out and does the actual work on Lancelot's machine.
- **Camelot** — the PostgreSQL database. The castle — the central place where all records, history, and state are kept.
- **Merlin** — planned LLM inference orchestration layer, not yet implemented.

If you see a reference to "Fleet Admiral" in the code or logs, that is the human operator — you.

---

## Project status

Core infrastructure is complete and running. Planned next steps:

- LLM inference via Ollama REST API (replacing the current SSH-based approach)
- RuralMedVision — medical imaging classification on HAM10000 as the first real workload
- GitHub Actions for lint/test on push
- WSL setup on Lancelot for Linux tooling

---

## License

MIT
