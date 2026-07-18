"""F05-T142 — always-on ability-check / initiative advantage (grant_d20_modifier).

Mirrors the save-advantage spine: the check-advantage field is derived on CORE (permanent_defenses)
and MODIFIER (effective_defenses) and independently re-derived by the defenses check. In the synthetic
ruleset a dedicated feat ('Feat Check Adv') owns a target_kind='check', modifier_id='advantage' grant
that maps to the 'initiative' scope."""
from app.derivation.core import _permanent_defenses
from app.derivation.modifier import ActiveEffects, derive_defenses
from validator.checks.defenses import check
from validator.checks.modifier import _check_defenses


def _sheet(species="Species A", classes=None, feats=None, defenses=None):
    return {
        "identity": {"species": species,
                     "classes": classes if classes is not None else [{"class": "Class A", "level": 3}]},
        "feats": feats or [],
        "defenses": defenses or {},
    }


def _codes(sheet, access):
    return {v.code for v in check(sheet, access)}


# ---- CORE validator (independent re-derivation) ----

def test_check_advantage_clean(access):
    s = _sheet(feats=[{"name": "Feat Check Adv", "source": "asi"}],
               defenses={"check_advantages": ["initiative"]})
    assert "check-advantage-missing" not in _codes(s, access)
    assert "check-advantage-ungranted" not in _codes(s, access)


def test_check_advantage_missing_flagged(access):
    s = _sheet(feats=[{"name": "Feat Check Adv", "source": "asi"}],
               defenses={})
    assert "check-advantage-missing" in _codes(s, access)


def test_check_advantage_ungranted_flagged(access):
    s = _sheet(feats=[], defenses={"check_advantages": ["initiative"]})
    assert "check-advantage-ungranted" in _codes(s, access)


# ---- CORE deriver (permanent_defenses) ----

def test_core_deriver_materialises_check_advantage(access):
    perm = _permanent_defenses(access, {
        "identity": {"species": "Species A", "classes": [{"class": "Class A", "level": 3}]},
        "feats": [{"name": "Feat Check Adv", "source": "asi"}]})
    assert perm.get("check_advantages") == ["initiative"]


def test_core_deriver_additive_when_absent(access):
    perm = _permanent_defenses(access, {
        "identity": {"species": "Species A", "classes": [{"class": "Class A", "level": 3}]},
        "feats": []})
    # additive: the key is omitted entirely when the build owns no check-advantage grant
    assert "check_advantages" not in perm


# ---- MODIFIER deriver (effective_defenses union) ----

def test_modifier_deriver_unions_permanent_check_advantage(access):
    core = {"permanent_defenses": {"check_advantages": ["initiative"]}}
    eff = derive_defenses(core, ActiveEffects(), access)
    assert eff.get("check_advantages") == ["initiative"]


def test_modifier_deriver_omits_when_empty(access):
    core = {"permanent_defenses": {}}
    eff = derive_defenses(core, ActiveEffects(), access)
    assert "check_advantages" not in eff


# ---- MODIFIER validator (effective ⊇ core subset) ----

def test_modifier_subset_violation_when_dropped(access):
    sheet = {
        "core": {"permanent_defenses": {"check_advantages": ["initiative"]}},
        "modifier": {"effective_defenses": {}},
    }
    v = []
    _check_defenses(sheet, v)
    assert any(x.code == "defense-subset-violation" and "check_advantages" in (x.path or "")
               for x in v)


def test_modifier_subset_ok_when_retained(access):
    sheet = {
        "core": {"permanent_defenses": {"check_advantages": ["initiative"]}},
        "modifier": {"effective_defenses": {"check_advantages": ["initiative"]}},
    }
    v = []
    _check_defenses(sheet, v)
    assert v == []
