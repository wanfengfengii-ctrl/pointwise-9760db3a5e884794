"""Belief-space policy synthesis for signboard-routed proofs.

The service never knows which shift is on duty; it only keeps the set of
shifts still compatible with the accepted readings (the belief).  A policy is
issuable when, from the initial belief at the start station, every move edge
is open under every compatible shift and every possible subsequent reading
still leaves a finite continuation to the end station.

Winning states are discovered by least fixed point over the reachable
AND/OR graph.  The action that first witnesses a winning state is locked in:
every selected action then descends to a strictly smaller rank, so the
resulting policy is acyclic even when the physical graph contains cycles.
"""
from dataclasses import dataclass, field

from gallery.routes.eligibility import EligibleGraph
from gallery.signboards.shifts import Shift


State = tuple[str, frozenset[int]]
Belief = frozenset[int]


@dataclass(frozen=True, slots=True)
class MoveAction:
    kind: str
    station: str
    minutes: int


@dataclass(frozen=True, slots=True)
class ReadAction:
    kind: str
    station: str


@dataclass(frozen=True, slots=True)
class CompleteAction:
    kind: str
    station: str


@dataclass(frozen=True, slots=True)
class SignboardPolicy:
    graph: EligibleGraph
    start: str
    end: str
    shifts: tuple[Shift, ...]
    actions: dict[State, object] = field(default_factory=dict)
    ranks: dict[State, int] = field(default_factory=dict)
    issuable: bool = False

    def initial_state(self) -> State:
        return self.start, frozenset(range(len(self.shifts)))

    def action_at(self, station: str, belief: Belief) -> object:
        return self.actions.get((station, belief))

    def move_targets(self, station: str, belief: Belief) -> dict[str, int]:
        """Edges from station open under every shift in the belief."""
        targets: dict[str, int] = {}
        for target, minutes in self.graph.outgoing[station].items():
            if all((station, target) in self.shifts[index].open for index in belief):
                targets[target] = minutes
        return targets

    def compatible_reading(self, station: str, belief: Belief, reading: str) -> Belief | None:
        survivors = frozenset(
            index
            for index in belief
            if self.shifts[index].reading_at(station) == reading
        )
        return survivors or None

    def read_successors(self, station: str, belief: Belief) -> dict[str, Belief]:
        groups: dict[str, set[int]] = {}
        for index in belief:
            reading = self.shifts[index].reading_at(station)
            if reading is None:
                return {}
            groups.setdefault(reading, set()).add(index)
        return {reading: frozenset(indices) for reading, indices in groups.items()}


def build_signboard_policy(
    graph: EligibleGraph,
    shifts: tuple[Shift, ...],
    start: str,
    end: str,
) -> SignboardPolicy:
    policy = SignboardPolicy(graph=graph, start=start, end=end, shifts=shifts)

    initial = policy.initial_state()
    transitions: dict[State, dict[str, dict]] = {}
    queue = [initial]
    queued = {initial}
    while queue:
        station, belief = queue.pop(0)
        entry: dict[str, dict] = {'moves': {}, 'reads': {}}
        for target, minutes in policy.move_targets(station, belief).items():
            successor = (target, belief)
            entry['moves'][target] = (minutes, successor)
            if successor not in queued:
                queued.add(successor)
                queue.append(successor)
        for reading, next_belief in policy.read_successors(station, belief).items():
            successor = (station, next_belief)
            entry['reads'][reading] = successor
            if successor not in queued:
                queued.add(successor)
                queue.append(successor)
        transitions[(station, belief)] = entry

    winning: set[State] = set()
    ranks: dict[State, int] = {}
    actions: dict[State, object] = {}
    changed = True
    while changed:
        changed = False
        for state, entry in transitions.items():
            if state in winning:
                continue
            station, _belief = state
            if station == end:
                winning.add(state)
                ranks[state] = 0
                actions[state] = CompleteAction('complete', end)
                changed = True
                continue
            move_options = [
                (successor, target, minutes)
                for target, (minutes, successor) in entry['moves'].items()
                if successor in winning
            ]
            if move_options:
                successor, target, minutes = min(
                    move_options, key=lambda item: (ranks[item[0]], item[2], item[1])
                )
                winning.add(state)
                ranks[state] = ranks[successor] + 1
                actions[state] = MoveAction('move', target, minutes)
                changed = True
                continue
            read_groups = entry['reads']
            if len(read_groups) > 1 and all(successor in winning for successor in read_groups.values()):
                successor_ranks = [ranks[successor] for successor in read_groups.values()]
                winning.add(state)
                ranks[state] = 1 + max(successor_ranks)
                actions[state] = ReadAction('read', station)
                changed = True

    return SignboardPolicy(
        graph=graph,
        start=start,
        end=end,
        shifts=shifts,
        actions=actions,
        ranks=ranks,
        issuable=initial in winning,
    )
