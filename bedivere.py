import logging
import psycopg2
import psycopg2.extras
import threading
import time
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import BOT_TOKEN, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, AUTHORIZED_USERS, MAX_QUEUE
from gawain import ssh_exec

DB = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST
)

logging.basicConfig(level=logging.INFO)

pending = {}
cwd = {}  # current working directory per user — {user_id: path}
DEFAULT_DIR = "C:/Users/asmit/Desktop"

DEAD_MAN_HOURS = 6
DEAD_MAN_CHECK_INTERVAL = 3600

def log_command(source, message, meta=None):
    with DB.cursor() as cur:
        cur.execute(
            "INSERT INTO logs (level, source, message, meta, last_accessed) VALUES (%s, %s, %s, %s, NOW()) RETURNING id",
            ("INFO", source, message, psycopg2.extras.Json(meta) if meta else None)
        )
        log_id = cur.fetchone()[0]
        cur.execute("UPDATE logs SET last_accessed = NOW() WHERE id = %s", (log_id,))
    DB.commit()

def touch(table, record_id):
    with DB.cursor() as cur:
        cur.execute(f"UPDATE {table} SET last_accessed = NOW() WHERE id = %s", (record_id,))
    DB.commit()

def dead_man_switch():
    bot = Bot(token=BOT_TOKEN)
    while True:
        time.sleep(DEAD_MAN_CHECK_INTERVAL)
        try:
            with DB.cursor() as cur:
                cur.execute("SELECT MAX(ts) FROM logs")
                last_log = cur.fetchone()[0]
            if last_log is None or datetime.now() - last_log > timedelta(hours=DEAD_MAN_HOURS):
                for user_id in AUTHORIZED_USERS:
                    import asyncio
                    asyncio.run(bot.send_message(
                        chat_id=user_id,
                        text=f" Dead man's switch triggered. Artoria has been silent for over {DEAD_MAN_HOURS} hours."
                    ))
        except Exception as e:
            logging.error(f"Dead man's switch error: {e}")

async def check_auth(update: Update) -> bool:
    if update.effective_user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("Unauthorized. This incident will be logged.")
        log_command("bedivere", "UNAUTHORIZED ACCESS ATTEMPT", {"user": update.effective_user.username, "id": update.effective_user.id})
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    log_command("bedivere", "/start", {"user": update.effective_user.username})
    await update.message.reply_text("Bedivere online. Awaiting orders, Fleet Admiral.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    log_command("bedivere", "/status", {"user": update.effective_user.username})
    with DB.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'")
        queued = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM jobs WHERE status='done'")
        done = cur.fetchone()[0]
    msg = f"Artoria: online\nCamelot DB: online\nLancelot: online\nQueued jobs: {queued}\nCompleted jobs: {done}"
    await update.message.reply_text(msg)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    log_command("bedivere", "/ping", {"user": update.effective_user.username})
    await update.message.reply_text("Pong.")

async def ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    user_id = update.effective_user.id
    path = context.args[0] if context.args else cwd.get(user_id, DEFAULT_DIR)
    log_command("bedivere", "/ls", {"user": update.effective_user.username, "path": path})
    out, err = ssh_exec(f'dir /b "{path}"')
    if err and not out:
        await update.message.reply_text(f"Error:\n{err}")
        return
    await update.message.reply_text(f" {path}\n\n{out if out else '(empty)'}")

async def cd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(f"Current dir: {cwd.get(user_id, DEFAULT_DIR)}")
        return
    new_path = context.args[0]
    log_command("bedivere", "/cd", {"user": update.effective_user.username, "path": new_path})
    out, err = ssh_exec(f'dir /b "{new_path}"')
    if err and not out:
        await update.message.reply_text(f"Invalid path:\n{err}")
        return
    cwd[user_id] = new_path
    await update.message.reply_text(f"Changed to: {new_path}")

async def mkdir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /mkdir <folder_name>")
        return
    base = cwd.get(user_id, DEFAULT_DIR)
    folder = context.args[0]
    full_path = f"{base}/{folder}"
    log_command("bedivere", "/mkdir", {"user": update.effective_user.username, "path": full_path})
    out, err = ssh_exec(f'mkdir "{full_path}"')
    if err:
        await update.message.reply_text(f"Error:\n{err}")
        return
    await update.message.reply_text(f"Created: {full_path}")

async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    log_command("bedivere", "/run", {"user": update.effective_user.username, "args": context.args})
    if not context.args:
        await update.message.reply_text("Usage: /run <script_path>")
        return
    with DB.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs WHERE status='queued' OR status='running'")
        active = cur.fetchone()[0]
    if active >= MAX_QUEUE:
        await update.message.reply_text(f"Queue full. Max {MAX_QUEUE} active jobs.")
        return
    script_path = context.args[0]
    pending[update.effective_user.id] = script_path
    await update.message.reply_text(
        f"Confirm dispatch of:\n`{script_path}`\n\nSend /confirm to proceed or /cancel to abort.",
        parse_mode="Markdown"
    )

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    user_id = update.effective_user.id
    if user_id not in pending:
        await update.message.reply_text("No pending dispatch to confirm.")
        return
    script_path = pending.pop(user_id)
    log_command("bedivere", "/confirm", {"user": update.effective_user.username, "script": script_path})
    await update.message.reply_text(f"Dispatching {script_path} to Lancelot...")
    out, err = run_on_lancelot(script_path)
    if err:
        await update.message.reply_text(f"Errors:\n{err}")
    await update.message.reply_text(f"Output:\n{out}" if out else "No output.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    user_id = update.effective_user.id
    if user_id not in pending:
        await update.message.reply_text("No pending dispatch to cancel.")
        return
    script_path = pending.pop(user_id)
    log_command("bedivere", "/cancel", {"user": update.effective_user.username, "script": script_path})
    await update.message.reply_text(f"Dispatch of {script_path} cancelled.")


dms_thread = threading.Thread(target=dead_man_switch, daemon=True)
dms_thread.start()

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("ls", ls))
app.add_handler(CommandHandler("cd", cd))
app.add_handler(CommandHandler("mkdir", mkdir))
app.add_handler(CommandHandler("run", run))
app.add_handler(CommandHandler("confirm", confirm))
app.add_handler(CommandHandler("cancel", cancel))

print("Bedivere is listening...")
app.run_polling()
