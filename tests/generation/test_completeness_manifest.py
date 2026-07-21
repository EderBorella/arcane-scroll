"""F07-T11 / T13 — the completeness manifest builder + its exhaustiveness proof.

T11 pins the generation-side manifest: from the choice grammar's count/gating helpers plus a build's
``choices``, emit the typed ``manifest[]`` of the completeness report — one entry per unfilled /
over-filled choice, FLAG-ONLY (a generic resource kind + counts, never an options pool or a
source-specific name) and VALIDATOR-INDEPENDENT (never reads the validator's output).

T13 is the exhaustiveness harness: it enumerates the grammar's choice surface and asserts every
grammar-known choice is either COVERED by a manifest entry (for an unfilled build) or explicitly
EXCLUDED with a logged reason — failing loudly if a NEW grammar field appears without a decision.

Synthetic ids only, from the shared rules DB fixture.
"""
import pytest

from engine.choices import build_manifest, manifest, parse_request
from engine.choices import grammar, options


# ------------------------------------------------------------------ small local helpers

def _spec(gen_access, classes, **kw):
    payload = {"species": "species-a", "background": "bg-a", "classes": classes}
    payload.update(kw)
    return parse_request(gen_access, payload)


def _empty_class_choices(classes):
    """A choices object that has picked NOTHING — only the class entries (with no subclass), so every
    grammar choice shows up as an unfilled gap."""
    return {"classes": [{"class": cid, "level": lv, "subclass": None} for cid, lv, _s in classes]}


# --------------------------------------------------------------------------- T11: entry shape

_CONTRACT_RESOURCES = {"subclass", "feat", "spell", "cantrip", "skill", "expertise", "tool",
                       "language", "focus_item", "ability_increase"}
_CONTRACT_SECTIONS = {"core", "grimoire", "inventory", "companion"}
_CONTRACT_TYPES = {"missing", "too_few", "too_many"}
_ENTRY_KEYS = {"choice_key", "section", "path", "resource", "type", "count", "status", "description"}


def test_manifest_entries_match_the_contract_shape(gen_access):
    spec = _spec(gen_access, [{"class": "class-a", "level": 19}])
    resolved = [("class-a", 19, "sub-a")]
    m = build_manifest(gen_access, spec, resolved, _empty_class_choices(resolved))
    assert m, "an empty build must produce gaps"
    for e in m:
        assert set(e) == _ENTRY_KEYS
        assert e["section"] in _CONTRACT_SECTIONS
        assert e["resource"] in _CONTRACT_RESOURCES
        assert e["type"] in _CONTRACT_TYPES
        assert e["status"] in {"required", "optional"}
        assert "filled" in e["count"]


def test_manifest_is_flag_only_no_option_pool(gen_access):
    # An entry names the generic resource kind + counts; it must NOT carry any list of candidate
    # options (a pool) — only the fixed count keys are allowed under `count`.
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    resolved = [("class-tl", 2, None)]
    m = build_manifest(gen_access, spec, resolved, _empty_class_choices(resolved))
    for e in m:
        assert set(e["count"]) <= {"required", "min", "max", "filled"}
        # no entry field is a list (an options pool would be one)
        assert not any(isinstance(val, list) for val in e.values())


def test_choice_key_is_deterministic_and_readable(gen_access):
    spec = _spec(gen_access, [{"class": "class-a", "level": 19}])
    resolved = [("class-a", 19, "sub-a")]
    choices = _empty_class_choices(resolved)
    keys_a = [e["choice_key"] for e in build_manifest(gen_access, spec, resolved, choices)]
    keys_b = [e["choice_key"] for e in build_manifest(gen_access, spec, resolved, choices)]
    assert keys_a == keys_b                                   # stable across stateless calls
    assert len(keys_a) == len(set(keys_a))                    # unique per field
    assert "core.classes.0.subclass" in keys_a                # readable section.path
    for k in keys_a:
        assert k.split(".")[0] in _CONTRACT_SECTIONS


