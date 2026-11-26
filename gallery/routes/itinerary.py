import json
from dataclasses import asdict, dataclass

from gallery.routes.eligibility import EligibleGraph


@dataclass(frozen=True, slots=True)
class Leg:
    source: str
    target: str
    minutes: int


@dataclass(frozen=True, slots=True)
class Itinerary:
    stations: tuple[str, ...]
    legs: tuple[Leg, ...]
    total_minutes: int


def build_itinerary(graph: EligibleGraph, stations: tuple[str, ...]) -> Itinerary:
    legs = tuple(
        Leg(source, target, graph.outgoing[source][target])
        for source, target in zip(stations, stations[1:])
    )
    return Itinerary(stations, legs, sum(leg.minutes for leg in legs))


def encode_itinerary(itinerary: Itinerary) -> str:
    return json.dumps(asdict(itinerary), ensure_ascii=False)


def decode_itinerary(document: str) -> Itinerary:
    data = json.loads(document)
    return Itinerary(
        tuple(data['stations']),
        tuple(Leg(**leg) for leg in data['legs']),
        data['total_minutes'],
    )
