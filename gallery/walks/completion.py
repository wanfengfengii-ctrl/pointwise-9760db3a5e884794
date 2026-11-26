from enum import StrEnum


class WalkStatus(StrEnum):
    WALKING = 'walking'
    COMPLETE = 'complete'


def progress_after_arrival(route_length: int, ordinal: int) -> tuple[WalkStatus, int | None]:
    if not 0 <= ordinal < route_length:
        raise ValueError('实际到站序次超出固定站序。')
    if ordinal == route_length - 1:
        return WalkStatus.COMPLETE, None
    return WalkStatus.WALKING, ordinal + 1
