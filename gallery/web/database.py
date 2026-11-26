import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from gallery.issues.directory import DIRECTORY_SCHEMA
from gallery.issues.snapshots import GUIDE_SCHEMA
from gallery.maps.revisions import MAP_SCHEMA
from gallery.routes.proofs import PROOF_SCHEMA
from gallery.walks.history import WALK_SCHEMA


DatabasePath = str | Path
SCHEMA = '\n'.join((MAP_SCHEMA, PROOF_SCHEMA, GUIDE_SCHEMA, DIRECTORY_SCHEMA, WALK_SCHEMA))


def open_database(path: DatabasePath) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def initialize_database(path: DatabasePath) -> None:
    with closing(open_database(path)) as connection, connection:
        connection.executescript(f'BEGIN IMMEDIATE;\n{SCHEMA}\nCOMMIT;')


@contextmanager
def write_transaction(path: DatabasePath):
    with closing(open_database(path)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        yield connection


@contextmanager
def read_transaction(path: DatabasePath):
    with closing(open_database(path)) as connection, connection:
        connection.execute('PRAGMA query_only = ON')
        connection.execute('BEGIN')
        yield connection
