import sqlite3
from dataclasses import dataclass

from gallery.issues.receipts import GuideReceipt, get_guide_receipt
from gallery.routes.itinerary import Leg
from gallery.walks.completion import WalkStatus, progress_after_arrival


WALK_SCHEMA = '''
CREATE TABLE IF NOT EXISTS walks (
    id INTEGER PRIMARY KEY,
    guide_id INTEGER NOT NULL REFERENCES guides(id),
    status TEXT NOT NULL CHECK (status IN ('walking', 'complete'))
);
CREATE TABLE IF NOT EXISTS walk_arrivals (
    walk_id INTEGER NOT NULL REFERENCES walks(id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    station TEXT NOT NULL,
    PRIMARY KEY (walk_id, ordinal)
);
'''

REPORT_SCHEMA = '''
CREATE TABLE IF NOT EXISTS walk_reports (
    walk_id INTEGER NOT NULL REFERENCES walks(id),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    station TEXT NOT NULL,
    reading TEXT NOT NULL,
    PRIMARY KEY (walk_id, sequence)
);
'''


class UnknownWalk(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ReportEntry:
    sequence: int
    ordinal: int
    station: str
    reading: str


@dataclass(frozen=True, slots=True)
class WalkRecord:
    id: int
    guide_id: int
    status: WalkStatus
    arrivals: tuple[str, ...]
    reports: tuple[ReportEntry, ...]

    def timeline(self) -> tuple[tuple[str, dict], ...]:
        """Accepted arrivals and reports in acceptance order."""
        events: list[tuple[int, int, str, dict]] = []
        for ordinal, station in enumerate(self.arrivals):
            events.append((ordinal, 0, 'arrival', {'ordinal': ordinal, 'station': station}))
        for report in self.reports:
            events.append((report.ordinal, 1, 'report', {
                'ordinal': report.ordinal,
                'station': report.station,
                'reading': report.reading,
            }))
        events.sort(key=lambda item: (item[0], item[1], item[2]))
        return tuple((kind, payload) for _ordinal, _tie, kind, payload in events)


@dataclass(frozen=True, slots=True)
class WalkView:
    record: WalkRecord
    guide: GuideReceipt
    next_ordinal: int | None
    next_leg: Leg | None


def append_arrival(connection: sqlite3.Connection, walk_id: int, ordinal: int, station: str) -> None:
    connection.execute(
        'INSERT INTO walk_arrivals(walk_id, ordinal, station) VALUES (?, ?, ?)',
        (walk_id, ordinal, station),
    )


def append_report(
    connection: sqlite3.Connection,
    walk_id: int,
    sequence: int,
    ordinal: int,
    station: str,
    reading: str,
) -> None:
    connection.execute(
        '''INSERT INTO walk_reports(walk_id, sequence, ordinal, station, reading)
           VALUES (?, ?, ?, ?, ?)''',
        (walk_id, sequence, ordinal, station, reading),
    )


def get_walk_record(connection: sqlite3.Connection, walk_id: int) -> WalkRecord:
    row = connection.execute('SELECT guide_id, status FROM walks WHERE id = ?', (walk_id,)).fetchone()
    if row is None:
        raise UnknownWalk(f'没有走览 {walk_id}。')
    arrivals = tuple(
        station for (station,) in connection.execute(
            'SELECT station FROM walk_arrivals WHERE walk_id = ? ORDER BY ordinal', (walk_id,)
        )
    )
    reports = tuple(
        ReportEntry(sequence, ordinal, station, reading)
        for sequence, ordinal, station, reading in connection.execute(
            '''SELECT sequence, ordinal, station, reading FROM walk_reports
               WHERE walk_id = ? ORDER BY sequence''',
            (walk_id,),
        )
    )
    return WalkRecord(walk_id, row[0], WalkStatus(row[1]), arrivals, reports)


def get_walk_view(connection: sqlite3.Connection, walk_id: int) -> WalkView:
    record = get_walk_record(connection, walk_id)
    guide = get_guide_receipt(connection, record.guide_id)
    _, next_ordinal = progress_after_arrival(len(guide.itinerary.stations), len(record.arrivals) - 1)
    next_leg = guide.itinerary.legs[next_ordinal - 1] if next_ordinal is not None else None
    return WalkView(record, guide, next_ordinal, next_leg)
