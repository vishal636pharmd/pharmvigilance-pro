# modules/db_config.py
# Kept for backward compatibility — actual DB logic is now in patient_db.py
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

if not USE_POSTGRES:
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "database", "pvpro.db"
    )
else:
    DB_PATH = None


def get_connection():
    if USE_POSTGRES:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        import sqlite3
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return sqlite3.connect(DB_PATH)


def get_placeholder():
    return "%s" if USE_POSTGRES else "?"


def adapt_query(query):
    if USE_POSTGRES:
        return query.replace("?", "%s")
    return query