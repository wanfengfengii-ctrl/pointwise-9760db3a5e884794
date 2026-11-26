import json
import sqlite3
from dataclasses import dataclass

from gallery.routes.itinerary import Itinerary, decode_itinerary, encode_itinerary
from gallery.routes.proofs import RouteProof


GUIDE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS guides (
    id INTEGER PRIMARY KEY,
    proof_id INTEGER NOT NULL REFERENCES route_proofs(id),
    revision_id INTEGER NOT NULL REFERENCES map_revisions(id),
    allowed TEXT NOT NULL,
    itinerary TEXT NOT NULL
);
'''


@dataclass(frozen=True, slots=True)
class GuideSnapshot:
    id: int
    proof_id: int
    revision_id: int
    allowed: tuple[str, ...]
    itinerary: Itinerary


def freeze_guide(connection: sqlite3.Connection, proof: RouteProof) -> GuideSnapshot:
    itinerary = proof.itinerary
    if itinerary is None:
        raise ValueError('封存发行需要可达校样。')
    cursor = connection.execute(
        'INSERT INTO guides(proof_id, revision_id, allowed, itinerary) VALUES (?, ?, ?, ?)',
        (proof.id, proof.revision_id, json.dumps(proof.allowed, ensure_ascii=False),
         encode_itinerary(itinerary)),
    )
    return GuideSnapshot(cursor.lastrowid, proof.id, proof.revision_id, proof.allowed, itinerary)


def get_guide_snapshot(connection: sqlite3.Connection, guide_id: int) -> GuideSnapshot | None:
    row = connection.execute(
        'SELECT proof_id, revision_id, allowed, itinerary FROM guides WHERE id = ?', (guide_id,)
    ).fetchone()
    if row is None:
        return None
    proof_id, revision_id, allowed, itinerary = row
    return GuideSnapshot(
        guide_id, proof_id, revision_id, tuple(json.loads(allowed)), decode_itinerary(itinerary)
    )
