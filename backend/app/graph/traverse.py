"""Backend-neutral neighbourhood traversal.

`neighborhood` is the one query in the five-query surface whose Cypher would
differ meaningfully between Neo4j and Kuzu, because variable-length patterns are
where the dialects diverge most. Building it as a BFS over a single-hop
primitive that both backends implement makes the two results identical by
construction rather than by review - which is what acceptance criterion 9
("passes on either backend") actually needs.

Cost is bounded by `MAX_NODES`: the force-graph is a comprehension aid, and a
thousand-node hairball helps nobody.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Protocol

# Sized to hold the whole domain pack (157 entity + 28 policy nodes) rather than
# to a round number, so `overview` shows the graph instead of an arbitrary
# prefix of it. The cap still exists, and still bounds a runaway traversal.
#
# A 185-node overview is genuinely busy. That is the honest picture of the
# record, and the readable view is `neighborhood` centred on one entity - which
# is what the panel's search box is for. Raising this further would trade
# legibility for a number nobody reads off a hairball.
MAX_NODES = 220


class Traversable(Protocol):
    def node_by_key(self, key_value: str) -> dict[str, Any] | None: ...

    def edges_of(self, key_value: str) -> list[dict[str, str]]: ...


def bfs(store: Traversable, entity_id: str, hops: int = 2) -> dict[str, Any]:
    root = store.node_by_key(entity_id)
    if root is None:
        return {"root": entity_id, "found": False, "nodes": [], "links": [], "truncated": False}

    nodes: dict[str, dict[str, Any]] = {entity_id: dict(root, distance=0)}
    links: dict[tuple[str, str, str], dict[str, str]] = {}
    queue: deque[tuple[str, int]] = deque([(entity_id, 0)])
    truncated = False

    while queue:
        current, depth = queue.popleft()
        if depth >= max(0, hops):
            continue
        for edge in store.edges_of(current):
            other = edge["target"] if edge["source"] == current else edge["source"]
            if other not in nodes:
                if len(nodes) >= MAX_NODES:
                    truncated = True
                    continue
                found = store.node_by_key(other)
                if found is None:
                    continue
                nodes[other] = dict(found, distance=depth + 1)
                queue.append((other, depth + 1))
            links[(edge["source"], edge["target"], edge["label"])] = edge

    return {
        "root": entity_id,
        "found": True,
        "hops": hops,
        "nodes": list(nodes.values()),
        "links": list(links.values()),
        "truncated": truncated,
    }


def overview(store: Any, limit: int = MAX_NODES) -> dict[str, Any]:
    """The whole seed graph, for the grounding panel's default view.

    Built from the same primitives as bfs() so the two views cannot disagree.
    The policy subgraph is disconnected from the entity subgraph - that is real
    structure, not a bug, and the visualisation should show it.
    """
    from app.graph.schema import NODES

    nodes: list[dict[str, Any]] = []
    links: dict[tuple[str, str, str], dict[str, str]] = {}
    truncated = False

    for spec in NODES:
        for key in store.keys(spec.label):
            if len(nodes) >= limit:
                truncated = True
                break
            found = store.node_by_key(key)
            if found:
                nodes.append(dict(found, distance=0))

    present = {n["id"] for n in nodes}
    for node_id in present:
        for edge in store.edges_of(node_id):
            if edge["source"] in present and edge["target"] in present:
                links[(edge["source"], edge["target"], edge["label"])] = edge

    return {"root": None, "found": bool(nodes), "hops": None, "nodes": nodes,
            "links": list(links.values()), "truncated": truncated}
