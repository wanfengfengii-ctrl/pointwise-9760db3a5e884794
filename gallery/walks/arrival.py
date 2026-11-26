import sqlite3

from gallery.walks.completion import WalkStatus, progress_after_arrival
from gallery.walks.history import WalkView, append_arrival, get_walk_view


class ArrivalConflict(ValueError):
    pass


def confirm_arrival(
    connection: sqlite3.Connection, walk_id: int, station: str, ordinal: int | None
) -> WalkView:
    """Check and apply the arrival while the caller holds the write transaction."""
    view = get_walk_view(connection, walk_id)
    if view.record.status == WalkStatus.COMPLETE or view.next_leg is None:
        raise ArrivalConflict('本次走览已完成。')
    if type(ordinal) is not int or ordinal != view.next_ordinal or station != view.next_leg.target:
        raise ArrivalConflict('提交的站点或序次与当前指令不符。')

    append_arrival(connection, walk_id, ordinal, station)
    status, _ = progress_after_arrival(len(view.guide.itinerary.stations), ordinal)
    connection.execute('UPDATE walks SET status = ? WHERE id = ?', (status.value, walk_id))
    return get_walk_view(connection, walk_id)
