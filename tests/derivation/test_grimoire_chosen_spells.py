"""GRIMOIRE deriver — consuming the generator's chosen spells (F05-T82).

The migrated choice grammar records the model's spell picks in ``choices["spells"]``
(``{"cantrips": [id, ...], "spells": [id, ...]}``). These tests pin that the GRIMOIRE deriver folds
those picks into the spellbook — placed on the matching CLASS source as chosen cantrips / prepared
spells, capped at the DB per-source budgets — AND that the gold / ``migrate`` path (no picks
supplied) is untouched, so the deterministic re-derivation is byte-for-byte unchanged.

All ids are synthetic placeholders from the shared rules-DB fixture (``class-a``, ``sp1`` …), never
real game vocabulary. In the fixture, class-a is a full caster: at level 3 it knows 2 cantrips and
prepares 3 spells. sp1/sp2 are cantrips and sp3 a leveled spell, all on class-a's list; sp5 is on
class-b's list only (off class-a's).
"""
from app.derivation.document import derive_document
from app.derivation.grimoire import derive_grimoire, derive_sources, derive_spells
from app.generation.choices import generate_choices, parse_request
from validator.validate_grimoire import validate_grimoire


def _caster_core(**overrides):
    """A minimal core-sheet:1 for a single-class level-3 class-a caster (full caster)."""
    core = {
        "schema_version": 1,
        "character_id": "test-cs",
        "character_name": "Test",
        "identity": {
            "name": "Test", "species": "Species A", "lineage": None,
            "classes": [{"class": "Class A", "level": 3, "subclass": None,
                         "subclass_detail": None, "class_detail": None}],
            "total_level": 3, "background": "Background A",
        },
        "abilities": {},
        "proficiency_bonus": 2,
        "feats": [],
        "features": [],
    }
    core.update(overrides)
    return core


# --------------------------------------------------------------------------- gold path unchanged

def test_no_chosen_spells_is_noop(access):
    """Absent chosen picks (the gold / migrate path), the deriver is identical whether the optional
    argument is omitted or passed as None — and no chosen-bucket spells are invented."""
    core = _caster_core()
    without_arg = derive_grimoire(core, None, access)
    with_none = derive_grimoire(core, None, access, chosen_spells=None)
    assert without_arg == with_none

    buckets = {s["bucket"] for s in without_arg["spells"]}
    assert "cantrip" not in buckets
    assert "prepared" not in buckets


def test_empty_chosen_spells_adds_nothing(access):
    """An empty picks object (a legal 'chose nothing' shape) leaves the spellbook deterministic."""
    core = _caster_core()
    baseline = derive_grimoire(core, None, access)
    empty = derive_grimoire(core, None, access, chosen_spells={"cantrips": [], "spells": []})
    assert empty["spells"] == baseline["spells"]


# --------------------------------------------------------------------------- picks folded in

def test_chosen_spells_placed_on_class_source(access):
    core = _caster_core()
    grimoire = derive_grimoire(core, None, access,
                               chosen_spells={"cantrips": ["sp1", "sp2"], "spells": ["sp3"]})

    src = "class:class-a"
    held = {(s["name"], s["bucket"], s["source"]) for s in grimoire["spells"]}
    assert ("Sp1", "cantrip", src) in held
    assert ("Sp2", "cantrip", src) in held
    assert ("Sp3", "prepared", src) in held

    cantrips = [s for s in grimoire["spells"] if s["source"] == src and s["bucket"] == "cantrip"]
    prepared = [s for s in grimoire["spells"] if s["source"] == src and s["bucket"] == "prepared"]
    assert len(cantrips) == 2      # cantrips_known = 2 at level 3
    assert len(prepared) == 1
    assert all(s["recovery"] == "at_will" for s in cantrips)
    assert all(s["recovery"] == "spell_slot" for s in prepared)


def test_chosen_grimoire_passes_validator(access):
    core = _caster_core()
    grimoire = derive_grimoire(core, None, access,
                               chosen_spells={"cantrips": ["sp1", "sp2"], "spells": ["sp3"]})
    report = validate_grimoire(core, grimoire, access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]


def test_chosen_cantrips_capped_at_budget(access):
    """A source that knows only one cantrip receives only one chosen cantrip, even when the model
    supplies two on-list picks — the placement honours the DB budget."""
    core = _caster_core()
    sources = {"class:class-a": {"kind": "class", "ability": "a1", "cantrips_known": 1,
                                 "prepared_limit": 3, "ability_mode": None}}
    spells = derive_spells(core, None, sources, access,
                           chosen_spells={"cantrips": ["sp1", "sp2"], "spells": []})
    cantrips = [s for s in spells if s["source"] == "class:class-a" and s["bucket"] == "cantrip"]
    assert len(cantrips) == 1


def test_off_list_chosen_spell_not_placed(access):
    """sp5 is on class-b's list only. A class-a caster cannot hold it as a chosen prepared spell, so
    it is dropped (never emitted off-list, which the validator would reject)."""
    core = _caster_core()
    sources = derive_sources(core, access)
    spells = derive_spells(core, None, sources, access,
                           chosen_spells={"cantrips": [], "spells": ["sp5"]})
    assert not any(s["name"] == "Sp5" for s in spells)


# --------------------------------------------------------------------------- T84 list-widening

def test_list_widened_chosen_spell_is_placed(access):
    """A pick legal ONLY through a list-widening grant reaches the GRIMOIRE. class-a's widening
    grant (gained at level 10) adds class-b's list, so at level 10 the class-b-only sp5 becomes a
    placeable class-a prepared pick — the deriver's gate now matches the validator's admission."""
    core = _caster_core()
    core["identity"]["classes"][0]["level"] = 10
    core["identity"]["total_level"] = 10
    sources = derive_sources(core, access)
    spells = derive_spells(core, None, sources, access,
                           chosen_spells={"cantrips": [], "spells": ["sp5"]})
    placed = [s for s in spells
              if s["name"] == "Sp5" and s["source"] == "class:class-a" and s["bucket"] == "prepared"]
    assert len(placed) == 1


