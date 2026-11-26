from dataclasses import dataclass

from gallery.maps.revisions import MapRevision


class InvalidProofEndpoint(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EligibleGraph:
    outgoing: dict[str, dict[str, int]]


def validate_endpoints(revision: MapRevision, start: str, end: str) -> None:
    enabled = {station.id for station in revision.stations if station.enabled}
    for role, station_id in (('起站', start), ('终站', end)):
        if station_id not in enabled:
            raise InvalidProofEndpoint(f'{role} {station_id or "（空）"} 不存在或已停用。')


def build_eligible_graph(revision: MapRevision, allowed: tuple[str, ...]) -> EligibleGraph:
    outgoing = {station.id: {} for station in revision.stations if station.enabled}
    permitted = set(allowed)
    for passage in revision.passages:
        if passage.source not in outgoing or passage.target not in outgoing:
            continue
        if not permitted.issuperset(passage.requires):
            continue
        neighbors = outgoing[passage.source]
        previous = neighbors.get(passage.target)
        if previous is None or passage.minutes < previous:
            neighbors[passage.target] = passage.minutes
    return EligibleGraph(outgoing)
