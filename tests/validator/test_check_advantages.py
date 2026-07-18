"""F05-T142 — always-on ability-check / initiative advantage (grant_d20_modifier).

Mirrors the save-advantage spine: the check-advantage field is derived on CORE (permanent_defenses)
and MODIFIER (effective_defenses) and independently re-derived by the defenses check. In the synthetic
ruleset a dedicated feat ('Feat Check Adv') owns two target_kind='check', modifier_id='advantage'
grants (one row per scope) that map to the 'initiative' and 'athletics' scopes — exercising the FULL
per-owner scope set from the structured ``scope`` column, not a single hardcoded scope."""
import sqlite3

from access.validator import ValidatorAccess
from app.derivation.core import _permanent_defenses
from app.derivation.modifier import ActiveEffects, derive_defenses, resolve_active_effects
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
               defenses={"check_advantages": ["athletics", "initiative"]})
    assert "check-advantage-missing" not in _codes(s, access)
    assert "check-advantage-ungranted" not in _codes(s, access)


def test_check_advantage_partial_scope_flagged(access):
    # The owner confers BOTH scopes; a sheet carrying only one is missing the other.
    s = _sheet(feats=[{"name": "Feat Check Adv", "source": "asi"}],
               defenses={"check_advantages": ["initiative"]})
    assert "check-advantage-missing" in _codes(s, access)


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
    # The full per-owner scope set is emitted (sorted), not just the initiative scope.
    assert perm.get("check_advantages") == ["athletics", "initiative"]


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


# ---- item-owned advantages (deriver ↔ validator symmetry close-out) ----
# A single magic item owns BOTH a save-advantage grant (concentration) and a check-advantage
# grant (perception). This exercises the item path the deriver's _accumulate_item_effects now
# materialises alongside senses/speeds, matching the validator's item re-derivation via
# item_grants_for for grant_save_advantage AND grant_d20_modifier. Neutral synthetic ids only.

ADV_ITEM_NAME = "Adv Item Alpha"


def _with_item_advantages(access, requires_attunement=0):
    """Wire a non-attunement (or attunement) magic item owning one save-advantage grant
    (concentration) and one check-advantage grant (perception), then return a fresh access."""
    con = sqlite3.connect(access.db.path)
    con.execute("INSERT INTO catalog_item (id,name,kind,category_id) VALUES "
                "('mi-adv','Adv Item Alpha','armor','shield')")
    con.execute("INSERT INTO magic_item (id,rarity_id,requires_attunement) VALUES "
                "('mi-adv','uncommon',?)", (requires_attunement,))
    con.execute("INSERT INTO grant_save_advantage VALUES "
                "('gsa-mi-adv','magic_item','mi-adv',NULL,'concentration',NULL,NULL,NULL)")
    con.execute("INSERT INTO grant_d20_modifier "
                "(owner_kind,owner_id,target_kind,ability_id,modifier_id,scope,source_name) "
                "VALUES ('magic_item','mi-adv','check','a2','advantage','perception','mi-adv')")
    con.commit()
    con.close()
    return ValidatorAccess(path=access.db.path)


def _core_l3():
    return {"identity": {"species": "Species A",
                         "classes": [{"class": "Class A", "level": 3}]},
            "feats": []}


def _equip_adv_item(attuned=False):
    item = {"id": "item-adv", "name": ADV_ITEM_NAME, "magic": True}
    if attuned:
        item["attunement"] = {"attuned": True}
    return {"equipped": {"shield": item}}


# deriver — passive-on-equip branch (non-attunement item, no attunement needed)

def test_item_advantages_materialise_on_equip(access):
    acc = _with_item_advantages(access, requires_attunement=0)
    effects = resolve_active_effects(_core_l3(), _equip_adv_item(), [], [], acc)
    assert "concentration" in effects.save_advantages
    assert "perception" in effects.check_advantages
    eff = derive_defenses({"permanent_defenses": {}}, effects, acc)
    assert eff.get("save_advantages") == ["concentration"]
    assert eff.get("check_advantages") == ["perception"]


# deriver — attuned branch (attunement item, contributes only while attuned)

def test_item_advantages_materialise_when_attuned(access):
    acc = _with_item_advantages(access, requires_attunement=1)
    inv = _equip_adv_item()
    item_states = [{"inventory_ref": "item-adv", "attuned": True}]
    effects = resolve_active_effects(_core_l3(), inv, [], item_states, acc)
    assert "concentration" in effects.save_advantages
    assert "perception" in effects.check_advantages


def test_item_advantages_absent_when_attunement_item_unattuned(access):
    # An attunement item that is equipped but NOT attuned confers neither advantage — matching
    # the validator's item_grants_for gate.
    acc = _with_item_advantages(access, requires_attunement=1)
    effects = resolve_active_effects(_core_l3(), _equip_adv_item(), [], [], acc)
    assert "concentration" not in effects.save_advantages
    assert "perception" not in effects.check_advantages


# validator — clean when the sheet carries exactly the item-owned advantages

def test_item_advantages_validator_clean(access):
    acc = _with_item_advantages(access, requires_attunement=0)
    s = {"identity": {"species": "Species A", "classes": [{"class": "Class A", "level": 3}]},
         "feats": [],
         "equipped": {"shield": {"magic": True, "name": ADV_ITEM_NAME}},
         "defenses": {"save_advantages": ["concentration"], "check_advantages": ["perception"]}}
    codes = {v.code for v in check(s, acc)}
    assert "save-advantage-missing" not in codes
    assert "save-advantage-ungranted" not in codes
    assert "check-advantage-missing" not in codes
    assert "check-advantage-ungranted" not in codes


# validator — independence: a sheet missing an equipped item's advantage is flagged

def test_item_save_advantage_missing_flagged(access):
    acc = _with_item_advantages(access, requires_attunement=0)
    s = {"identity": {"species": "Species A", "classes": [{"class": "Class A", "level": 3}]},
         "feats": [],
         "equipped": {"shield": {"magic": True, "name": ADV_ITEM_NAME}},
         "defenses": {"check_advantages": ["perception"]}}  # save advantage dropped
    assert "save-advantage-missing" in {v.code for v in check(s, acc)}


def test_item_check_advantage_missing_flagged(access):
    acc = _with_item_advantages(access, requires_attunement=0)
    s = {"identity": {"species": "Species A", "classes": [{"class": "Class A", "level": 3}]},
         "feats": [],
         "equipped": {"shield": {"magic": True, "name": ADV_ITEM_NAME}},
         "defenses": {"save_advantages": ["concentration"]}}  # check advantage dropped
    assert "check-advantage-missing" in {v.code for v in check(s, acc)}
