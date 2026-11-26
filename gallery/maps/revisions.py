import json
import sqlite3
from dataclasses import asdict, dataclass

from gallery.maps.passages import Passage
from gallery.maps.stations import Station
from gallery.maps.validation import validate_map_draft


MAP_SCHEMA = '''
CREATE TABLE IF NOT EXISTS map_revisions (
    id INTEGER PRIMARY KEY,
    document TEXT NOT NULL
);
'''


@dataclass(frozen=True, slots=True)
class MapRevision:
    id: int
    stations: tuple[Station, ...]
    passages: tuple[Passage, ...]

    def document(self) -> dict[str, list]:
        return {
            'stations': [asdict(station) for station in self.stations],
            'passages': [asdict(passage) for passage in self.passages],
        }


def save_revision(
    connection: sqlite3.Connection, station_rows: object, passage_rows: object
) -> MapRevision:
    draft = validate_map_draft(station_rows, passage_rows)
    cursor = connection.execute(
        'INSERT INTO map_revisions(document) VALUES (?)',
        (json.dumps(asdict(draft), ensure_ascii=False),),
    )
    return MapRevision(cursor.lastrowid, draft.stations, draft.passages)


def get_revision(connection: sqlite3.Connection, revision_id: int) -> MapRevision | None:
    row = connection.execute(
        'SELECT document FROM map_revisions WHERE id = ?', (revision_id,)
    ).fetchone()
    if row is None:
        return None

    document = json.loads(row[0])
    stations = tuple(Station(item['id'], item['enabled']) for item in document['stations'])
    passages = tuple(
        Passage(item['source'], item['target'], item['minutes'], tuple(item['requires']))
        for item in document['passages']
    )
    return MapRevision(revision_id, stations, passages)


def has_revisions(connection: sqlite3.Connection) -> bool:
    return connection.execute('SELECT 1 FROM map_revisions LIMIT 1').fetchone() is not None
