"""Randomisering af præsentationsrækkefølge.

Regler (spec §2):
* Fire blokke (én pr. perspektiv). `fixed_last` (belong) altid sidst.
* Rækkefølgen af de øvrige blokke modbalanceres: den permutation, der er
  brugt færrest gange i (surveyversion, afdeling), vælges; uafgjort brydes
  deterministisk ud fra seed.
* Items randomiseres inden for blok.
* To items fra samme domæne skal have mindst `min_gap` andre items imellem
  (afstand >= min_gap + 1), hvis det er matematisk muligt – også hen over
  blokgrænser. Ellers bedst mulige (maksimal mindste afstand).
* Seed og faktisk rækkefølge gemmes; genoptagelse bruger den gemte rækkefølge.
"""
from __future__ import annotations

import itertools
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

MIN_GAP = 2  # mindst to andre items imellem


@dataclass(frozen=True)
class Item:
    question_id: str
    perspective: str
    domain: str


@dataclass
class Plan:
    seed: int
    block_order: list[str]
    order: list[Item]
    meta: dict = field(default_factory=dict)


def block_permutations(perspectives: Sequence[str], fixed_last: str | None) -> list[tuple[str, ...]]:
    movable = [p for p in perspectives if p != fixed_last]
    perms = [tuple(p) for p in itertools.permutations(movable)]
    if fixed_last and fixed_last in perspectives:
        perms = [p + (fixed_last,) for p in perms]
    return perms


def choose_block_order(
    perms: list[tuple[str, ...]], usage: dict[tuple[str, ...], int], rng: random.Random
) -> tuple[str, ...]:
    least = min(usage.get(p, 0) for p in perms)
    candidates = [p for p in perms if usage.get(p, 0) == least]
    return candidates[rng.randrange(len(candidates))]


def gap_feasible(domain_counts: Counter, n: int, distance: int) -> bool:
    """Nødvendig og tilstrækkelig betingelse for at placere n elementer med
    mindsteafstand `distance` mellem ens elementer: (cmax-1)*distance + #max <= n."""
    if not domain_counts:
        return True
    cmax = max(domain_counts.values())
    nmax = sum(1 for c in domain_counts.values() if c == cmax)
    return (cmax - 1) * distance + nmax <= n


def min_distance(seq: Sequence[str]) -> int | None:
    last: dict[str, int] = {}
    best: int | None = None
    for i, d in enumerate(seq):
        if d in last:
            dist = i - last[d]
            best = dist if best is None else min(best, dist)
        last[d] = i
    return best


def _arrange_block(
    items: list[Item], rng: random.Random, distance: int, tail: list[str], greedy: bool = False
) -> list[Item] | None:
    """Randomiseret grådig konstruktion: vælg blandt tilladte domæner, vægtet
    efter resterende antal (det sikrer gennemførlighed når betingelsen holder).
    `tail` = domæner for de seneste items i forrige blok (grænsereglen)."""
    pools: dict[str, list[Item]] = {}
    for it in items:
        pools.setdefault(it.domain, []).append(it)
    for pool in pools.values():
        rng.shuffle(pool)
    recent = list(tail[-(distance - 1) :]) if distance > 1 else []
    out: list[Item] = []
    remaining_total = len(items)
    while remaining_total:
        blocked = set(recent[-(distance - 1) :]) if distance > 1 else set()
        allowed = [d for d, p in pools.items() if p and d not in blocked]
        if not allowed:
            return None
        cmax = max(len(pools[d]) for d in allowed)
        # Domæner, der ellers ikke kan nå at blive placeret, SKAL vælges nu
        urgent = [d for d in allowed if (len(pools[d]) - 1) * distance + 1 >= remaining_total]
        if urgent:
            choice_pool = urgent
        elif greedy:
            choice_pool = [d for d in allowed if len(pools[d]) == cmax]
        else:
            # vægtet tilfældigt valg; tunge domæner foretrækkes lidt
            choice_pool = [d for d in allowed for _ in range(len(pools[d]))]
            if rng.random() < 0.35:
                choice_pool = [d for d in allowed if len(pools[d]) == cmax]
        d = choice_pool[rng.randrange(len(choice_pool))]
        out.append(pools[d].pop())
        recent.append(d)
        remaining_total -= 1
    return out


def _best_effort(items: list[Item], rng: random.Random, tail: list[str]) -> list[Item]:
    """Når reglen er umulig: maksimér mindste afstand via gentagne forsøg."""
    best: list[Item] | None = None
    best_score = -1
    for dist in range(MIN_GAP, 0, -1):
        for _ in range(200):
            cand = _arrange_block(items, rng, dist + 1, tail)
            if cand is not None:
                score = min_distance(tail + [i.domain for i in cand]) or 10**6
                if score > best_score:
                    best, best_score = cand, score
        if best is not None:
            return best
    shuffled = items[:]
    rng.shuffle(shuffled)
    return shuffled


def build_plan(
    items: Sequence[Item],
    perspectives: Sequence[str],
    fixed_last: str | None,
    usage: dict[tuple[str, ...], int],
    seed: int,
    attempts: int = 500,
) -> Plan:
    rng = random.Random(seed)
    perms = block_permutations(perspectives, fixed_last)
    block_order = list(choose_block_order(perms, usage, rng))
    distance = MIN_GAP + 1
    order: list[Item] = []
    gap_ok_all = True
    for p in block_order:
        block_items = [i for i in items if i.perspective == p]
        tail = [i.domain for i in order]
        counts = Counter(i.domain for i in block_items)
        arranged = None
        if gap_feasible(counts, len(block_items), distance):
            for k in range(attempts):
                # sidste forsøg: ren "flest-tilbage"-grådig (garanteret når betingelsen holder)
                arranged = _arrange_block(block_items, rng, distance, tail, greedy=k >= attempts - 50)
                if arranged is not None:
                    break
        if arranged is None:
            gap_ok_all = False
            arranged = _best_effort(block_items, rng, tail)
        order.extend(arranged)
    return Plan(
        seed=seed,
        block_order=block_order,
        order=order,
        meta={
            "algorithm": "counterbalanced-blocks+gap-greedy/v1",
            "minGap": MIN_GAP,
            "gapRuleSatisfied": gap_ok_all,
            "achievedMinDistance": min_distance([i.domain for i in order]),
            "fixedLast": fixed_last,
        },
    )
