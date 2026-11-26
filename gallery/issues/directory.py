import sqlite3

from gallery.issues.admission import require_issuable_proof
from gallery.issues.snapshots import GuideSnapshot, freeze_guide


DIRECTORY_SCHEMA = '''
CREATE TABLE IF NOT EXISTS guide_directory (
    slot INTEGER PRIMARY KEY CHECK (slot = 1),
    guide_id INTEGER NOT NULL REFERENCES guides(id)
);
'''


def publish_guide(connection: sqlite3.Connection, proof_id: int) -> GuideSnapshot:
    """Freeze the approved proof and advance the directory in one caller transaction."""
    proof = require_issuable_proof(connection, proof_id)
    guide = freeze_guide(connection, proof)
    connection.execute(
        '''INSERT INTO guide_directory(slot, guide_id) VALUES (1, ?)
           ON CONFLICT(slot) DO UPDATE SET guide_id = excluded.guide_id''',
        (guide.id,),
    )
    return guide


def get_current_guide_id(connection: sqlite3.Connection) -> int | None:
    row = connection.execute('SELECT guide_id FROM guide_directory WHERE slot = 1').fetchone()
    return row[0] if row is not None else None
