import json
import sqlite3
from dataclasses import dataclass

from gallery.routes.itinerary import Itinerary, decode_itinerary, encode_itinerary
from gallery.routes.proofs import RouteProof
from gallery.signboards.shifts import Shift, decode_shifts, encode_shifts


GUIDE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS guides (
    id INTEGER PRIMARY KEY,
    proof_id INTEGER NOT NULL REFERENCES route_proofs(id),
    revision_id INTEGER NOT NULL REFERENCES map_revisions(id),
    start_station TEXT NOT NULL,
    end_station TEXT NOT NULL,
    allowed TEXT NOT NULL,
    itinerary TEXT,
    shifts TEXT
);
'''


@dataclass(frozen=True, slots=True)
class GuideSnapshot:
    id: int
    proof_id: int
    revision_id: int
    start: str
    end: str
    allowed: tuple[str, ...]
    itinerary: Itinerary | None
    shifts: tuple[Shift, ...] | None


def freeze_guide(connection: sqlite3.Connection, proof: RouteProof) -> GuideSnapshot:
    if not proof.issuable:
        raise ValueError('封存发行需要可发行校样。')
    if proof.shifts is not None:
        itinerary_document = None
        shifts_document = encode_shifts(proof.shifts)
    else:
        if proof.itinerary is None:
            raise ValueError('封存固定发行需要可达校样。')
        itinerary_document = encode_itinerary(proof.itinerary)
        shifts_document = None
    cursor = connection.execute(
        '''INSERT INTO guides(proof_id, revision_id, start_station, end_station,
                              allowed, itinerary, shifts)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (
            proof.id,
            proof.revision_id,
            proof.start,
            proof.end,
            json.dumps(proof.allowed, ensure_ascii=False),
            itinerary_document,
            shifts_document,
        ),
    )
    return GuideSnapshot(
        cursor.lastrowid,
        proof.id,
        proof.revision_id,
        proof.start,
        proof.end,
        proof.allowed,
        proof.itinerary,
        proof.shifts,
    )


def get_guide_snapshot(connection: sqlite3.Connection, guide_id: int) -> GuideSnapshot | None:
    row = connection.execute(
        '''SELECT proof_id, revision_id, start_station, end_station, allowed, itinerary, shifts
           FROM guides WHERE id = ?''',
        (guide_id,),
    ).fetchone()
    if row is None:
        return None
    proof_id, revision_id, start, end, allowed, itinerary, shifts_document = row
    return GuideSnapshot(
        guide_id,
        proof_id,
        revision_id,
        start,
        end,
        tuple(json.loads(allowed)),
        decode_itinerary(itinerary) if itinerary is not None else None,
        decode_shifts(shifts_document),
    )
