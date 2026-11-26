import json
import sqlite3
from dataclasses import dataclass

from gallery.maps.passages import normalize_tags
from gallery.maps.revisions import get_revision
from gallery.routes.eligibility import InvalidProofEndpoint as InvalidProofEndpoint
from gallery.routes.eligibility import build_eligible_graph, validate_endpoints
from gallery.routes.itinerary import Itinerary, build_itinerary, decode_itinerary, encode_itinerary
from gallery.routes.shortest import find_shortest_path


PROOF_SCHEMA = '''
CREATE TABLE IF NOT EXISTS route_proofs (
    id INTEGER PRIMARY KEY,
    revision_id INTEGER NOT NULL REFERENCES map_revisions(id),
    start_station TEXT NOT NULL,
    end_station TEXT NOT NULL,
    allowed TEXT NOT NULL,
    itinerary TEXT
);
'''


class UnknownRevision(LookupError):
    pass


class InvalidProofAttributes(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RouteProof:
    id: int
    revision_id: int
    start: str
    end: str
    allowed: tuple[str, ...]
    itinerary: Itinerary | None


def create_proof(
    connection: sqlite3.Connection,
    revision_id: int,
    start: str,
    end: str,
    allowed: list[str] | tuple[str, ...],
) -> RouteProof:
    revision = get_revision(connection, revision_id)
    if revision is None:
        raise UnknownRevision(f'没有设施修订 {revision_id}。')
    validate_endpoints(revision, start, end)
    try:
        normalized = normalize_tags(allowed)
    except ValueError as error:
        raise InvalidProofAttributes(str(error)) from error

    graph = build_eligible_graph(revision, normalized)
    path = find_shortest_path(graph, start, end)
    itinerary = build_itinerary(graph, path) if path is not None else None
    cursor = connection.execute(
        '''INSERT INTO route_proofs(revision_id, start_station, end_station, allowed, itinerary)
           VALUES (?, ?, ?, ?, ?)''',
        (
            revision_id,
            start,
            end,
            json.dumps(normalized, ensure_ascii=False),
            encode_itinerary(itinerary) if itinerary is not None else None,
        ),
    )
    return RouteProof(cursor.lastrowid, revision_id, start, end, normalized, itinerary)


def get_proof(connection: sqlite3.Connection, proof_id: int) -> RouteProof | None:
    row = connection.execute(
        '''SELECT revision_id, start_station, end_station, allowed, itinerary
           FROM route_proofs WHERE id = ?''',
        (proof_id,),
    ).fetchone()
    if row is None:
        return None
    revision_id, start, end, allowed, itinerary = row
    return RouteProof(
        proof_id,
        revision_id,
        start,
        end,
        tuple(json.loads(allowed)),
        decode_itinerary(itinerary) if itinerary is not None else None,
    )