def test_filled_choices_produce_no_entry(gen_access):
    # A build whose skill choice is exactly filled yields no skill gap.
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}])
    resolved = [("class-a", 3, "sub-a")]
    choices = {"classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
               "skills": ["sk1", "sk2"]}
    keys = [e["choice_key"] for e in build_manifest(gen_access, spec, resolved, choices)]
    assert "core.skills" not in keys
    assert "core.classes.0.subclass" not in keys              # subclass chosen -> no gap


def test_over_fill_is_typed_too_many(gen_access):
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}])
    resolved = [("class-a", 3, "sub-a")]
    choices = {"classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
               "skills": ["sk1", "sk2", "sk3"]}     # 3 > the pool choice of 2
    skill = next(e for e in build_manifest(gen_access, spec, resolved, choices)
                 if e["choice_key"] == "core.skills")
    assert skill["type"] == "too_many"
    assert skill["count"] == {"max": 2, "filled": 3}


def test_awaiting_choices_reflects_required_entries(gen_access):
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}])
    resolved = [("class-a", 3, "sub-a")]
    assert manifest.awaiting_choices(
        build_manifest(gen_access, spec, resolved, _empty_class_choices(resolved))) is True
    # a fully satisfied build (no required gap) is not awaiting choices
    full = {"classes": [{"class": "class-a", "level": 3, "subclass": "sub-a"}],
            "skills": ["sk1", "sk2"], "expertise": ["sk1"],
            "background_increase": {"a1": 2, "a2": 1},
            "spells": {"cantrips": ["sp1"], "spells": ["sp3"]}}
    assert manifest.awaiting_choices(build_manifest(gen_access, spec, resolved, full)) is False


def test_manifest_ordered_by_section(gen_access):
    spec = _spec(gen_access, [{"class": "class-a", "level": 19}])
    resolved = [("class-a", 19, "sub-a")]
    m = build_manifest(gen_access, spec, resolved, _empty_class_choices(resolved))
    order = [manifest._SECTION_ORDER[e["section"]] for e in m]
    assert order == sorted(order)


def test_equipment_choice_items_are_flagged(gen_access):
    spec = _spec(gen_access, [{"class": "class-tl", "level": 2}])
    resolved = [("class-tl", 2, None)]
    choices = _empty_class_choices(resolved)
    choices["equipment_choices"] = [
        {"kind": "tool_category", "tool_category": "tc-music"},
        {"kind": "focus", "focus_type": "ft-a"},
        {"kind": "proficiency_choice"},
    ]
    inv = [e for e in build_manifest(gen_access, spec, resolved, choices) if e["section"] == "inventory"]
    assert [e["resource"] for e in inv] == ["tool", "focus_item", "tool"]
    assert [e["choice_key"] for e in inv] == [
        "inventory.equipment_choices.0", "inventory.equipment_choices.1", "inventory.equipment_choices.2"]


def test_manifest_module_is_validator_independent():
    # The builder must never import the validator (that would let it read the validator's output
    # instead of re-deriving the choice surface independently).
    src = open(manifest.__file__, encoding="utf-8").read()
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "validator" not in stripped, f"manifest must not import the validator: {stripped!r}"


# =========================================================================== T13: exhaustiveness

# Representative builds whose UNION of grammar fields exercises the whole choice surface: a caster with
# a lineage species + ability/boon slots; a tool/language/expertise + variant-axis build; a
# weapon-mastery build. Together they emit every field the grammar can offer.
_SURFACE_BUILDS = [
    ("species-l", [{"class": "class-a", "level": 19}], [("class-a", 19, "sub-a")]),
    ("species-v", [{"class": "class-tl", "level": 2}], [("class-tl", 2, None)]),
    ("species-a", [{"class": "class-wm", "level": 1}], [("class-wm", 1, None)]),
]


