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

from engine.derivation.document import derive_document
from app.generation.choices import generate_choices
from engine.choices import assemble, grammar, options, parse_request
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


# ------------------------------------------------------- T89 multiclass-prerequisite legality

def test_parse_request_accepts_legal_multiclass(gen_access):
    # class-a's array puts a3 at 13 -> class-mc-ok (primary a3) meets the multiclass minimum
    spec = parse_request(gen_access, {
        "species": "species-a", "background": "bg-a",
        "classes": [{"class": "class-a", "level": 3}, {"class": "class-mc-ok", "level": 2}]})
    assert spec.classes == [("class-a", 3), ("class-mc-ok", 2)]


def test_parse_request_accepts_legal_multiclass_or_relation(gen_access):
    # class-mc-or needs the minimum in EITHER primary; a3 (13) qualifies though a4 (10) would not
    spec = parse_request(gen_access, {
        "species": "species-a", "background": "bg-a",
        "classes": [{"class": "class-a", "level": 3}, {"class": "class-mc-or", "level": 2}]})
    assert [cid for cid, _ in spec.classes] == ["class-a", "class-mc-or"]


def test_parse_request_rejects_undermin_multiclass(gen_access):
    # class-mc-bad's primary ability (a4) sits at the baseline 10 in class-a's array -> below the
    # multiclass minimum, so the illegal combination is gated at parse time
    with pytest.raises(ValueError):
        parse_request(gen_access, {
            "species": "species-a", "background": "bg-a",
            "classes": [{"class": "class-a", "level": 3}, {"class": "class-mc-bad", "level": 2}]})


def test_parse_request_single_class_not_gated_by_prereq(gen_access):
    # a single-class build of the same class is legal — the prerequisite gates ADDITIONAL classes only
    spec = parse_request(gen_access, {
        "species": "species-a", "background": "bg-a",
        "classes": [{"class": "class-mc-bad", "level": 3}]})
    assert spec.classes == [("class-mc-bad", 3)]


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


