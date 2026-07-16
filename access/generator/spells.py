"""Spell-domain option reads for the choice grammar: a caster class's selectable spell pool (the
spells on its list), optionally bounded by spell level. Pure DB reads — no rule math (how many a
caster may take, and at which levels, is the grammar's/deriver's concern)."""
from access.generator import GeneratorAccess


def class_spell_pool(access: GeneratorAccess, class_id: str,
                     level_min: int | None = None, level_max: int | None = None) -> list:
    """The spells on a class's list — its selectable pool — as (id, name, level, is_ritual) rows,
    ordered by (level, id). `level_min`/`level_max` bound the spell level inclusively (pass
    level_min=level_max=0 for cantrips only). DISTINCT guards against a duplicated spell_class pair
    yielding the same spell twice."""
    sql = ("SELECT DISTINCT s.id, s.name, s.level, s.is_ritual FROM spell s "
           "JOIN spell_class sc ON s.id = sc.spell_id WHERE sc.class_id=?")
    params: list = [class_id]
    if level_min is not None:
        sql += " AND s.level>=?"
        params.append(level_min)
    if level_max is not None:
        sql += " AND s.level<=?"
        params.append(level_max)
    sql += " ORDER BY s.level, s.id"
    return access.db.q(sql, *params)
