import psutil
import psycopg2
import subprocess
from datetime import datetime
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST

DB = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST
)

HUD_PATH = "/home/artoria/Desktop/camelot/hud.html"

def get_metrics():
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/mnt/nas")
    net = psutil.net_io_counters()
    now = datetime.now()
    boot = datetime.fromtimestamp(psutil.boot_time())
    uptime = now - boot
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(rem, 60)

    try:
        temp_out = subprocess.check_output(["cat", "/sys/class/thermal/thermal_zone0/temp"]).decode().strip()
        temp = int(temp_out) // 1000
    except:
        temp = "N/A"

    with DB.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'")
        queued = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM jobs WHERE status='done'")
        done = cur.fetchone()[0]
        cur.execute("SELECT message, ts FROM logs ORDER BY ts DESC LIMIT 4")
        logs = cur.fetchall()

    def check_service(name):
        try:
            result = subprocess.check_output(["systemctl", "is-active", name]).decode().strip()
            return result == "active"
        except:
            return False

    services = {
        "Telegram Bot": check_service("bedivere"),
        "Samba": check_service("smbd"),
        "HTTP Server": check_service("camelot-hud"),
        "SSH": check_service("ssh"),
    }

    return {
        "cpu": cpu,
        "ram_used": round(ram.used / 1024**3, 1),
        "ram_total": round(ram.total / 1024**3, 1),
        "ram_pct": ram.percent,
        "disk_used": round(disk.used / 1024**3, 1),
        "disk_total": round(disk.total / 1024**3, 1),
        "disk_pct": disk.percent,
        "net_in": round(net.bytes_recv / 1024**2, 1),
        "net_out": round(net.bytes_sent / 1024**2, 1),
        "temp": temp,
        "uptime_days": days,
        "uptime_hours": hours,
        "uptime_mins": minutes,
        "queued": queued,
        "done": done,
        "logs": logs,
        "services": services,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
    }

def generate_hud(m):
    def bar_class(pct):
        if pct >= 85: return "danger"
        if pct >= 65: return "warn"
        return ""

    log_rows = ""
    for msg, ts in m["logs"]:
        log_rows += f"<tr><td class='td-time'>{ts.strftime('%H:%M')}</td><td class='td-msg'>{msg}</td></tr>\n"

    service_rows = ""
    for name, online in m["services"].items():
        dot_class = "" if online else "offline"
        status_class = "online" if online else "offline"
        status_text = "ONLINE" if online else "OFFLINE"
        service_rows += f"<tr><td class='td-svc'>{name}</td><td class='td-status'><div class='status-dot'><div class='dot {dot_class}'></div><span class='status-text {status_class}'>{status_text}</span></div></td></tr>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta http-equiv="refresh" content="30">