def test_apply_equipment_stacks_shared_item_ids(gen_access, access):
    # a class bundle (sa-b) and a background bundle (sa-bg) both grant gear-a; assembly must merge the
    # two grants into ONE stacked backpack record (summed quantity), never a duplicate item id
    from validator.checks import inventory as inventory_check
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a",
        "character_id": "char-eq", "character_name": "Eq"})
    resolved = [("class-a", 3, "sub-a")]
    choices = assemble.assemble_choices(gen_access, spec, resolved, {"name": "Eq"})
    choices = assemble.apply_equipment(
        gen_access, spec, resolved,
        {"equipment_class": "sa-b", "equipment_background": "sa-bg"}, choices)

    backpack = choices["equipment"]["backpack"]
    stacked = [i for i in backpack if i["id"] == "gear-a"]
    assert len(stacked) == 1                 # one merged record, not two duplicate ids
    assert stacked[0]["quantity"] == 3       # 1 (class bundle) + 2 (background bundle)

    # the inventory validator (unchanged) accepts the stacked record — no duplicate-item-id finding
    sheet = {"equipped": choices["equipment"]["equipped"], "backpack": backpack}
    violations = inventory_check.check(sheet, access)
    assert not any(v.code == "duplicate-item-id" for v in violations), violations


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
    # class-m below its subclass-unlock level, with a species that grants no innate spell
    # (species-l), is a genuine non-caster (no spellcasting class, no caster subclass, no innate
    # grant) -> the document carries NO grimoire.
    spec = parse_request(gen_access, {
        "species": "species-l", "classes": [{"class": "class-m", "level": 2}], "background": "bg-a",
        "character_id": "char-nc", "character_name": "Alpha"})
    pick = _stub_pick(
        {"name": "Alpha",
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"}})
    choices = generate_choices(gen_access, spec, pick=pick)

    # ruleset shape: species-sourced identity, background-sourced boost, no superseded keys
    assert choices["species"] == "species-l" and "race" not in choices
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

    # bundle sa-a: its weapon is wielded (main hand), its 15 gp becomes starting treasure (T79/T80)
    assert choices["equipment"]["backpack"] == []
    assert choices["equipment"]["equipped"]["main_hand"]["name"] == "Blade A"
    assert choices["treasure"]["gp"] == 15

    document = derive_document(choices, gen_access)
    assert "grimoire" in document
    # the wielded weapon carries its resolved catalog facts, and the coin purse the derived treasure
    assert document["inventory"]["equipped"]["main_hand"]["category"] == "weapon"
    assert document["modifier"]["treasure"]["gp"] == 15
    assert validate_core(document["core"], access)["legal"] is True
    assert validate_grimoire(document["core"], document["grimoire"], access)["legal"] is True
    inv = validate_inventory(document["core"], document["inventory"], document.get("modifier"), access)
    assert inv["legal"] is True, inv["violations"]
    mod = validate_modifier(document["core"], document.get("inventory"), document["grimoire"],
                            document["modifier"], access)
    assert mod["legal"] is True, mod["violations"]


# --------------------------------------------------------------------------- ASI/feat slot progression

def test_ability_feat_slot_count_sums_per_class(gen_access):
    # class-a: 0 slots at L3, 2 by L8 (the synthetic ASI spine at levels 4 and 8)
    assert options.ability_feat_slot_count(gen_access, [("class-a", 3, None)]) == 0
    assert options.ability_feat_slot_count(gen_access, [("class-a", 8, None)]) == 2
    # multiclass sums each class at its own level (class-m opens none)
    assert options.ability_feat_slot_count(
        gen_access, [("class-a", 8, None), ("class-m", 4, None)]) == 2


def test_feat_increase_allocation(gen_access):
    scores = {"a1": 17, "a2": 15, "a3": 13}
    # a fixed-target feat raises its allowed ability (a2) by its point budget
    assert options.feat_increase_allocation(gen_access, "feat-inc", scores) == {"ability": "a2", "amount": 1}
    # the from-any raw increase raises the highest ability (+2, capped at max_per_ability=2)
    assert options.feat_increase_allocation(
        gen_access, "ability-score-improvement", scores) == {"ability": "a1", "amount": 2}
    # a feat with no increase allocates nothing
    assert options.feat_increase_allocation(gen_access, "feat-gen", scores) is None


def test_pass1_grammar_offers_slot_feats(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}], "background": "bg-a"})
    resolved = [("class-a", 8, "sub-a")]
    # default slot count is DB-derived: 2 slots by level 8
    schema = grammar.build_pass1_grammar(
        gen_access, spec, resolved,
        feat_slots=options.ability_feat_slot_count(gen_access, resolved))
    feats_field = schema["properties"]["feats"]
    assert feats_field["minItems"] == 2 and feats_field["maxItems"] == 2
    assert "feats" in schema["required"]
    # a level-3 build (below the first slot) offers no feats field at all
    schema3 = grammar.build_pass1_grammar(gen_access, spec, [("class-a", 3, "sub-a")], feat_slots=0)
    assert "feats" not in schema3["properties"]


def test_multilevel_slots_flow_into_document(gen_access, access):
    # a single-class L8 build reaches its two ability-increase/feat slots; the picks flow into the
    # CORE feats array and the folded increase lands in the ability final -- and it all validates.
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-l8", "character_name": "Delta"})
    pick = _stub_pick(
        {"name": "Delta", "skills": ["sk1", "sk2"],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "spells": {"cantrips": ["sp1"], "spells": ["sp3"]},
         "feats": ["feat-gen", "feat-inc"]},
        {"equipment_class": "sa-a"})
    choices = generate_choices(gen_access, spec, pick=pick)

    # two slot feats picked, alongside the background origin feat added by CORE
    assert [f["feat"] for f in choices["feats"]] == ["feat-gen", "feat-inc"]
    inc = next(f for f in choices["feats"] if f["feat"] == "feat-inc")["ability_increase"]
    assert inc == {"ability": "a2", "amount": 1}

    document = derive_document(choices, gen_access)
    names = [f["name"] for f in document["core"]["feats"]]
    assert "feat-gen" in names and "feat-inc" in names and "feat-origin" in names
    # a2: base 14 + background +1 + feat +1 = 16 (the fold reaches the ability final)
    assert document["core"]["abilities"]["x2"]["final"] == 16
    assert validate_core(document["core"], access)["legal"] is True
    inv = validate_inventory(document["core"], document["inventory"], document.get("modifier"), access)
    assert inv["legal"] is True, inv["violations"]


