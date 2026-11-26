import sqlite3

from gallery.issues.receipts import get_guide_receipt
from gallery.walks.completion import progress_after_arrival
from gallery.walks.history import WalkView, append_arrival, get_walk_view


def start_walk(connection: sqlite3.Connection, guide_id: int) -> WalkView:
    guide = get_guide_receipt(connection, guide_id)
    stations = guide.itinerary.stations
    status, _ = progress_after_arrival(len(stations), 0)
    cursor = connection.execute(
        'INSERT INTO walks(guide_id, status) VALUES (?, ?)', (guide.id, status.value)
    )
    walk_id = cursor.lastrowid
    append_arrival(connection, walk_id, 0, stations[0])
    return get_walk_view(connection, walk_id)
