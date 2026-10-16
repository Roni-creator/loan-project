
import sqlite3

conn = sqlite3.connect("creditscore.db")
cursor = conn.cursor()

cursor.execute(
    "SELECT name FROM sqlite_master WHERE type = ? ORDER BY name",
    ("table",)
)

print("\nDatabase tables:")
for row in cursor.fetchall():
    print("-", row[0])

conn.close()
