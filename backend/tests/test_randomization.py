"""Property-tests af randomisering (spec §16)."""
from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.randomization import (
    Item,
    block_permutations,
    build_plan,
    gap_feasible,
    min_distance,
)

PERSP = ["self", "team", "frame", "belong"]


def sample_items(domains=10, per_domain=4):
    items = []
    for p in PERSP:
        for d in range(domains):
            for i in range(per_domain):
                items.append(Item(f"{p}_{d}_{i}", p, f"D{d}"))
    return items


@settings(max_examples=150, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**63 - 1))
def test_sample_structure_all_rules(seed):
    items = sample_items()
    plan = build_plan(items, PERSP, "belong", {}, seed)
    ids = [i.question_id for i in plan.order]
    # alle items præcis én gang
    assert sorted(ids) == sorted(i.question_id for i in items)
    # belong altid sidst og blokke er sammenhængende
    assert plan.block_order[-1] == "belong"
    persp_seq = [i.perspective for i in plan.order]
    assert persp_seq[-40:] == ["belong"] * 40
    for b, p in enumerate(plan.block_order):
        assert set(persp_seq[b * 40:(b + 1) * 40]) == {p}
    # gap-regel er matematisk mulig her og skal derfor være opfyldt – også hen over blokgrænser
    assert plan.meta["gapRuleSatisfied"] is True
    assert min_distance([i.domain for i in plan.order]) >= 3


@settings(max_examples=200, deadline=None)
@given(
    counts=st.lists(st.integers(min_value=1, max_value=6), min_size=1, max_size=8),
    seed=st.integers(min_value=0, max_value=2**32),
)
def test_arbitrary_structure_invariants(counts, seed):
    items = []
    for p in PERSP:
        for d, c in enumerate(counts):
            for i in range(c):
                items.append(Item(f"{p}{d}{i}", p, f"D{d}"))
    plan = build_plan(items, PERSP, "belong", {}, seed)
    assert Counter(i.question_id for i in plan.order) == Counter(i.question_id for i in items)
    assert plan.block_order[-1] == "belong"
    if plan.meta["gapRuleSatisfied"]:
        md = min_distance([i.domain for i in plan.order])
        assert md is None or md >= 3
    # når hver blok har rigelig slack (også mod forrige bloks hale), skal reglen opfyldes
    c = Counter({f"D{d}": n for d, n in enumerate(counts)})
    n = sum(counts)
    if gap_feasible(c, n, 3) and (max(counts) - 1) * 3 + sum(1 for x in counts if x == max(counts)) + 2 <= n:
        assert plan.meta["gapRuleSatisfied"], (counts, seed)


def test_impossible_gap_is_reported_not_crashing():
    items = [Item(f"{p}{i}", p, "D0") for p in PERSP for i in range(3)]
    plan = build_plan(items, PERSP, "belong", {}, 1)
    assert plan.meta["gapRuleSatisfied"] is False
    assert len(plan.order) == 12


def test_counterbalancing_is_exact():
    items = sample_items(domains=3, per_domain=2)
    usage: dict = {}
    perms = block_permutations(PERSP, "belong")
    assert len(perms) == 6
    for k in range(60):
        plan = build_plan(items, PERSP, "belong", usage, seed=k * 7919)
        key = tuple(plan.block_order)
        usage[key] = usage.get(key, 0) + 1
    assert set(usage) == set(perms)
    assert set(usage.values()) == {10}


def test_deterministic_for_same_seed_and_usage():
    items = sample_items()
    a = build_plan(items, PERSP, "belong", {}, 42)
    b = build_plan(items, PERSP, "belong", {}, 42)
    assert [i.question_id for i in a.order] == [i.question_id for i in b.order]
    c = build_plan(items, PERSP, "belong", {}, 43)
    assert [i.question_id for i in a.order] != [i.question_id for i in c.order]


def test_gap_feasibility_condition():
    assert gap_feasible(Counter({"A": 4, "B": 4, "C": 4}), 12, 3)
    assert not gap_feasible(Counter({"A": 4, "B": 1}), 5, 3)
