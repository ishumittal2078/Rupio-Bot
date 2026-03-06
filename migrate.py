import sqlite3
import psycopg2
import os

# SQLite
sqlite_conn = sqlite3.connect("expenses.db")
sqlite_cursor = sqlite_conn.cursor()

# PostgreSQL
pg_conn = psycopg2.connect(os.getenv("DATABASE_URL"))
pg_cursor = pg_conn.cursor()

tables = ["expenses", "recurring", "goals", "lending", "autopay_log"]

for table in tables:
    sqlite_cursor.execute(f"SELECT * FROM {table}")
    rows = sqlite_cursor.fetchall()

    for row in rows:
        placeholders = ",".join(["%s"] * len(row))
        pg_cursor.execute(
            f"INSERT INTO {table} VALUES ({placeholders})",
            row
        )

pg_conn.commit()

print("Migration complete")