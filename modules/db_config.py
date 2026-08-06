# modules/db_config.py
# Handles both local SQLite (development) and PostgreSQL (Render production)

import os
import sqlite3

# Check if running on Render with PostgreSQL
DATABASE_URL = os.environ.get("DATABASE_URL", "")

USE_POSTGRES = bool(DATABASE_URL)

if not USE_POSTGRES:
    # Local development — use SQLite
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "database", "pvpro.db"
    )
else:
    DB_PATH = None  # Not used when PostgreSQL is active


def get_connection():
    """
    Returns a database connection.
    Uses PostgreSQL on Render, SQLite locally.
    """
    if USE_POSTGRES:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return sqlite3.connect(DB_PATH)


def get_placeholder():
    """
    Returns the correct SQL placeholder.
    PostgreSQL uses %s, SQLite uses ?
    """
    return "%s" if USE_POSTGRES else "?"


def adapt_query(query):
    """
    Converts SQLite ? placeholders to PostgreSQL %s placeholders.
    """
    if USE_POSTGRES:
        return query.replace("?", "%s")
    return query