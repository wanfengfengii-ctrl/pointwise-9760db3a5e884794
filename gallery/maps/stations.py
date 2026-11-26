from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    enabled: bool


def is_token(value: object) -> bool:
    return isinstance(value, str) and bool(value) and all(
        character.isprintable() and not character.isspace() for character in value
    )


def parse_stations(rows: object) -> tuple[Station, ...]:
    if not isinstance(rows, list) or not rows:
        raise ValueError('站点须为非空 JSON 数组。')

    stations = []
    seen = set()
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'第 {number} 个站点须为对象。')
        station_id = row.get('id')
        enabled = row.get('enabled')
        if not is_token(station_id):
            raise ValueError(f'第 {number} 个站点的站号无效。')
        if station_id in seen:
            raise ValueError(f'站号 {station_id} 重复。')
        if type(enabled) is not bool:
            raise ValueError(f'站点 {station_id} 的启停值须为 true 或 false。')
        stations.append(Station(station_id, enabled))
        seen.add(station_id)
    return tuple(stations)
