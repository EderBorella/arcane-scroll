"""Migration tests for the DAL-grounded choice grammar (F05-T69, S13 Phase 4).

The grammar enumerates the choice space from the generator DAL (``access/generator`` over the
synthetic rules DB) and produces the ``choices`` structure the derivation pipeline consumes. These
tests pin the three migration guarantees:

* the choice space is DAL-sourced (skills/spells/feats/equipment enumerated from the DB, not a
  flat-file catalog);
* the choices are shaped for the loaded ruleset (``species`` not ``race``; ability boosts + origin feat from the
  background; no ``racial_bonus``/``race`` anywhere);
* grammar -> choices -> ``derive_document`` yields a full, validator-legal five-schema document, for
  a non-caster and a caster.

All ids are synthetic placeholders from the shared rules-DB fixture (``class-a``, ``species-a``,
``sub-ek`` ...), never real game vocabulary.
"""
import pytest

from app.derivation.document import derive_document
from app.generation.choices import assemble, grammar, options
from app.generation.choices import generate_choices, parse_request
from validator.validate_core import validate_core
from validator.validate_grimoire import validate_grimoire
from validator.validate_inventory import validate_inventory
from validator.validate_modifier import validate_modifier


# --------------------------------------------------------------------------- request parsing

def test_parse_request_validates_ids(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a", "character_name": "Alpha"})
    assert spec.species == "species-a"
    assert spec.classes == [("class-a", 3)]
    assert spec.subclasses == {"class-a": "sub-a"}
    assert spec.background == "bg-a"


@pytest.mark.parametrize("payload", [
    {"species": "nope", "classes": [{"class": "class-a", "level": 3}]},
    {"species": "species-a", "classes": [{"class": "nope", "level": 3}]},
    {"species": "species-a", "classes": [{"class": "class-a", "level": 99}]},
    {"species": "species-a", "classes": [{"class": "class-a", "level": 3}],
     "subclasses": {"class-a": "nope"}},
    {"species": "species-a", "classes": [{"class": "class-a", "level": 3}], "background": "nope"},
])
def test_parse_request_rejects_unknown(gen_access, payload):
    with pytest.raises(ValueError):
        parse_request(gen_access, payload)


# --------------------------------------------------------------------------- DAL-sourced options

def test_subclass_resolution_gated_by_unlock_level(gen_access):
    # class-a unlocks its subclass at level 3
    assert options.resolve_subclass(gen_access, "class-a", 2, "sub-a") is None
    assert options.resolve_subclass(gen_access, "class-a", 3, "sub-a") == "sub-a"


def test_base_ability_scores_cover_every_ability(gen_access):
    scores = options.base_ability_scores(gen_access, "class-a")
    # class-a's suggested standard array (DAL) supplies a1/a2/a3; the rest fall to the baseline.
    assert scores["a1"] == 15 and scores["a2"] == 14 and scores["a3"] == 13
    all_ids = {r["id"] for r in options.catalog.list_abilities(gen_access)}
    assert set(scores) == all_ids          # every ability carries a base score


def test_default_background_boost_is_two_one(gen_access):
    # bg-a's ability options (ordinal order) are a1, a2, a3
    assert options.default_background_boost(gen_access, "bg-a") == {"a1": 2, "a2": 1}


def test_skill_choice_from_class_pool(gen_access):
    n, pool = options.skill_choice(gen_access, "class-a")
    assert n == 2
    assert pool == ["sk1", "sk2", "sk3"]
    # class-m carries no explicit skill pool -> no picks offered
    assert options.skill_choice(gen_access, "class-m") == (0, [])


def test_spell_pools_none_for_noncaster(gen_access):
    resolved = [("class-a", 3, "sub-a")]     # class-a is a full caster
    cantrips, leveled = options.spell_pools(gen_access, resolved)
    assert cantrips == ["sp1", "sp2"] and leveled == ["sp3"]


def test_spell_pools_via_caster_subclass(gen_access):
    # class-m is a non-caster; its subclass sub-ek casts from class-a's list
    resolved = [("class-m", 3, "sub-ek")]
    cantrips, leveled = options.spell_pools(gen_access, resolved)
    assert cantrips == ["sp1", "sp2"] and leveled == ["sp3"]


def test_spell_pools_none_for_true_noncaster(gen_access):
    resolved = [("class-m", 2, None)]        # non-caster class, subclass not yet unlocked
    assert options.spell_pools(gen_access, resolved) == (None, None)


def test_equipment_bundles_and_item_resolution(gen_access):
    bundles = options.equipment_bundles(gen_access, "class", "class-a")
    assert [bid for bid, _ in bundles] == ["sa-a", "sa-b"]
    items = options.resolve_bundle_items(gen_access, "sa-a")
    assert items == [{"id": "blade-a", "name": "Blade A", "quantity": 1}]


# --------------------------------------------------------------------------- grammar shape

def test_pass1_grammar_constrains_to_dal_options(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    schema = grammar.build_pass1_grammar(gen_access, spec, [("class-a", 3, "sub-a")])
    props = schema["properties"]
    assert props["skills"]["items"]["enum"] == ["sk1", "sk2", "sk3"]
    assert props["spells"]["properties"]["cantrips"]["items"]["enum"] == ["sp1", "sp2"]
    # ruleset shape: a background ability-boost choice, and no race/racial-bonus field
    assert "background_increase" in props
    assert "race" not in props and "racial_bonus" not in props


def test_equipment_grammar_lists_bundles(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    schema = grammar.build_equipment_grammar(gen_access, spec, [("class-a", 3, "sub-a")])
    assert schema["properties"]["equipment_class"]["enum"] == ["sa-a", "sa-b"]
    assert schema["properties"]["equipment_background"]["enum"] == ["sa-bg"]


# --------------------------------------------------------------------------- assembled choices shape

def test_assembled_choices_shape(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a",
        "character_name": "Alpha"})
    resolved = [("class-a", 3, "sub-a")]
    choices = assemble.assemble_choices(gen_access, spec, resolved, {
        "name": "Alpha", "skills": ["sk1", "sk2"],
        "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a3"}})
    # species, not race; canonical ids; none of the superseded flat-file vocabulary
    assert choices["species"] == "species-a"
    assert "race" not in choices and "racial_bonus" not in choices and "ability_assignment" not in choices
    assert choices["classes"] == [{"class": "class-a", "level": 3, "subclass": "sub-a"}]
    # ability boost is background-sourced and reflects the model's legal pick
    assert choices["background_increase"] == {"a1": 2, "a3": 1}
    assert choices["skills"] == ["sk1", "sk2"]


def test_assemble_falls_back_to_default_boost_on_bad_pick(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    # a {2,1} pick with the same target twice is not a legal two-target boost -> default
    choices = assemble.assemble_choices(gen_access, spec, [("class-a", 3, "sub-a")], {
        "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a1"}})
    assert choices["background_increase"] == {"a1": 2, "a2": 1}


# --------------------------------------------------------------------------- end-to-end: grammar -> choices -> document

def _stub_pick(pass1, pass2=None):
    """A deterministic model stub: pass 1 is the schema carrying a 'name' field, pass 2 the
    equipment schema."""
    def pick(_prompt, schema):
        if "name" in (schema.get("required") or []):
            return pass1
        return pass2 or {}
    return pick


def test_noncaster_end_to_end(gen_access, access):
    # class-m below its subclass-unlock level is a genuine non-caster (no spellcasting class, no
    # caster subclass) -> the document carries NO grimoire.
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-m", "level": 2}], "background": "bg-a",
        "character_id": "char-nc", "character_name": "Alpha"})
    pick = _stub_pick(
        {"name": "Alpha",
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"}})
    choices = generate_choices(gen_access, spec, pick=pick)

    # ruleset shape: species-sourced identity, background-sourced boost, no superseded keys
    assert choices["species"] == "species-a" and "race" not in choices
    assert choices["background_increase"] == {"a1": 2, "a2": 1}

    document = derive_document(choices, gen_access)
    assert set(document) >= {"core", "inventory", "modifier"}
    assert "grimoire" not in document
    assert validate_core(document["core"], access)["legal"] is True
    inv = validate_inventory(document["core"], document["inventory"], document.get("modifier"), access)
    assert inv["legal"] is True, inv["violations"]
    mod = validate_modifier(document["core"], document["inventory"], document.get("grimoire"),
                            document["modifier"], access)
    assert mod["legal"] is True, mod["violations"]


def test_caster_full_class_end_to_end(gen_access, access):
    # class-a is a full spellcasting class -> a GRIMOIRE sheet; also exercises the class skill pool
    # and the starting-equipment bundle resolving into a concrete backpack item.
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-fc", "character_name": "Gamma"})
    pick = _stub_pick(
        {"name": "Gamma", "skills": ["sk1", "sk2"],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "spells": {"cantrips": ["sp1"], "spells": ["sp3"]}},
        {"equipment_class": "sa-a"})
    choices = generate_choices(gen_access, spec, pick=pick)

    assert choices["equipment"]["backpack"] == [{"id": "blade-a", "name": "Blade A", "quantity": 1}]

    document = derive_document(choices, gen_access)
    assert "grimoire" in document
    assert validate_core(document["core"], access)["legal"] is True
    assert validate_grimoire(document["core"], document["grimoire"], access)["legal"] is True
    inv = validate_inventory(document["core"], document["inventory"], document.get("modifier"), access)
    assert inv["legal"] is True, inv["violations"]
    mod = validate_modifier(document["core"], document.get("inventory"), document["grimoire"],
                            document["modifier"], access)
    assert mod["legal"] is True, mod["violations"]


def test_caster_end_to_end(gen_access, access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-m", "level": 3}],
        "subclasses": {"class-m": "sub-ek"}, "background": "bg-a",
        "character_id": "char-c", "character_name": "Beta"})
    # class-m has no skill pool -> the grammar offers no skills field; the caster's spell pool comes
    # from the subclass's spell-list class.
    pick = _stub_pick({"name": "Beta",
                       "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
                       "spells": {"cantrips": ["sp1"], "spells": ["sp3"]}})
    choices = generate_choices(gen_access, spec, pick=pick)

    assert choices["spells"] == {"cantrips": ["sp1"], "spells": ["sp3"]}

    document = derive_document(choices, gen_access)
    assert "grimoire" in document            # a spellcasting subclass -> a GRIMOIRE sheet
    assert validate_core(document["core"], access)["legal"] is True
    assert validate_grimoire(document["core"], document["grimoire"], access)["legal"] is True
    inv = validate_inventory(document["core"], document["inventory"], document.get("modifier"), access)
    assert inv["legal"] is True, inv["violations"]
    mod = validate_modifier(document["core"], document.get("inventory"), document["grimoire"],
                            document["modifier"], access)
    assert mod["legal"] is True, mod["violations"]