def test_slot_feats_repeatability_helpers(gen_access):
    # the raw ability-score-increase feat is repeatable; the plain general feat is not
    assert options.any_repeatable(gen_access, ["feat-gen", "ability-score-improvement"]) is True
    assert options.any_repeatable(gen_access, ["feat-gen", "feat-inc"]) is False
    # dedupe keeps repeatables' duplicates but collapses a repeated non-repeatable feat
    assert options.dedupe_slot_feats(
        gen_access, ["ability-score-improvement", "ability-score-improvement"]) == \
        ["ability-score-improvement", "ability-score-improvement"]
    assert options.dedupe_slot_feats(gen_access, ["feat-gen", "feat-gen"]) == ["feat-gen"]


def test_pass1_grammar_drops_uniqueitems_when_repeatable_available(gen_access):
    # with a repeatable feat in the pool, uniqueItems must NOT be set (else the raw ASI couldn't
    # fill two slots), and the slot count is preserved.
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}], "background": "bg-a"})
    schema = grammar.build_pass1_grammar(gen_access, spec, [("class-a", 8, "sub-a")], feat_slots=2)
    feats_field = schema["properties"]["feats"]
    assert feats_field["minItems"] == 2 and feats_field["maxItems"] == 2
    assert "ability-score-improvement" in feats_field["items"]["enum"]
    assert "uniqueItems" not in feats_field


def test_two_slots_both_spent_on_raw_asi(gen_access, access):
    # regression for the code-review find: before, uniqueItems + a single ASI enum entry made a
    # two-slot raw-ASI build unsatisfiable (and there was no ASI feat row at all). Now both slots may
    # take the repeatable raw ability-score-increase; the increases fold into the ability final,
    # clamped at the standard cap, and the document validates legal AND complete.
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-asi", "character_name": "Epsilon"})
    pick = _stub_pick(
        {"name": "Epsilon", "skills": ["sk1", "sk2"], "expertise": ["sk1", "sk2"],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "spells": {"cantrips": ["sp1"], "spells": ["sp3"]},
         "feats": ["ability-score-improvement", "ability-score-improvement"]},
        {"equipment_class": "sa-a"})
    choices = generate_choices(gen_access, spec, pick=pick)

    # both slots kept (repeatable), each folding a +2 to the highest ability (a1)
    assert [f["feat"] for f in choices["feats"]] == \
        ["ability-score-improvement", "ability-score-improvement"]
    assert all(f["ability_increase"] == {"ability": "a1", "amount": 2} for f in choices["feats"])

    document = derive_document(choices, gen_access)
    # a1: base 15 + background +2 + two feat +2s = 21, clamped to the cap (20)
    assert document["core"]["abilities"]["x1"]["final"] == 20
    result = validate_core(document["core"], access)
    assert result["legal"] is True and result["complete"] is True, result["violations"]


def test_two_slots_reject_duplicate_non_repeatable(gen_access, access):
    # a non-repeatable feat picked twice collapses to a single entry (rather than a repeated feat the
    # validator would flag) — the second slot is simply left unspent, which is legal.
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-dup", "character_name": "Zeta"})
    pick = _stub_pick(
        {"name": "Zeta", "skills": ["sk1", "sk2"],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "spells": {"cantrips": ["sp1"], "spells": ["sp3"]},
         "feats": ["feat-gen", "feat-gen"]},
        {"equipment_class": "sa-a"})
    choices = generate_choices(gen_access, spec, pick=pick)
    assert [f["feat"] for f in choices["feats"]] == ["feat-gen"]

    document = derive_document(choices, gen_access)
    assert validate_core(document["core"], access)["legal"] is True


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


# --------------------------------------------------------------------------- species sub-choices

