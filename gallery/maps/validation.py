from dataclasses import dataclass

from gallery.maps.passages import Passage, parse_passages
from gallery.maps.stations import Station, parse_stations


class MapInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MapDraft:
    stations: tuple[Station, ...]
    passages: tuple[Passage, ...]


def validate_map_draft(station_rows: object, passage_rows: object) -> MapDraft:
    try:
        stations = parse_stations(station_rows)
        passages = parse_passages(passage_rows)
    except ValueError as error:
        raise MapInputError(str(error)) from error

    station_ids = {station.id for station in stations}
    for passage in passages:
        if passage.source not in station_ids or passage.target not in station_ids:
            raise MapInputError(f'通道 {passage.source} → {passage.target} 引用了未录入的站点。')
    return MapDraft(stations, passages)
