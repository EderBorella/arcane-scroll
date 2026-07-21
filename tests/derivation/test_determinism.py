"""Determinism guardrails for the MODIFIER derivation (F05-T52).

These lock in the order-stability fixes so a from-scratch regen of the corpus
stays byte-reproducible. They assert ORDER only — no derived value is checked
against the generator, and no value is expected to change.

The cross-process test is the load-bearing one: same-process regen shares a
hash seed, so it cannot catch hash-seed-dependent set-iteration order. Spawning
subprocesses under different PYTHONHASHSEED values is what actually guards the
class of bug (an unsorted set feeding a dict/array's emit order).
"""
import json
import os
import subprocess
import sys

from engine.derivation.modifier import ActiveEffects, derive_defenses
from engine.derivation.modifier_orchestrator import _deep_merge, derive_modifier
from validator.checks.movement import _resolve_speeds

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _core(**overrides):
    sheet = {
        "schema_version": 1,
        "character_id": "test-01",
        "character_name": "Test",
        "identity": {
            "name": "Test", "species": "Species A",
            "size": "medium", "creature_type": "Type A",
            "classes": [{"class": "Class A", "level": 3, "subclass": None}],
            "total_level": 3, "background": "Background A",
        },
        "abilities": {
            "a1": {"final": 14},
            "a2": {"final": 16},
            "a3": {"final": 12},
        },
        "proficiency_bonus": 2,
        "saving_throws": {
            "a1": {"proficient": True},
            "a2": {"proficient": False},
            "a3": {"proficient": True},
        },
        "skills": {
            "sk1": {"ability": "a1", "proficient": True, "expertise": False},
            "sk2": {"ability": "a2", "proficient": False, "expertise": False},
        },
        "permanent_senses": {},
        "permanent_speed": {"walk": 30},
        "permanent_defenses": {
            "resistances": [], "immunities": [], "vulnerabilities": [],
            "condition_immunities": [], "save_advantages": [], "condition_advantages": [],
        },
        "proficiencies": {"armor": [], "weapons": [], "tools": []},
        "weapon_masteries": [],
        "features": [{"name": "Feat A", "source": "class-a"}],
        "feats": [{"name": "feat-gen", "source": "bg-a"}],
        "resource_budgets": {},
        "hit_points": {"max": 22},
        "hit_dice": {"d8": {"max": 3}},
        "languages": [], "flavour": None,
    }
    sheet.update(overrides)
    return sheet


# ── (a) set-derived defence arrays are order-stable (== sorted form) ───────────


def test_derive_defenses_arrays_are_sorted(access):
    """A core with populated permanent_defenses merged with state effects emits
    each set-derived array in sorted order, regardless of set iteration order.
    Values are opaque placeholder ids — derive_defenses does not resolve them."""
    core = _core(permanent_defenses={
        "resistances": ["dmg-p", "dmg-f", "dmg-a"],
        "immunities": ["dmg-t", "dmg-c"],
        "vulnerabilities": ["dmg-r", "dmg-n"],
        "condition_immunities": ["cond-f", "cond-c"],
        "save_advantages": ["a3", "a1"],
        "condition_advantages": [],
    })
    effects = ActiveEffects()
    effects.resistances.update({"dmg-l", "dmg-b"})
    effects.immunities.add("dmg-y")
    effects.vulnerabilities.add("dmg-o")
    effects.condition_immunities.add("cond-s")
    effects.save_advantages.add("a2")

    defenses = derive_defenses(core, effects, access)
    for field in ("resistances", "immunities", "vulnerabilities",
                  "condition_immunities", "save_advantages"):
        assert defenses[field] == sorted(defenses[field]), f"{field} not order-stable"


# ── (b) deep-merge preserves base key order ────────────────────────────────────


def test_deep_merge_preserves_base_key_order():
    """Keys shared with (or unique to) base keep base's insertion order; existing-
    only keys follow in existing's order — never a set-union's arbitrary order."""
    base = {"z": 1, "m": 2, "a": 3, "k": 4}
    existing = {"a": 30, "k": 40, "m": 20, "z": 10, "extra": 99}
    merged = _deep_merge(base, existing)
    assert list(merged.keys()) == ["z", "m", "a", "k", "extra"]


# ── (c) full modifier derivation is byte-identical across runs ─────────────────


def test_derive_modifier_byte_identical(access):
    core = _core(permanent_defenses={
        "resistances": ["dmg-p", "dmg-f", "dmg-a"],
        "immunities": ["dmg-t", "dmg-c"],
        "vulnerabilities": [], "condition_immunities": ["cond-f", "cond-c"],
        "save_advantages": ["a3", "a1"], "condition_advantages": [],
    })
    first, _ = derive_modifier(core, None, None, None, "full", access)
    second, _ = derive_modifier(core, None, None, None, "full", access)
    assert json.dumps(first) == json.dumps(second)


# ── (d) multi-mode equals_walk speed order is stable ───────────────────────────


def _walk_equal_rows(*modes):
    """Synthetic grant rows: each mode mirrors the walk speed (equals_walk)."""
    return [{"movement_mode_id": m, "sets_total": 0, "feet": None,
             "additive": 0, "equals_walk": 1} for m in modes]


def test_resolve_speeds_multi_equals_walk_key_order():
    """Two-or-more walk-equal modes must land in a stable (sorted) key order —
    the emit order previously followed a raw set's hash-seed-dependent iteration."""
    rows = _walk_equal_rows("swim", "climb")
    speeds = _resolve_speeds(rows, 30, [])
    # walk is seeded first; the equals_walk modes follow in sorted order.
    assert list(speeds.keys()) == ["walk", "climb", "swim"]


# ── (e) cross-process byte-identity under differing hash seeds ─────────────────

# Worker: serialize a speed dict with several walk-equal modes. Its key order is
# driven by the equals_walk set's iteration, so without a stable sort the JSON
# bytes vary with PYTHONHASHSEED. Run under different seeds and diff the output.
_WORKER = (
    "import json;"
    "from validator.checks.movement import _resolve_speeds;"
    "rows=[{'movement_mode_id':m,'sets_total':0,'feet':None,'additive':0,"
    "'equals_walk':1} for m in ('climb','swim','fly','burrow','crawl','glide')];"
    "print(json.dumps(_resolve_speeds(rows,30,[])))"
)


def _run_under_seed(seed: str) -> str:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    env["PYTHONPATH"] = _REPO + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.run(
        [sys.executable, "-c", _WORKER],
        cwd=_REPO, env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout


def test_speed_serialization_byte_identical_across_hash_seeds():
    """The real guard: a set-iteration ordering bug only shows up across processes
    with different hash seeds. Emit order must be byte-identical for every seed."""
    outputs = {seed: _run_under_seed(seed) for seed in ("0", "1", "42", "1000")}
    distinct = set(outputs.values())
    assert len(distinct) == 1, f"hash-seed-dependent output: {outputs}"