def _grammar_fields(gen_access):
    """Every field the pass-1 + equipment grammar can emit across the representative builds."""
    fields: set[str] = set()
    for species, classes, resolved in _SURFACE_BUILDS:
        spec = parse_request(gen_access, {"species": species, "background": "bg-a", "classes": classes})
        feat_slots = options.ability_feat_slot_count(gen_access, resolved)
        boon_slots = options.boon_slot_count(gen_access, resolved)
        s1 = grammar.build_pass1_grammar(gen_access, spec, resolved,
                                         feat_slots=feat_slots, boon_slots=boon_slots)
        s2 = grammar.build_equipment_grammar(gen_access, spec, resolved)
        fields |= set(s1["properties"]) | set(s2["properties"])
    return fields


def test_every_grammar_choice_is_covered_or_explicitly_excluded(gen_access):
    # The exhaustiveness proof: every field the grammar knows must be classified — COVERED (a manifest
    # entry) or EXCLUDED (a logged reason). A NEW grammar field lands in neither set and fails here,
    # loudly, rather than being silently dropped from the manifest.
    classified = manifest.COVERED_GRAMMAR_FIELDS | set(manifest.EXCLUDED_GRAMMAR_FIELDS)
    ungoverned = _grammar_fields(gen_access) - classified
    assert not ungoverned, (
        f"grammar choices with no manifest decision: {sorted(ungoverned)} — add each to "
        "COVERED_GRAMMAR_FIELDS or EXCLUDED_GRAMMAR_FIELDS in the manifest builder")


def test_every_exclusion_carries_a_reason():
    # No silent caps: each deliberate exclusion logs WHY it is out of the manifest.
    for field, reason in manifest.EXCLUDED_GRAMMAR_FIELDS.items():
        assert isinstance(reason, str) and reason.strip(), f"{field} excluded without a reason"


def test_covered_fields_yield_a_manifest_entry_when_unfilled(gen_access):
    # For each representative build, every COVERED grammar field the build actually OFFERS must show
    # up as a manifest entry when the build is empty (nothing silently dropped).
    field_to_key_prefix = {
        "background_increase": "core.abilities.background_increase",
        "skills": "core.skills",
        "expertise": "core.skills.expertise",
        "languages": "core.languages",
        "tools": "core.proficiencies.tools",
        "feats": "core.feats",
        "boons": "core.feats.boons",
        "spells": ("grimoire.cantrips", "grimoire.spells"),
    }
    for species, classes, resolved in _SURFACE_BUILDS:
        spec = parse_request(gen_access, {"species": species, "background": "bg-a", "classes": classes})
        feat_slots = options.ability_feat_slot_count(gen_access, resolved)
        boon_slots = options.boon_slot_count(gen_access, resolved)
        offered = set(grammar.build_pass1_grammar(
            gen_access, spec, resolved, feat_slots=feat_slots, boon_slots=boon_slots)["properties"])
        keys = {e["choice_key"] for e in
                build_manifest(gen_access, spec, resolved, _empty_class_choices(resolved))}
        for field in offered & manifest.COVERED_GRAMMAR_FIELDS:
            expected = field_to_key_prefix[field]
            expected = (expected,) if isinstance(expected, str) else expected
            assert any(k in keys for k in expected), (
                f"{species}/{classes[0]['class']}: covered grammar field {field!r} produced no "
                f"manifest entry (expected one of {expected})")


def test_subclass_gap_is_covered_even_though_not_a_grammar_field(gen_access):
    # subclass is code-resolved (not a model-facing grammar field) but is still a required choice the
    # manifest must surface — the contract's canonical example (core.classes.0.subclass).
    spec = _spec(gen_access, [{"class": "class-a", "level": 3}])
    resolved = [("class-a", 3, "sub-a")]
    keys = {e["choice_key"] for e in
            build_manifest(gen_access, spec, resolved, _empty_class_choices(resolved))}
    assert "core.classes.0.subclass" in keys
    assert "subclass" in manifest.NON_GRAMMAR_COVERED
