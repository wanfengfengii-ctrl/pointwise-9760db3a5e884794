"""Station-by-station engine for signboard-routed walks."""
import sqlite3
from dataclasses import dataclass

from gallery.issues.receipts import GuideReceipt, get_guide_receipt
from gallery.maps.revisions import get_revision
from gallery.routes.eligibility import build_eligible_graph
from gallery.signboards.planner import (
    CompleteAction,
    MoveAction,
    ReadAction,
    SignboardPolicy,
    build_signboard_policy,
)
from gallery.walks.completion import WalkStatus
from gallery.walks.history import (
    WalkRecord,
    append_arrival,
    append_report,
    get_walk_record,
)


class WalkConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SignboardWalkView:
    record: WalkRecord
    guide: GuideReceipt
    policy: SignboardPolicy
    belief: frozenset[int]
    action: object
    next_ordinal: int


def build_guide_policy(connection: sqlite3.Connection, guide) -> SignboardPolicy:
    revision = get_revision(connection, guide.revision_id)
    graph = build_eligible_graph(revision, guide.allowed)
    return build_signboard_policy(graph, guide.shifts, guide.start, guide.end)


def current_belief(policy: SignboardPolicy, record: WalkRecord) -> frozenset[int]:
    """Replay accepted reports to recover the set of compatible shifts."""
    belief = frozenset(range(len(policy.shifts)))
    for report in record.reports:
        survivors = policy.compatible_reading(report.station, belief, report.reading)
        if survivors is None:
            raise WalkConflict('保存的报牌与发行班况不再相容。')
        belief = survivors
    return belief


def get_signboard_view(connection: sqlite3.Connection, walk_id: int) -> SignboardWalkView:
    record = get_walk_record(connection, walk_id)
    guide = get_guide_receipt(connection, record.guide_id)
    if guide.shifts is None:
        raise WalkConflict('该发行不是按牌分流导览。')
    policy = build_guide_policy(connection, guide)
    belief = current_belief(policy, record)
    station = record.arrivals[-1]
    action = policy.action_at(station, belief)
    if action is None:
        raise WalkConflict('当前状态没有可发行的走法。')
    return SignboardWalkView(record, guide, policy, belief, action, len(record.arrivals))


def start_signboard_walk(connection: sqlite3.Connection, guide_id: int) -> SignboardWalkView:
    guide = get_guide_receipt(connection, guide_id)
    if guide.shifts is None:
        raise WalkConflict('该发行不是按牌分流导览。')
    policy = build_guide_policy(connection, guide)
    if not policy.issuable:
        raise WalkConflict('该按牌校样没有可发行走法。')
    initial_status = (
        WalkStatus.COMPLETE.value if guide.start == guide.end else WalkStatus.WALKING.value
    )
    cursor = connection.execute(
        'INSERT INTO walks(guide_id, status) VALUES (?, ?)',
        (guide.id, initial_status),
    )
    walk_id = cursor.lastrowid
    append_arrival(connection, walk_id, 0, guide.start)
    return get_signboard_view(connection, walk_id)


def confirm_signboard_arrival(
    connection: sqlite3.Connection, walk_id: int, station: str, ordinal: int | None
) -> SignboardWalkView:
    view = get_signboard_view(connection, walk_id)
    if view.record.status == WalkStatus.COMPLETE or isinstance(view.action, CompleteAction):
        raise WalkConflict('本次走览已完成。')
    action = view.action
    if not isinstance(action, MoveAction):
        raise WalkConflict('当前动作是在本站读牌，请先报告指示牌读数。')
    if type(ordinal) is not int or ordinal != view.next_ordinal or station != action.station:
        raise WalkConflict('提交的站点或序次与当前指令不符。')

    append_arrival(connection, walk_id, ordinal, station)
    refreshed = get_signboard_view(connection, walk_id)
    if isinstance(refreshed.action, CompleteAction):
        connection.execute(
            'UPDATE walks SET status = ? WHERE id = ?', (WalkStatus.COMPLETE.value, walk_id)
        )
        refreshed = get_signboard_view(connection, walk_id)
    return refreshed


def accept_signboard_reading(
    connection: sqlite3.Connection,
    walk_id: int,
    station: str,
    ordinal: int | None,
    reading: str,
) -> SignboardWalkView:
    view = get_signboard_view(connection, walk_id)
    if view.record.status == WalkStatus.COMPLETE or isinstance(view.action, CompleteAction):
        raise WalkConflict('本次走览已完成。')
    action = view.action
    if not isinstance(action, ReadAction):
        raise WalkConflict('当前动作不是读牌，该读数暂不受理。')
    current_station = view.record.arrivals[-1]
    expected_ordinal = len(view.record.arrivals) - 1
    if (
        type(ordinal) is not int
        or ordinal != expected_ordinal
        or station != current_station
        or station != action.station
    ):
        raise WalkConflict('读数提交的站点或序次与当前读牌提示不符。')
    if not isinstance(reading, str) or not reading:
        raise WalkConflict('请填写本站指示牌读数。')
    next_belief = view.policy.compatible_reading(current_station, view.belief, reading)
    if next_belief is None:
        raise WalkConflict('该读数与仍相容的班况均不一致。')

    sequence = len(view.record.reports)
    append_report(connection, walk_id, sequence, ordinal, current_station, reading)
    return get_signboard_view(connection, walk_id)
