from validator.checks.spellcasting import check


def _sheet(spellcasting=None, classes=None, species="Species A", feats=None):
    return {
        "identity": {
            "classes": classes if classes is not None else [{"class": "Class A", "level": 3}],
            "species": species,
            "background": "Background A",
        },
        "feats": feats if feats is not None else [],
        "proficiency_bonus": 2,
        "abilities": {"a1": {"final": 14, "modifier": 2}},
        "spellcasting": spellcasting if spellcasting is not None else _clean_class_a(),
    }


def _clean_class_a():
    return {
        "ability": "Ability 1",
        "save_dc": 12,          # 8 + pb(2) + mod(2)
        "attack_bonus": 4,      # pb(2) + mod(2)
        "shared_slots": {"1": {"max": 4, "used": 0}, "2": {"max": 2, "used": 0}},
        "Class A": {"cantrips": ["Sp1", "Sp2"], "prepared": ["Sp1", "Sp2", "Sp3"]},
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


def test_clean_single_full_caster_has_no_findings(access):
    assert check(_sheet(), access) == []


def test_wrong_save_dc(access):
    sc = _clean_class_a()
    sc["save_dc"] = 99
    assert "spell-save-dc-mismatch" in _codes(_sheet(sc), access)


def test_wrong_attack_bonus(access):
    sc = _clean_class_a()
    sc["attack_bonus"] = 99
    assert "spell-attack-mismatch" in _codes(_sheet(sc), access)


def test_shared_slots_mismatch(access):
    sc = _clean_class_a()
    sc["shared_slots"]["1"]["max"] = 5
    assert "spell-slots-mismatch" in _codes(_sheet(sc), access)


def test_too_many_cantrips(access):
    sc = _clean_class_a()
    sc["Class A"]["cantrips"] = ["Sp1", "Sp2", "Sp3"]
    codes = _codes(_sheet(sc), access)
    assert "too-many-cantrips" in codes


def test_too_many_prepared(access):
    sc = _clean_class_a()
    sc["Class A"]["prepared"] = ["Sp1", "Sp2", "Sp3", "Sp1"]
    assert "too-many-prepared" in _codes(_sheet(sc), access)


def test_off_list_spell_not_granted_is_illegal(access):
    sc = _clean_class_a()
    sc["Class A"]["prepared"] = ["Sp1", "Sp2", "Sp4"]
    # no species (so no grant confers sp4) -- sp4 is off class-a's list and thus illegal here
    assert "spell-not-on-list" in _codes(_sheet(sc, species=None), access)


def test_off_list_spell_granted_to_species_is_allowed(access):
    sc = _clean_class_a()
    sc["Class A"]["prepared"] = ["Sp1", "Sp2", "Sp4"]
    codes = _codes(_sheet(sc, species="Species A"), access)
    assert "spell-not-on-list" not in codes


def test_unknown_spell_name(access):
    sc = _clean_class_a()
    sc["Class A"]["prepared"] = ["Sp1", "Sp2", "Nonexistent Spell"]
    assert "unknown-spell" in _codes(_sheet(sc), access)


def test_pact_slots_match_no_findings(access):
    sc = {
        "ability": "Ability 1", "save_dc": 12, "attack_bonus": 4,
        "pact_slots": {"level": 1, "max": 2, "used": 0},
        "Class P": {"cantrips": [], "prepared": []},
    }
    classes = [{"class": "Class P", "level": 2}]
    assert check(_sheet(sc, classes=classes), access) == []


def test_pact_slots_mismatch(access):
    sc = {
        "ability": "Ability 1", "save_dc": 12, "attack_bonus": 4,
        "pact_slots": {"level": 1, "max": 99, "used": 0},
        "Class P": {"cantrips": [], "prepared": []},
    }
    classes = [{"class": "Class P", "level": 2}]
    assert "pact-slots-mismatch" in _codes(_sheet(sc, classes=classes), access)


def test_unexpected_pact_slots_without_a_pact_class(access):
    sc = _clean_class_a()
    sc["pact_slots"] = {"level": 1, "max": 2, "used": 0}
    assert "unexpected-pact-slots" in _codes(_sheet(sc), access)


def test_two_leveled_casters_uses_multiclass_slots(access):
    # class-a L3 (full, +3) + class-b L3 with third-caster subclass sub-b (floor(3/3)=1) -> combined 4
    sc = {
        "ability": "Ability 1", "save_dc": 12, "attack_bonus": 4,
        "shared_slots": {"1": {"max": 4, "used": 0}, "2": {"max": 3, "used": 0}},
        "Class A": {"cantrips": [], "prepared": []},
    }
    classes = [{"class": "Class A", "level": 3}, {"class": "Class B", "level": 3, "subclass": "Sub B"}]
    assert check(_sheet(sc, classes=classes), access) == []


def test_two_leveled_casters_single_class_slot_table_would_mismatch(access):
    # sanity: if the multiclass path were NOT taken, class-a's own L3 table ({1:4,2:2}) would not
    # match these declared slots ({1:4,2:3}) -- proves the combined formula is actually exercised
    sc = {
        "ability": "Ability 1", "save_dc": 12, "attack_bonus": 4,
        "shared_slots": {"1": {"max": 4, "used": 0}, "2": {"max": 2, "used": 0}},
        "Class A": {"cantrips": [], "prepared": []},
    }
    classes = [{"class": "Class A", "level": 3}, {"class": "Class B", "level": 3, "subclass": "Sub B"}]
    assert "spell-slots-mismatch" in _codes(_sheet(sc, classes=classes), access)


def test_spellcasting_not_a_dict_does_not_raise(access):
    sheet = _sheet()
    sheet["spellcasting"] = "x"
    assert check(sheet, access) == []


def test_malformed_identity_does_not_raise(access):
    sheet = _sheet()
    sheet["identity"] = "oops"
    assert isinstance(check(sheet, access), list)


def test_malformed_ability_list_does_not_raise_and_skips_dc_attack(access):
    sc = _clean_class_a()
    sc["ability"] = ["Ability 1"]
    codes = _codes(_sheet(sc), access)
    assert "spell-save-dc-mismatch" not in codes
    assert "spell-attack-mismatch" not in codes
