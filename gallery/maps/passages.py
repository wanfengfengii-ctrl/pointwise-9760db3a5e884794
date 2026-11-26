from dataclasses import dataclass

from gallery.maps.stations import is_token


@dataclass(frozen=True, slots=True)
class Passage:
    source: str
    target: str
    minutes: int
    requires: tuple[str, ...]


def normalize_tags(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError('通行属性须为字符串数组。')
    for tag in values:
        if not is_token(tag) or ',' in tag:
            raise ValueError('通行属性须为不含逗号的非空标签。')
    return tuple(sorted(set(values)))


def parse_passages(rows: object) -> tuple[Passage, ...]:
    if not isinstance(rows, list):
        raise ValueError('通道须为 JSON 数组。')

    passages = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'第 {number} 条通道须为对象。')
        source = row.get('source')
        target = row.get('target')
        minutes = row.get('minutes')
        if not is_token(source) or not is_token(target):
            raise ValueError(f'第 {number} 条通道的起站和终站均须填写有效站号。')
        if type(minutes) is not int or minutes <= 0:
            raise ValueError(f'第 {number} 条通道的分钟须为正整数。')
        try:
            requires = normalize_tags(row.get('requires', []))
        except ValueError as error:
            raise ValueError(f'第 {number} 条通道：{error}') from error
        passages.append(Passage(source, target, minutes, requires))
    return tuple(passages)
