import sqlite3
import pandas as pd

DB_FILE = "artifacts/python-backend/market_cache/fii_dii_cache.db"

try:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("Tables in DB:", tables)
        for table in tables:
            t = table[0]
            df = pd.read_sql(f"SELECT * FROM {t}", conn)
            print(f"Table {t} has {len(df)} rows. Min date: {df['date'].min()}, Max date: {df['date'].max()}")
except Exception as e:
    print("Error:", e)