def test_pass1_grammar_offers_lineage_for_species_with_lineages(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-l", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    resolved = [("class-a", 3, "sub-a")]
    schema = grammar.build_pass1_grammar(gen_access, spec, resolved)
    assert "lineage" in schema["properties"]
    assert schema["properties"]["lineage"]["enum"] == ["lin-l1", "lin-l2"]
    assert "lineage" in schema["required"]
    # a lineage-only species offers no variant field
    assert "species_variant" not in schema["properties"]


def test_pass1_grammar_offers_variant_for_species_with_variant_axis(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-v", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    resolved = [("class-a", 3, "sub-a")]
    schema = grammar.build_pass1_grammar(gen_access, spec, resolved)
    assert "species_variant" in schema["properties"]
    assert schema["properties"]["species_variant"]["enum"] == ["Variant A", "Variant B"]
    assert "species_variant" in schema["required"]
    assert "lineage" not in schema["properties"]


def test_pass1_grammar_offers_no_subchoice_for_plain_species(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    resolved = [("class-a", 3, "sub-a")]
    schema = grammar.build_pass1_grammar(gen_access, spec, resolved)
    assert "lineage" not in schema["properties"]
    assert "species_variant" not in schema["properties"]


def test_assemble_passes_lineage_pick_into_choices(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-l", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    resolved = [("class-a", 3, "sub-a")]
    choices = assemble.assemble_choices(
        gen_access, spec, resolved, {"name": "L", "lineage": "lin-l1"})
    assert choices["lineage"] == "lin-l1"
    # an invalid lineage pick is dropped rather than passed through
    bad = assemble.assemble_choices(
        gen_access, spec, resolved, {"name": "L", "lineage": "not-a-lineage"})
    assert bad["lineage"] is None


def test_assemble_passes_variant_pick_into_choices(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-v", "classes": [{"class": "class-a", "level": 3}], "background": "bg-a"})
    resolved = [("class-a", 3, "sub-a")]
    choices = assemble.assemble_choices(
        gen_access, spec, resolved, {"name": "V", "species_variant": "Variant A"})
    assert choices["species_variant"] == "Variant A"
    bad = assemble.assemble_choices(
        gen_access, spec, resolved, {"name": "V", "species_variant": "Nope"})
    assert bad["species_variant"] is None


# --------------------------------------------------------------------------- T87 top-tier boon slot

def _domains(report):
    return {v["domain"] for v in report["violations"]}


def test_boon_slot_count_gated_at_top_tier(gen_access):
    # the top-tier boon slot is a distinct feature gated at the top of the level range (level 19 in
    # the fixture); below it the build opens none, at/above it exactly one for a single-class build.
    assert options.boon_slot_count(gen_access, [("class-a", 8, None)]) == 0
    assert options.boon_slot_count(gen_access, [("class-a", 19, None)]) == 1
    # counted per class at its own level, summed across a multiclass
    assert options.boon_slot_count(
        gen_access, [("class-a", 19, None), ("class-m", 4, None)]) == 1


def test_pass1_grammar_offers_boon_slot_from_own_category(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 19}], "background": "bg-a"})
    resolved = [("class-a", 19, "sub-a")]
    schema = grammar.build_pass1_grammar(
        gen_access, spec, resolved,
        feat_slots=options.ability_feat_slot_count(gen_access, resolved),
        boon_slots=options.boon_slot_count(gen_access, resolved))
    boons = schema["properties"]["boons"]
    assert boons["minItems"] == 1 and boons["maxItems"] == 1
    # the boon slot draws from its OWN category (epic-boon: feat-boon), NOT the general feat pool
    assert boons["items"]["enum"] == ["feat-boon"]
    assert "feat-boon" not in schema["properties"]["feats"]["items"]["enum"]
    assert "boons" in schema["required"]
    # a build below the gating level offers no boon field at all
    below = grammar.build_pass1_grammar(gen_access, spec, [("class-a", 8, "sub-a")],
                                        feat_slots=2, boon_slots=0)
    assert "boons" not in below["properties"]


def test_boon_pick_flows_into_core(gen_access, access):
    from engine.derivation.core import derive_core
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 19}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-boon", "character_name": "Omega"})
    pick = _stub_pick(
        {"name": "Omega", "skills": ["sk1", "sk2"],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "spells": {"cantrips": ["sp1"], "spells": ["sp3"]},
         "boons": ["feat-boon"]})
    choices = generate_choices(gen_access, spec, pick=pick)

    # the boon feat is folded into the choices' feat list (its own category slot)
    assert "feat-boon" in [f["feat"] for f in choices["feats"]]

    core = derive_core(choices, gen_access)
    assert "feat-boon" in [f["name"] for f in core["feats"]]
    # feat-boon confers a from-any +1; the deterministic allocation raises the highest ability (a1):
    # base 15 + background +2 + boon +1 = 18
    assert core["abilities"]["x1"]["final"] == 18
    assert validate_core(core, access)["legal"] is True


# ------------------------------------------------------------------- T88 model-chosen increase target

def test_pass1_grammar_offers_ability_increase_targets(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}], "background": "bg-a"})
    resolved = [("class-a", 8, "sub-a")]
    schema = grammar.build_pass1_grammar(
        gen_access, spec, resolved,
        feat_slots=options.ability_feat_slot_count(gen_access, resolved))
    inc = schema["properties"]["ability_increases"]
    assert inc["maxItems"] == 2
    shapes = {b["properties"]["shape"]["const"] for b in inc["items"]["oneOf"]}
    assert shapes == {"two", "split"}
    # targets are constrained to actual ability ids (legality by construction)
    two_branch = next(b for b in inc["items"]["oneOf"] if b["properties"]["shape"]["const"] == "two")
    assert set(two_branch["properties"]["ability"]["enum"]) >= {"a1", "a2", "a3"}
    # the target field is offered but not forced (a slot may take a feat instead of an increase)
    assert "ability_increases" not in schema["required"]


