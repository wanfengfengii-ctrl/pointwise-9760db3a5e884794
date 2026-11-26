import json
import sqlite3
from pathlib import Path

from gallery.maps.revisions import MapRevision, has_revisions, save_revision


DEMO_MAP = Path(__file__).resolve().parents[2] / 'samples' / 'demo-map.json'


def seed_demo_map(connection: sqlite3.Connection) -> MapRevision | None:
    """Import the demonstration revision inside the caller's write transaction."""
    if has_revisions(connection):
        return None
    document = json.loads(DEMO_MAP.read_text(encoding='utf-8'))
    return save_revision(connection, document['stations'], document['passages'])