def test_list_widening_not_applied_below_grant_level(access):
    """Below the widening grant's level the widened list is NOT admitted: sp5 (class-b only) is
    dropped for a level-3 class-a caster, matching the validator's level-gated widening."""
    core = _caster_core()  # level 3 < widening level 10
    sources = derive_sources(core, access)
    spells = derive_spells(core, None, sources, access,
                           chosen_spells={"cantrips": [], "spells": ["sp5"]})
    assert not any(s["name"] == "Sp5" for s in spells)


# --------------------------------------------------------------------------- T93 subclass free cantrip

def _class_c_core(**overrides):
    """A minimal core-sheet:1 for a single-class level-3 class-c caster (isolated full caster)."""
    core = _caster_core()
    core["identity"]["classes"] = [{"class": "Class C", "level": 3, "subclass": None,
                                    "subclass_detail": None, "class_detail": None}]
    core.update(overrides)
    return core


def test_subclass_free_cantrip_reserves_slot(access):
    """A subclass free bonus cantrip attributed to the class source reserves a cantrip slot, so
    chosen cantrips are clamped to the remaining budget: granted (Spf) + chosen never exceeds the
    class's cantrips_known (2 at level 3). The result validates legal."""
    core = _class_c_core()
    core["identity"]["classes"][0]["subclass"] = "Sub Free Cantrip"
    grimoire = derive_grimoire(core, None, access,
                               chosen_spells={"cantrips": ["sp1", "sp2"], "spells": []})
    src = "class:class-c"
    cantrips = [s for s in grimoire["spells"] if s["source"] == src and s["bucket"] == "cantrip"]
    assert len(cantrips) == 2                                   # capped at cantrips_known, not 3
    assert any(s["name"] == "Spf" for s in cantrips)           # the granted free cantrip is kept
    report = validate_grimoire(core, grimoire, access)
    assert report["legal"] is True, report["violations"]


# --------------------------------------------------------------------------- T85 same-bucket grant

def test_same_bucket_grant_reduces_chosen_budget(access):
    """A same-bucket prepared grant on the class source reduces the chosen prepared budget: granted
    (Sp3) + chosen never exceeds prepared_limit (3 at level 3), even when the model offers three
    on-list picks. The result validates legal."""
    core = _class_c_core()
    core["identity"]["classes"][0]["subclass"] = "Sub Prep Grant"
    grimoire = derive_grimoire(core, None, access,
                               chosen_spells={"cantrips": [], "spells": ["sp7", "sp8", "sp9"]})
    src = "class:class-c"
    prepared = [s for s in grimoire["spells"] if s["source"] == src and s["bucket"] == "prepared"]
    assert len(prepared) == 3                                  # granted Sp3 + 2 chosen, capped at 3
    assert any(s["name"] == "Sp3" for s in prepared)           # the granted prepared spell is kept
    report = validate_grimoire(core, grimoire, access)
    assert report["legal"] is True, report["violations"]


# --------------------------------------------------------------------------- T86 pact spells-known

def _pact_core(**overrides):
    """A minimal core-sheet:1 for a single-class level-2 class-p pact caster."""
    core = {
        "schema_version": 1, "character_id": "test-p", "character_name": "Pact",
        "identity": {
            "name": "Pact", "species": "Species A", "lineage": None,
            "classes": [{"class": "Class P", "level": 2, "subclass": None,
                         "subclass_detail": None, "class_detail": None}],
            "total_level": 2, "background": "Background A",
        },
        "abilities": {}, "proficiency_bonus": 2, "feats": [], "features": [],
    }
    core.update(overrides)
    return core


def test_pact_chosen_capped_at_spells_known(access):
    """The pact caster's chosen leveled picks are capped at the DB spells-known count (3 at level 2),
    not left uncapped: four on-list picks yield exactly three placed prepared spells."""
    core = _pact_core()
    grimoire = derive_grimoire(core, None, access,
                               chosen_spells={"cantrips": [], "spells": ["sp3", "sp7", "sp8", "sp9"]})
    src = "class:class-p"
    prepared = [s for s in grimoire["spells"] if s["source"] == src and s["bucket"] == "prepared"]
    assert len(prepared) == 3


# --------------------------------------------------------------------------- end-to-end

def test_generated_caster_grimoire_reflects_picks(gen_access, access):
    """generate_choices (stubbed pick) -> derive_document: a generated caster's GRIMOIRE contains its
    chosen spells with the right counts AND passes /validate-grimoire legal + complete."""
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-t82", "character_name": "Gamma"})

    def pick(_prompt, schema):
        if "name" in (schema.get("required") or []):
            return {"name": "Gamma", "skills": ["sk1", "sk2"],
                    "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
                    "spells": {"cantrips": ["sp1", "sp2"], "spells": ["sp3"]}}
        return {"equipment_class": "sa-a"}

    choices = generate_choices(gen_access, spec, pick=pick)
    assert choices["spells"] == {"cantrips": ["sp1", "sp2"], "spells": ["sp3"]}

    document = derive_document(choices, gen_access)
    assert "grimoire" in document

    held = {(s["name"], s["bucket"]) for s in document["grimoire"]["spells"]}
    assert ("Sp1", "cantrip") in held
    assert ("Sp2", "cantrip") in held
    assert ("Sp3", "prepared") in held

    report = validate_grimoire(document["core"], document["grimoire"], access)
    assert report["legal"] is True, report["violations"]
    assert report["complete"] is True, report["violations"]
