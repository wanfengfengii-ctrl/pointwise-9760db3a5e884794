import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from gallery.issues.directory import DIRECTORY_SCHEMA
from gallery.issues.snapshots import GUIDE_SCHEMA
from gallery.maps.revisions import MAP_SCHEMA
from gallery.routes.proofs import PROOF_SCHEMA
from gallery.walks.history import WALK_SCHEMA, REPORT_SCHEMA


DatabasePath = str | Path
SCHEMA = '\n'.join((MAP_SCHEMA, PROOF_SCHEMA, GUIDE_SCHEMA, DIRECTORY_SCHEMA, WALK_SCHEMA, REPORT_SCHEMA))


def open_database(path: DatabasePath) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info({table})').fetchall()}


def _migrate(connection: sqlite3.Connection) -> None:
    """Upgrade databases created before signboard-routed guides existed."""
    proof_columns = _column_names(connection, 'route_proofs')
    if proof_columns and 'shifts' not in proof_columns:
        connection.execute('ALTER TABLE route_proofs ADD COLUMN shifts TEXT')
        connection.execute(
            "ALTER TABLE route_proofs ADD COLUMN issuable INTEGER NOT NULL DEFAULT 1"
        )
        connection.execute(
            'UPDATE route_proofs SET issuable = 0 WHERE itinerary IS NULL'
        )

    guide_columns = _column_names(connection, 'guides')
    if guide_columns and 'shifts' not in guide_columns:
        # Rebuild the guides table so itinerary can be NULL for shift guides.
        connection.execute('PRAGMA foreign_keys = OFF')
        connection.execute('ALTER TABLE guides RENAME TO guides_legacy')
        connection.execute(GUIDE_SCHEMA)
        connection.execute(
            '''INSERT INTO guides(id, proof_id, revision_id, start_station, end_station,
                                  allowed, itinerary, shifts)
               SELECT g.id, g.proof_id, g.revision_id,
                      json_extract(g.itinerary, '$.stations[0]'),
                      json_extract(g.itinerary, '$.stations[#-1]'),
                      g.allowed, g.itinerary, NULL
               FROM guides_legacy AS g'''
        )
        connection.execute('DROP TABLE guides_legacy')
        connection.execute('PRAGMA foreign_keys = ON')


def initialize_database(path: DatabasePath) -> None:
    with closing(open_database(path)) as connection, connection:
        connection.executescript(f'BEGIN IMMEDIATE;\n{SCHEMA}\nCOMMIT;')
        _migrate(connection)


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
