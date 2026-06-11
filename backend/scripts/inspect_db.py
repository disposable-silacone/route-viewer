import sqlite3
from pathlib import Path

db = Path(".data/app.db")
if not db.exists():
    print("no db")
    raise SystemExit(1)
conn = sqlite3.connect(db)
row = conn.execute("SELECT sql FROM sqlite_master WHERE name='activities'").fetchone()
print("table sql:", row[0] if row else None)
for idx in conn.execute("PRAGMA index_list(activities)"):
    print("index", idx)
    info = conn.execute(f'PRAGMA index_info("{idx[1]}")').fetchall()
    print("  cols", [r[2] for r in info])
print("count", conn.execute("select count(*) from activities").fetchone()[0])
print("customers", conn.execute("select customer_id, count(*) from activities group by customer_id").fetchall())
