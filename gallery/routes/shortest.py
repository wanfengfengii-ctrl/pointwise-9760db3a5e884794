from heapq import heappop, heappush

from gallery.routes.eligibility import EligibleGraph


def find_shortest_path(graph: EligibleGraph, start: str, end: str) -> tuple[str, ...] | None:
    first = (0, (start,))
    best = {start: first}
    queue = [first]

    # Every edge costs time. An equal-cost alternative to a station cannot
    # be a strict prefix of its other path, so the tie order survives extension.
    while queue:
        score = heappop(queue)
        minutes, path = score
        station = path[-1]
        if score != best[station]:
            continue
        if station == end:
            return path
        for target, duration in graph.outgoing[station].items():
            candidate = (minutes + duration, path + (target,))
            if target not in best or candidate < best[target]:
                best[target] = candidate
                heappush(queue, candidate)
    return None