def test_model_chosen_increase_target_replaces_heuristic(gen_access, access):
    # the raw ability-score increase would default to the HIGHEST ability (a1); the model instead
    # targets a3, and the chosen target — not the heuristic — lands in the CORE ability final.
    from engine.derivation.core import derive_core
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-t88", "character_name": "Theta"})
    pick = _stub_pick(
        {"name": "Theta", "skills": ["sk1", "sk2"],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "spells": {"cantrips": ["sp1"], "spells": ["sp3"]},
         "feats": ["ability-score-improvement"],
         "ability_increases": [{"shape": "two", "ability": "a3"}]})
    choices = generate_choices(gen_access, spec, pick=pick)
    inc = choices["feats"][0]["ability_increase"]
    assert inc == {"ability": "a3", "amount": 2}

    core = derive_core(choices, gen_access)
    # a3: base 13 + chosen +2 = 15 (NOT a1, which the highest-ability heuristic would have picked)
    assert core["abilities"]["x3"]["final"] == 15
    assert core["abilities"]["x1"]["final"] == 17    # a1: base 15 + background +2, no ASI here
    assert validate_core(core, access)["legal"] is True


def test_model_chosen_split_increase(gen_access, access):
    # a split increase (+1 / +1 across two abilities) is representable and applied to BOTH abilities.
    from engine.derivation.core import derive_core
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-a", "level": 8}],
        "subclasses": {"class-a": "sub-a"}, "background": "bg-a",
        "character_id": "char-split", "character_name": "Iota"})
    pick = _stub_pick(
        {"name": "Iota", "skills": ["sk1", "sk2"],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "spells": {"cantrips": ["sp1"], "spells": ["sp3"]},
         "feats": ["ability-score-improvement"],
         "ability_increases": [{"shape": "split", "abilities": ["a2", "a3"]}]})
    choices = generate_choices(gen_access, spec, pick=pick)
    inc = choices["feats"][0]["ability_increase"]
    assert inc == [{"ability": "a2", "amount": 1}, {"ability": "a3", "amount": 1}]

    core = derive_core(choices, gen_access)
    # a2: base 14 + background +1 + split +1 = 16 ; a3: base 13 + split +1 = 14
    assert core["abilities"]["x2"]["final"] == 16
    assert core["abilities"]["x3"]["final"] == 14
    assert validate_core(core, access)["legal"] is True


# --------------------------------------------------------------------------- T94 weapon-mastery choice

