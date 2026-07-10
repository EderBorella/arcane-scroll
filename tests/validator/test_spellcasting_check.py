from validator.checks.spellcasting import check


def _sheet(sources=None, spells=None, spell_slots=None, pact_slots=None, classes=None,
          species="Species A", feats=None):
    sc = {
        "sources": sources if sources is not None else _clean_sources(),
        "spells": spells if spells is not None else _clean_spells(),
    }
    if spell_slots is None:
        spell_slots = {"1": {"max": 4, "remaining": 4}, "2": {"max": 2, "remaining": 2}}
    if spell_slots:
        sc["spell_slots"] = spell_slots
    if pact_slots:
        sc["pact_slots"] = pact_slots
    return {
        "identity": {
            "classes": classes if classes is not None else [{"class": "Class A", "level": 3}],
            "species": species,
            "background": "Background A",
        },
        "feats": feats if feats is not None else [],
        "proficiency_bonus": 2,
        "abilities": {"a1": {"final": 14, "modifier": 2}},
        "spellcasting": sc,
    }


def _clean_sources():
    # class-a L3: DB grants cantrips_known=2, prepared_spells=3 (class_cantrips_prepared);
    # save_dc 8+pb(2)+mod(2)=12, attack_bonus pb(2)+mod(2)=4
    return {"Class A": {"kind": "class", "ability": "Ability 1", "modifier": 2,
                        "save_dc": 12, "attack_bonus": 4, "cantrips_known": 2, "prepared_limit": 3}}


