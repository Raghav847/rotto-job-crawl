"""Postgres configuration and repeatable schema initialization."""

import os
import time
from pathlib import Path
from urllib.parse import quote

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


def database_url():
    load_dotenv()
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = quote(os.environ.get("POSTGRES_USER", "rotto"), safe="")
    password = quote(os.environ.get("POSTGRES_PASSWORD", "rotto-local"), safe="")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "55432")
    name = quote(os.environ.get("POSTGRES_DB", "rotto"), safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def connect(url, attempts=15):
    for attempt in range(attempts):
        try:
            return psycopg.connect(url, row_factory=dict_row, connect_timeout=3, autocommit=True)
        except psycopg.OperationalError:
            if attempt + 1 == attempts:
                raise
            time.sleep(1)


def initialize(connection):
    with connection.transaction():
        connection.execute(Path(__file__).with_name("schema.sql").read_text())


if __name__ == "__main__":
    with connect(database_url()) as connection:
        initialize(connection)
    print("Postgres jobs schema ready")