def test_weapon_mastery_choice_enumerated_from_dal(gen_access):
    # a build with the weapon-mastery feature is offered its pick count (2 at level 1) from the
    # masterable-weapon pool (the weapons carrying a mastery property); a build without it gets none.
    n, pool = options.weapon_mastery_choice(gen_access, [("class-wm", 1, None)])
    assert n == 2
    assert pool == ["weapon-a", "weapon-b", "weapon-c"]
    # the count follows the resource ladder (3 from level 5)
    n5, _ = options.weapon_mastery_choice(gen_access, [("class-wm", 5, None)])
    assert n5 == 3
    assert options.weapon_mastery_choice(gen_access, [("class-a", 3, None)]) == (0, [])


def test_pass1_grammar_offers_weapon_mastery(gen_access):
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-wm", "level": 1}], "background": "bg-a"})
    resolved = [("class-wm", 1, None)]
    schema = grammar.build_pass1_grammar(gen_access, spec, resolved)
    wm = schema["properties"]["weapon_masteries"]
    assert wm["items"]["enum"] == ["weapon-a", "weapon-b", "weapon-c"]
    assert wm["minItems"] == 2 and wm["maxItems"] == 2 and wm["uniqueItems"] is True
    assert "weapon_masteries" in schema["required"]


def test_weapon_mastery_picks_flow_into_core_and_validate_complete(gen_access, access):
    from engine.derivation.core import derive_core
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-wm", "level": 1}], "background": "bg-a",
        "character_id": "char-wm", "character_name": "Kappa"})
    pick = _stub_pick(
        {"name": "Kappa", "skills": [],
         "background_increase": {"shape": "two-one", "plus_two": "a1", "plus_one": "a2"},
         "weapon_masteries": ["weapon-a", "weapon-b"]})
    choices = generate_choices(gen_access, spec, pick=pick)
    assert choices["weapon_masteries"] == ["weapon-a", "weapon-b"]

    core = derive_core(choices, gen_access)
    assert core["weapon_masteries"] == ["weapon-a", "weapon-b"]
    assert "Weapon Mastery" in [f["name"] for f in core["features"]]
    report = validate_core(core, access)
    assert report["legal"] is True
    # the weapon-mastery completeness gap is closed: no finding in that domain
    assert "weapon_mastery" not in _domains(report)


def test_weapon_mastery_pick_constrained_to_masterable_pool(gen_access):
    # a stray pick outside the masterable pool is dropped; picks are capped at the granted count.
    spec = parse_request(gen_access, {
        "species": "species-a", "classes": [{"class": "class-wm", "level": 1}], "background": "bg-a"})
    resolved = [("class-wm", 1, None)]
    choices = assemble.assemble_choices(
        gen_access, spec, resolved,
        {"name": "K", "weapon_masteries": ["weapon-a", "not-a-weapon", "weapon-b", "weapon-c"]})
    # 'not-a-weapon' dropped, capped at the count of 2
    assert choices["weapon_masteries"] == ["weapon-a", "weapon-b"]


def test_weapon_mastery_count_stacks_across_multiclass(gen_access):
    # A multiclass build combining two mastery-granting classes STACKS (sums) each class's
    # allowance at its own level, rather than keeping the larger one. class-wm grants 2 at
    # level 1; class-wm2 grants 1 at level 1 -> 2 + 1 = 3 (the SUM, not the MAX of 2).
    n, pool = options.weapon_mastery_choice(
        gen_access, [("class-wm", 1, None), ("class-wm2", 1, None)])
    assert n == 3
    assert pool == ["weapon-a", "weapon-b", "weapon-c"]
    # A single-class build is unchanged: it keeps its own allowance (2 at level 1).
    n_single, _ = options.weapon_mastery_choice(gen_access, [("class-wm", 1, None)])
    assert n_single == 2
    # The stacked count is still capped at the masterable-weapon pool size: class-wm at
    # level 5 grants 3 and class-wm2 grants 1, summing to 4 -> capped at the 3-weapon pool.
    n_capped, _ = options.weapon_mastery_choice(
        gen_access, [("class-wm", 5, None), ("class-wm2", 1, None)])
    assert n_capped == 3