def _clean_spells():
    return [
        {"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "Class A"},
        {"name": "Sp2", "level": 0, "bucket": "cantrip", "source": "Class A"},
        {"name": "Sp3", "level": 1, "bucket": "prepared", "source": "Class A"},
    ]


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_single_source_has_no_findings(access):
    assert check(_sheet(), access) == []


def test_wrong_save_dc(access):
    sources = _clean_sources()
    sources["Class A"]["save_dc"] = 99
    assert "spell-save-dc-mismatch" in _codes(_sheet(sources=sources), access)


def test_wrong_attack_bonus(access):
    sources = _clean_sources()
    sources["Class A"]["attack_bonus"] = 99
    assert "spell-attack-mismatch" in _codes(_sheet(sources=sources), access)


def test_source_claims_more_cantrips_than_class_grants(access):
    # class-a L3 grants 2 cantrips_known; declaring 9 is a lie about the class's own budget
    sources = _clean_sources()
    sources["Class A"]["cantrips_known"] = 9
    assert "source-budget-too-high" in _codes(_sheet(sources=sources), access)


def test_source_claims_more_prepared_than_class_grants(access):
    sources = _clean_sources()
    sources["Class A"]["prepared_limit"] = 99
    assert "source-budget-too-high" in _codes(_sheet(sources=sources), access)


def test_too_many_cantrips_for_declared_budget(access):
    # declared cantrips_known stays truthful (2, matches the DB) but 3 cantrip-bucket spells exceed it
    spells = _clean_spells() + [{"name": "Sp3", "level": 0, "bucket": "cantrip", "source": "Class A"}]
    assert "too-many-cantrips" in _codes(_sheet(spells=spells), access)


def test_too_many_prepared_for_declared_budget(access):
    # prepared_limit is 3 -- 4 distinct (name, source) pairs exceeds it without tripping duplicate
    spells = [{"name": n, "level": 1, "bucket": "prepared", "source": "Class A"}
              for n in ("Sp1", "Sp2", "Sp3", "Sp4")]
    assert "too-many-prepared" in _codes(_sheet(spells=spells, species="Species A"), access)


def test_off_list_spell_not_granted_is_illegal(access):
    spells = _clean_spells() + [{"name": "Sp4", "level": 1, "bucket": "prepared", "source": "Class A"}]
    # no species (so no grant confers sp4) -- sp4 is off class-a's list and thus illegal here
    assert "spell-not-on-list" in _codes(_sheet(spells=spells, species=None), access)


def test_off_list_spell_granted_to_species_is_allowed(access):
    spells = _clean_spells() + [{"name": "Sp4", "level": 1, "bucket": "prepared", "source": "Class A"}]
    codes = _codes(_sheet(spells=spells, species="Species A"), access)
    assert "spell-not-on-list" not in codes


def test_always_bucket_spell_skips_class_list_check(access):
    # sp4 is off class-a's list, but bucket "always" is a grant -- never list-checked, regardless
    # of species/granted status
    spells = _clean_spells() + [{"name": "Sp4", "level": 1, "bucket": "always", "source": "Class A"}]
    assert "spell-not-on-list" not in _codes(_sheet(spells=spells, species=None), access)


def test_non_class_source_is_never_list_checked(access):
    sources = _clean_sources()
    sources["Species A"] = {"kind": "species", "ability": "Ability 1", "modifier": 2,
                            "save_dc": 12, "attack_bonus": 4}
    spells = _clean_spells() + [{"name": "Sp4", "level": 1, "bucket": "always", "source": "Species A"}]
    assert "spell-not-on-list" not in _codes(_sheet(sources=sources, spells=spells), access)


def test_third_caster_subclass_spell_on_its_subclass_caster_list_is_allowed(access):
    # class-m (non-caster) + sub-ek (third-caster, casts from class-a's list per subclass_spellcasting)
    # -- Sp1 is on class-a's list, so a spell sourced from class-m via sub-ek is legal even though
    # class-m has no spell list of its own
    sources = {"Class M": {"kind": "class", "ability": "Ability 1", "modifier": 2}}
    classes = [{"class": "Class M", "level": 3, "subclass": "Sub EK"}]
    spells = [{"name": "Sp1", "level": 0, "bucket": "cantrip", "source": "Class M"}]
    sheet = _sheet(sources=sources, spells=spells, spell_slots={}, classes=classes, species=None)
    assert "spell-not-on-list" not in _codes(sheet, access)


def test_third_caster_subclass_spell_off_its_subclass_caster_list_is_illegal(access):
    # Sp4 is not on class-a's list and not otherwise granted -- still illegal for a class-m/sub-ek
    # source, proving the check uses class-a's list (not class-m's, which doesn't exist) and doesn't
    # just wave everything through
    sources = {"Class M": {"kind": "class", "ability": "Ability 1", "modifier": 2}}
    classes = [{"class": "Class M", "level": 3, "subclass": "Sub EK"}]
    spells = [{"name": "Sp4", "level": 1, "bucket": "prepared", "source": "Class M"}]
    sheet = _sheet(sources=sources, spells=spells, spell_slots={}, classes=classes, species=None)
    assert "spell-not-on-list" in _codes(sheet, access)


def test_unknown_spell_name(access):
    spells = _clean_spells() + [{"name": "Nonexistent Spell", "level": 1, "bucket": "prepared",
                                 "source": "Class A"}]
    assert "unknown-spell" in _codes(_sheet(spells=spells), access)


def test_duplicate_name_source_pair_is_illegal(access):
    spells = _clean_spells() + [{"name": "Sp3", "level": 1, "bucket": "prepared", "source": "Class A"}]
    assert "spell-duplicate" in _codes(_sheet(spells=spells), access)


def test_same_name_different_source_is_not_a_duplicate(access):
    sources = _clean_sources()
    sources["Species A"] = {"kind": "species", "ability": "Ability 1", "modifier": 2,
                            "save_dc": 12, "attack_bonus": 4}
    spells = _clean_spells() + [{"name": "Sp3", "level": 1, "bucket": "always", "source": "Species A"}]
    assert "spell-duplicate" not in _codes(_sheet(sources=sources, spells=spells), access)


def test_spell_slots_mismatch(access):
    assert "spell-slots-mismatch" in _codes(
        _sheet(spell_slots={"1": {"max": 5, "remaining": 5}, "2": {"max": 2, "remaining": 2}}), access)


def test_pact_slots_match_no_findings(access):
    sources = {"Class P": {"kind": "class", "ability": "Ability 1", "modifier": 2,
                          "save_dc": 12, "attack_bonus": 4}}
    classes = [{"class": "Class P", "level": 2}]
    pact_slots = {"1": {"max": 2, "remaining": 2}}
    sheet = _sheet(sources=sources, spells=[], spell_slots={}, pact_slots=pact_slots, classes=classes)
    assert check(sheet, access) == []


def test_pact_slots_mismatch(access):
    sources = {"Class P": {"kind": "class", "ability": "Ability 1", "modifier": 2,
                          "save_dc": 12, "attack_bonus": 4}}
    classes = [{"class": "Class P", "level": 2}]
    pact_slots = {"1": {"max": 99, "remaining": 99}}
    sheet = _sheet(sources=sources, spells=[], spell_slots={}, pact_slots=pact_slots, classes=classes)
    assert "pact-slots-mismatch" in _codes(sheet, access)


def test_unexpected_pact_slots_without_a_pact_class(access):
    pact_slots = {"1": {"max": 2, "remaining": 2}}
    assert "unexpected-pact-slots" in _codes(_sheet(pact_slots=pact_slots), access)


def test_two_leveled_casters_uses_multiclass_slots(access):
    # class-a L3 (full, +3) + class-b L3 with third-caster subclass sub-b (floor(3/3)=1) -> combined 4
    classes = [{"class": "Class A", "level": 3}, {"class": "Class B", "level": 3, "subclass": "Sub B"}]
    spell_slots = {"1": {"max": 4, "remaining": 4}, "2": {"max": 3, "remaining": 3}}
    sheet = _sheet(spells=[], spell_slots=spell_slots, classes=classes)
    assert check(sheet, access) == []


def test_two_leveled_casters_single_class_slot_table_would_mismatch(access):
    # sanity: class-a's own L3 table ({1:4,2:2}) does not match the combined-caster-level expectation
    # ({1:4,2:3}) -- proves the multiclass path is actually exercised, not the solo one
    classes = [{"class": "Class A", "level": 3}, {"class": "Class B", "level": 3, "subclass": "Sub B"}]
    spell_slots = {"1": {"max": 4, "remaining": 4}, "2": {"max": 2, "remaining": 2}}
    sheet = _sheet(spells=[], spell_slots=spell_slots, classes=classes)
    assert "spell-slots-mismatch" in _codes(sheet, access)


def test_spellcasting_none_has_no_findings(access):
    sheet = _sheet()
    sheet["spellcasting"] = None
    assert check(sheet, access) == []


def test_spellcasting_not_a_dict_does_not_raise(access):
    sheet = _sheet()
    sheet["spellcasting"] = "x"
    assert check(sheet, access) == []


def test_sources_not_a_dict_does_not_raise(access):
    sheet = _sheet()
    sheet["spellcasting"] = {"sources": "oops", "spells": []}
    assert isinstance(check(sheet, access), list)


def test_source_entry_not_a_dict_does_not_raise(access):
    sheet = _sheet()
    sheet["spellcasting"] = {"sources": {"Class A": "oops"}, "spells": []}
    assert isinstance(check(sheet, access), list)


def test_spells_not_a_list_does_not_raise(access):
    sheet = _sheet()
    sheet["spellcasting"] = {"sources": _clean_sources(), "spells": "oops"}
    assert isinstance(check(sheet, access), list)


def test_spell_entry_not_a_dict_does_not_raise(access):
    sheet = _sheet()
    sheet["spellcasting"] = {"sources": _clean_sources(), "spells": ["oops"]}
    assert isinstance(check(sheet, access), list)


def test_malformed_identity_does_not_raise(access):
    sheet = _sheet()
    sheet["identity"] = "oops"
    assert isinstance(check(sheet, access), list)


def test_missing_modifier_skips_dc_attack_check(access):
    sources = _clean_sources()
    del sources["Class A"]["modifier"]
    sources["Class A"]["save_dc"] = 99  # would mismatch if the check ran
    codes = _codes(_sheet(sources=sources), access)
    assert "spell-save-dc-mismatch" not in codes


def _widen_sources():
    # class-a at level 10: no declared cantrips_known/prepared_limit budgets, so the
    # source-budget-truthfulness and spell-count checks stay silent regardless of the (untabulated)
    # level-10 row -- this fixture is only exercising the spell-list-widening check.
    return {"Class A": {"kind": "class", "ability": "Ability 1", "modifier": 2}}


def test_widened_class_list_spell_is_allowed_at_the_widening_level(access):
    # class-a's Magical-Secrets-style widening grant (gained_at_level=10) widens its legal list to
    # include class-b's list; sp5 is on class-b's list only. A level-10 class-a source preparing it
    # must NOT be flagged -- it's legal via the widened list.
    classes = [{"class": "Class A", "level": 10}]
    spells = [{"name": "Sp5", "level": 1, "bucket": "prepared", "source": "Class A"}]
    sheet = _sheet(sources=_widen_sources(), spells=spells, spell_slots={}, classes=classes, species=None)
    assert "spell-not-on-list" not in _codes(sheet, access)


def test_widened_class_list_spell_is_still_illegal_below_the_widening_level(access):
    # negative regression: a class-a source BELOW the widening level (gained_at_level=10) has no
    # widening yet -- sp5 (off class-a's own list, not granted) must still be flagged.
    classes = [{"class": "Class A", "level": 9}]
    spells = [{"name": "Sp5", "level": 1, "bucket": "prepared", "source": "Class A"}]
    sheet = _sheet(sources=_widen_sources(), spells=spells, spell_slots={}, classes=classes, species=None)
    assert "spell-not-on-list" in _codes(sheet, access)


def test_non_widened_class_off_list_non_granted_spell_is_still_illegal(access):
    # negative regression: a class with no widening grant at all preparing an off-list, non-granted
    # spell is still caught -- widening support must not turn the list check into a rubber stamp.
    # (class-a at its ordinary level 3 has no widening grant active either way, but this pins the
    # pre-existing off-list case explicitly against the widening change.)
    spells = _clean_spells() + [{"name": "Sp4", "level": 1, "bucket": "prepared", "source": "Class A"}]
    assert "spell-not-on-list" in _codes(_sheet(spells=spells, species=None), access)


# ── T34: list_widening_classes generalization tests ──────────────────────────

from access.validator import spellcasting as q


def test_list_widening_subclass(access):
    result = q.list_widening_classes(access, "subclass", "sub-widen")
    assert "class-b" in result


def test_list_widening_at_level(access):
    below = q.list_widening_classes(access, "class", "class-a", at_level=3)
    assert len(below) == 0
    at = q.list_widening_classes(access, "class", "class-a", at_level=10)
    assert "class-b" in at


def test_list_widening_class_detail(access):
    result = q.list_widening_classes(access, "class_detail", "detail-widen")
    assert "class-b" in result


def test_list_widening_class_option(access):
    result = q.list_widening_classes(access, "class_option", "class-opt-widen")
    assert "class-b" in result


def test_class_detail_widening_in_list_check(access):
    sources = {"Class A": {"kind": "class", "ability": "Ability 1", "modifier": 2}}
    classes = [{"class": "Class A", "level": 3, "class_detail": "Detail A"}]
    spells = [{"name": "Sp5", "level": 1, "bucket": "cantrip", "source": "Class A"}]
    sheet = _sheet(sources=sources, spells=spells, spell_slots={}, classes=classes, species=None)
    assert "spell-not-on-list" not in _codes(sheet, access)


def test_class_option_widening_in_list_check(access):
    sources = {"Class A": {"kind": "class", "ability": "Ability 1", "modifier": 2}}
    classes = [{"class": "Class A", "level": 3}]
    spells = [{"name": "Sp5", "level": 1, "bucket": "cantrip", "source": "Class A"}]
    sheet = _sheet(sources=sources, spells=spells, spell_slots={}, classes=classes, species=None)
    sheet["features"] = [{"name": "Class Opt A"}]
    assert "spell-not-on-list" not in _codes(sheet, access)

    features = sheet.get("features", [])
    fname = features[0].get("name") if isinstance(features[0], dict) else features[0]
    oid = access.resolve("class_option", fname)
    assert oid is not None
