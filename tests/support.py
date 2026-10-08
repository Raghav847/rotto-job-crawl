"""Fresh, uniquely named test databases; never reset a configured live database."""

import os
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from crawler.database import connect, database_url, initialize


@contextmanager
def isolated_database():
    live_url = database_url()
    admin_url = os.environ.get("TEST_DATABASE_ADMIN_URL") or make_conninfo(live_url, dbname="postgres")
    name = "rotto_test_" + uuid4().hex
    # CREATE must succeed before entering cleanup: an existing database is never dropped.
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        try:
            with connect(make_conninfo(admin_url, dbname=name), attempts=1) as connection:
                actual = connection.execute("SELECT current_database() AS name").fetchone()["name"]
                if actual != name:
                    raise RuntimeError("Test connection did not enter its freshly created database")
                initialize(connection)
                yield connection
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