<title>CAMELOT HUD</title>
<style>
  :root {{
    --bg: #000000; --text: #ffffff; --border: #ffffff;
    --gray-light: #222222; --gray-dark: #aaaaaa;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: "Amazon Ember", Bookerly, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    padding: 12px; max-width: 600px; margin: 0 auto; line-height: 1.25;
  }}
  .header {{
    border-bottom: 3px double var(--border);
    padding-bottom: 8px; margin-bottom: 10px;
  }}
  .title {{ font-size: 32px; font-weight: 900; letter-spacing: 0.08em; line-height: 1; }}
  
  summary.divider {{
    display: flex; align-items: center; gap: 8px;
    margin: 10px 0 6px 0; font-size: 12px; font-weight: 900;
    text-transform: uppercase; letter-spacing: 0.1em;
    cursor: pointer; list-style: none;
  }}
  summary.divider::-webkit-details-marker {{
    display: none;
  }}
  summary.divider::before, summary.divider::after {{ content: ''; flex: 1; height: 2px; background: var(--border); }}
  
  .divider-static {{
    display: flex; align-items: center; gap: 8px;
    margin: 10px 0 6px 0; font-size: 12px; font-weight: 900;
    text-transform: uppercase; letter-spacing: 0.1em;
  }}
  .divider-static::before, .divider-static::after {{ content: ''; flex: 1; height: 2px; background: var(--border); }}

  .bar-track {{ height: 5px; background: var(--gray-light); border: 1px solid var(--border); margin-top: 5px; }}
  .bar-fill {{ height: 100%; background: var(--border); }}
  .bar-fill.warn {{ background: var(--gray-dark); }}
  .bar-fill.danger {{ background: var(--border); }}

  .tbl {{ width: 100%; border-collapse: collapse; margin-bottom: 6px; border: 2px solid var(--border); }}
  .tbl th {{
    font-size: 12px; font-weight: 900; text-transform: uppercase;
    letter-spacing: 0.08em; text-align: left; padding: 5px 8px;
    border-bottom: 2px solid var(--border); background: var(--gray-light);
  }}
  .tbl td {{ padding: 5px 8px; border-bottom: 1px solid var(--gray-light); font-size: 13px; font-weight: 800; }}
  .tbl tr:last-child td {{ border-bottom: none; }}
  
  .td-time {{ color: var(--gray-dark); white-space: nowrap; width: 40px; }}
  .td-msg {{ color: var(--text); }}
  .td-label {{ color: var(--gray-dark); width: 80px; }}
  .td-value {{ font-weight: 900; font-size: 14px; }}
  .td-svc {{ }}
  .td-status {{ width: 90px; }}
  .status-dot {{ display: flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 900; }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--border); border: 1px solid var(--border); }}
  .dot.offline {{ background: var(--bg); border: 2px solid var(--border); }}
  .status-text.online {{ color: var(--text); }}
  .status-text.offline {{ color: var(--gray-dark); text-decoration: line-through; }}
  
  details {{
    outline: none;
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="title">CAMELOT</div>
  </div>

  <div class="divider-static">System</div>
  <table style="width: 100%; border: none; border-collapse: collapse; margin-bottom: 6px;">
    <tr>
      <td style="width: 70%; vertical-align: top; border: none; padding: 0;">
        <table class="tbl" style="margin-bottom: 0;">
          <thead>
            <tr>
              <th style="width: 30%;">Component</th>
              <th style="width: 35%;">Value</th>
              <th style="width: 35%;">Details</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="td-label">CPU</td>
              <td class="td-value">
                {m["cpu"]}%
                <div class="bar-track"><div class="bar-fill {bar_class(m["cpu"])}" style="width:{m["cpu"]}%"></div></div>
              </td>
              <td>i5 M460</td>
            </tr>
            <tr>
              <td class="td-label">Memory</td>
              <td class="td-value">
                {m["ram_used"]} GB
                <div class="bar-track"><div class="bar-fill {bar_class(m["ram_pct"])}" style="width:{m["ram_pct"]}%"></div></div>
              </td>
              <td>of {m["ram_total"]} GB ({m["ram_pct"]}%)</td>
            </tr>
            <tr>
              <td class="td-label">NAS Disk</td>
              <td class="td-value">
                {m["disk_used"]} GB
                <div class="bar-track"><div class="bar-fill {bar_class(m["disk_pct"])}" style="width:{m["disk_pct"]}%"></div></div>
              </td>
              <td>of {m["disk_total"]} GB ({m["disk_pct"]}%)</td>
            </tr>
            <tr>
              <td class="td-label">CPU Temp</td>
              <td class="td-value">{m["temp"]} °C</td>
              <td>Thermal zone 0</td>
            </tr>
            <tr>
              <td class="td-label">Uptime</td>
              <td class="td-value" colspan="2">{m["uptime_days"]}d {m["uptime_hours"]}h {m["uptime_mins"]}m</td>
            </tr>
          </tbody>
        </table>
      </td>
      <td style="width: 30%; vertical-align: top; border: 2px dashed var(--border); padding: 8px; text-align: center;">
        <div style="font-size: 11px; font-weight: 800; color: var(--gray-dark); margin-top: 45px; text-transform: uppercase;">
          <img src="Camelot_Singularity.png" alt="Camelot" style="width: 100%; height: auto">
        </div>
      </td>
    </tr>
  </table>

  <details open>
    <summary class="divider">Network</summary>
    <table class="tbl">
      <thead><tr><th>Metric</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td class="td-label">▲ OUT</td><td class="td-value">{m["net_out"]} MB</td></tr>
        <tr><td class="td-label">▼ IN</td><td class="td-value">{m["net_in"]} MB</td></tr>
        <tr><td class="td-label">Queued</td><td class="td-value">{m["queued"]}</td></tr>
        <tr><td class="td-label">Done</td><td class="td-value">{m["done"]}</td></tr>
      </tbody>
    </table>
  </details>

  <details open>
    <summary class="divider">Services</summary>
    <table class="tbl">
      <thead><tr><th>Service</th><th>Status</th></tr></thead>
      <tbody>
        {service_rows}
      </tbody>
    </table>
  </details>

  <details open>
    <summary class="divider">Command Log</summary>
    <table class="tbl">
      <thead><tr><th>Time</th><th>Action</th></tr></thead>
      <tbody>
        {log_rows}
      </tbody>
    </table>
  </details>

  <div style="font-size: 10px; text-align: center; margin-top: 15px; color: var(--gray-dark);">
    Generated: {m["timestamp"]}
  </div>
</body>
</html>"""
    return html

if __name__ == "__main__":
    m = get_metrics()
    html = generate_hud(m)
    with open(HUD_PATH, "w") as f:
        f.write(html)
    print(f"HUD generated at {m['timestamp']}")
