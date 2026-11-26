"""Shift (duty roster) inputs for signboard-routed proofs."""
from dataclasses import dataclass

from gallery.maps.revisions import MapRevision
from gallery.maps.stations import is_token


class InvalidShiftInput(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Shift:
    name: str
    open: frozenset[tuple[str, str]]
    signs: dict[str, str]

    def reading_at(self, station: str) -> str | None:
        return self.signs.get(station)


def _require_text(value: object, label: str) -> str:
    if not is_token(value):
        raise InvalidShiftInput(f'{label}须为不含空白或控制字符的非空文本。')
    return value


def parse_shifts(rows: object, revision: MapRevision) -> tuple[Shift, ...]:
    """Validate the shifts JSON payload against the saved revision."""
    if not isinstance(rows, list) or not rows:
        raise InvalidShiftInput('班况须为非空 JSON 数组。')

    enabled = {station.id for station in revision.stations if station.enabled}
    passages = {(passage.source, passage.target) for passage in revision.passages}
    parsed: list[Shift] = []
    names: set[str] = set()
    observation_sets: list[frozenset[str]] = []

    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise InvalidShiftInput(f'第 {number} 个班况须为对象。')
        name = _require_text(row.get('name'), f'第 {number} 个班况的班名')
        if name in names:
            raise InvalidShiftInput(f'班名 {name} 重复。')
        names.add(name)

        open_rows = row.get('open')
        if not isinstance(open_rows, list):
            raise InvalidShiftInput(f'班况 {name} 的开放通道须为数组。')
        opened: set[tuple[str, str]] = set()
        for pair in open_rows:
            if not isinstance(pair, list) or len(pair) != 2 or not all(is_token(item) for item in pair):
                raise InvalidShiftInput(f'班况 {name} 的开放通道须为 [起站, 到站] 文本对。')
            edge = (pair[0], pair[1])
            if edge not in passages:
                raise InvalidShiftInput(
                    f'班况 {name} 的开放通道 {edge[0]} → {edge[1]} 不在设施修订中。'
                )
            if edge[0] not in enabled or edge[1] not in enabled:
                raise InvalidShiftInput(
                    f'班况 {name} 的开放通道 {edge[0]} → {edge[1]} 经过停用站。'
                )
            opened.add(edge)

        sign_rows = row.get('signs')
        if not isinstance(sign_rows, dict):
            raise InvalidShiftInput(f'班况 {name} 的指示牌须为观察站到读数的对象。')
        signs: dict[str, str] = {}
        for station, reading in sign_rows.items():
            if not is_token(station):
                raise InvalidShiftInput(f'班况 {name} 的观察站号无效。')
            if station not in enabled:
                raise InvalidShiftInput(f'班况 {name} 的观察站 {station} 不在启用站点中。')
            _require_text(reading, f'班况 {name} 在 {station} 的读数')
            signs[station] = reading
        observation_sets.append(frozenset(signs))
        parsed.append(Shift(name, frozenset(opened), signs))

    first = observation_sets[0]
    for shift, observed in zip(parsed[1:], observation_sets[1:]):
        if observed != first:
            raise InvalidShiftInput(
                f'班况 {shift.name} 的观察站与首个班况不一致，各班须列出相同的观察站。'
            )
    return tuple(parsed)


def encode_shifts(shifts: tuple[Shift, ...]) -> str:
    import json

    return json.dumps(
        [
            {
                'name': shift.name,
                'open': sorted(shift.open),
                'signs': dict(sorted(shift.signs.items())),
            }
            for shift in shifts
        ],
        ensure_ascii=False,
    )


def decode_shifts(document: str | None) -> tuple[Shift, ...] | None:
    if document is None:
        return None
    import json

    rows = json.loads(document)
    return tuple(
        Shift(
            row['name'],
            frozenset(tuple(pair) for pair in row['open']),
            dict(row['signs']),
        )
        for row in rows
    )
