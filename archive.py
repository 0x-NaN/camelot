import psycopg2
import psycopg2.extras
import json
import os
from datetime import datetime
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, ARCHIVE_DIR

DB = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST
)

os.makedirs(ARCHIVE_DIR, exist_ok=True)


def archive_table(table):
    with DB.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT * FROM {table}
            WHERE last_accessed < NOW() - INTERVAL '14 days'
        """)
        rows = cur.fetchall()

        if not rows:
            print(f"[{table}] Nothing to archive.")
            return

        # Summarise to keep under 1MB
        summary = []
        for row in rows:
            entry = {k: str(v) for k, v in row.items()}
            summary.append(entry)

        week = datetime.now().strftime("%Y-W%W")
        filename = f"{ARCHIVE_DIR}/{table}_{week}.json"

        # Append to existing weekly file if it exists
        if os.path.exists(filename):
            with open(filename, "r") as f:
                existing = json.load(f)
            summary = existing + summary

        with open(filename, "w") as f:
            json.dump(summary, f, indent=2)

        # Delete archived rows from DB
        ids = [row["id"] for row in rows]
        cur.execute(f"DELETE FROM {table} WHERE id = ANY(%s)", (ids,))
        DB.commit()

        print(f"[{table}] Archived {len(rows)} rows to {filename}")

if __name__ == "__main__":
    print(f"Camelot archival run — {datetime.now()}")
    archive_table("logs")
    archive_table("jobs")
    archive_table("checkpoints")
    print("Done.")
