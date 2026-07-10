"""Fixtures for the data-access layer tests. Builds a small SYNTHETIC rules DB (the real table/column
shapes, fake vocabulary) into a temp file — so the tests exercise the query machinery, carry no game
content, and run anywhere without the real (local) rulebook DB."""
import sqlite3

import pytest

from access.db import RulesDB

# Every grant header table the primitives may touch: the uniform spine columns + a few domain columns
# the tests read. Real schema has more columns; primitives SELECT * so a subset is fine.
_HEADERS = {
    "grant_ability_increase": "points INTEGER",
    "grant_ability_set": "ability_id TEXT, score INTEGER, mode TEXT",
    "grant_bonus": "target_kind TEXT, target_id TEXT, value INTEGER",
    "grant_condition": "condition_id TEXT, effect TEXT",
    "grant_d20_modifier": "target_kind TEXT, ability_id TEXT, modifier_id TEXT, source_name TEXT, scope_note TEXT",
    "grant_expertise": "choose_n INTEGER, mode TEXT",
    "grant_feat": "choose_n INTEGER, from_category TEXT",
    "grant_hp": "flat INTEGER, per_level INTEGER",
    "grant_proficiency": "target_kind TEXT, mode TEXT, choose_n INTEGER, multiclass_only INTEGER",
    "grant_resistance": "damage_type_id TEXT, mode TEXT",
    "grant_resource": "name TEXT, uses_kind TEXT",
    "grant_save_advantage": "scope_kind TEXT, ability_id TEXT",
    "grant_sense": "sense_id TEXT, range_ft INTEGER",
    "grant_speed": "movement_mode_id TEXT, equals_walk INTEGER",
    "grant_spell": "bucket TEXT, recovery TEXT",
}
_CHILDREN = {  # child table -> columns beyond grant_id
    "grant_ability_increase_value": "ability_id TEXT",
    "grant_expertise_value": "skill_id TEXT",
    "grant_proficiency_value": "target_id TEXT",
    "grant_proficiency_category": "tool_category_id TEXT",
    "grant_proficiency_weapon_filter": "property_id TEXT",
    "grant_resistance_option": "damage_type_id TEXT",
    "grant_spell_fixed": "spell_id TEXT",
    "grant_spell_choice": "choose_n INTEGER, from_kind TEXT",
    "grant_spell_choice_value": "value_id TEXT",
}


def _build(path: str) -> None:
    con = sqlite3.connect(path)
    cur = con.cursor()
    for t, extra in _HEADERS.items():
        cur.execute(f"CREATE TABLE {t} (id TEXT PRIMARY KEY, owner_kind TEXT, owner_id TEXT, "
                    f"gained_at_level INTEGER, {extra})")
    for t, extra in _CHILDREN.items():
        cur.execute(f"CREATE TABLE {t} (grant_id TEXT, {extra})")
    cur.execute("CREATE TABLE class_resource_level (resource_id TEXT, level INTEGER, count INTEGER, "
                "die_count INTEGER, die_faces INTEGER, bonus INTEGER)")
    cur.execute("CREATE TABLE rules_constant (id TEXT PRIMARY KEY, value_int INTEGER, note TEXT)")
    cur.execute("CREATE TABLE class_feature (id TEXT PRIMARY KEY, class_id TEXT, level INTEGER, name TEXT)")
    cur.execute("CREATE TABLE subclass_feature (id TEXT PRIMARY KEY, subclass_id TEXT, class_level INTEGER, name TEXT)")

    # source 'src-a' confers: a fixed skill (L1), a choose-2 (L5), a resistance (L1)
    cur.execute("INSERT INTO grant_proficiency (id,owner_kind,owner_id,gained_at_level,target_kind,mode,choose_n,multiclass_only) "
                "VALUES ('gp1','species','src-a',1,'skill','fixed',NULL,0)")
    cur.execute("INSERT INTO grant_proficiency_value (grant_id,target_id) VALUES ('gp1','skill-x')")
    cur.execute("INSERT INTO grant_proficiency (id,owner_kind,owner_id,gained_at_level,target_kind,mode,choose_n,multiclass_only) "
                "VALUES ('gp2','species','src-a',5,'skill','choose',2,0)")
    cur.execute("INSERT INTO grant_resistance (id,owner_kind,owner_id,gained_at_level,damage_type_id,mode) "
                "VALUES ('gr1','species','src-a',1,'dmg-x','fixed')")
    # a magic item 'item-a' with two stacking AC bonuses (sum = 3)
    cur.execute("INSERT INTO grant_bonus (id,owner_kind,owner_id,gained_at_level,target_kind,target_id,value) "
                "VALUES ('gb1','magic','item-a',NULL,'ac',NULL,1)")
    cur.execute("INSERT INTO grant_bonus (id,owner_kind,owner_id,gained_at_level,target_kind,target_id,value) "
                "VALUES ('gb2','magic','item-a',NULL,'ac',NULL,2)")
    # a resource ladder 'res-a'
    for lv, cnt in [(1, 2), (5, 3), (9, 4)]:
        cur.execute("INSERT INTO class_resource_level (resource_id,level,count) VALUES (?,?,?)", ("res-a", lv, cnt))
    cur.execute("INSERT INTO rules_constant VALUES ('const-a',27,'a fake constant')")
    for lv, nm in [(1, "FeatureA"), (2, "FeatureB"), (5, "FeatureC")]:
        cur.execute("INSERT INTO class_feature (id,class_id,level,name) VALUES (?,?,?,?)", (f"cf-{lv}", "cls-a", lv, nm))
    con.commit()
    con.close()


@pytest.fixture
def rules_db_path(tmp_path) -> str:
    p = tmp_path / "rules.db"
    _build(str(p))
    return str(p)


@pytest.fixture
def db(rules_db_path):
    with RulesDB(rules_db_path) as handle:
        yield handle
