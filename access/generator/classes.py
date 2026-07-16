"""Class-domain option reads for the choice grammar: the class catalogue, each class's subclasses and
the level they unlock, the class skill-grant options, and the ability-priority facts (primary
abilities, saving throws, standard array) an allocator reads. Pure DB reads — no rule math."""
from access.generator import GeneratorAccess


def list_classes(access: GeneratorAccess) -> list:
    """Every class the grammar may choose, as (id, name, hit_die_faces, subclass_level,
    caster_progression, primary_mode, skill_choose_n, skill_from_any) rows, ordered by id."""
    return access.db.q(
        "SELECT id, name, hit_die_faces, subclass_level, caster_progression, primary_mode, "
        "skill_choose_n, skill_from_any FROM class ORDER BY id")


def subclasses_for_class(access: GeneratorAccess, class_id: str) -> list:
    """The subclasses of a class, as (id, class_id, name, is_caster) rows, ordered by id. Empty if
    the class is unknown or has no subclasses modelled."""
    return access.db.q(
        "SELECT id, class_id, name, is_caster FROM subclass WHERE class_id=? ORDER BY id", class_id)


def subclass_unlock_level(access: GeneratorAccess, class_id: str) -> int | None:
    """The class level at which a subclass may first be chosen. Returns None for EITHER an unknown
    class OR a class whose subclass_level is NULL — the caller can't distinguish the two from the
    return value alone."""
    return access.db.scalar("SELECT subclass_level FROM class WHERE id=?", class_id)


def class_skill_options(access: GeneratorAccess, class_id: str) -> tuple[int | None, int | None, list[str]]:
    """A class's skill-grant choice: (choose_n, from_any, option_skill_ids). `from_any`=1 means the
    class picks from ANY skill (no explicit pool, so option_skill_ids is empty); otherwise the pool
    is the class_skill_option rows, ordered by skill_id. Returns (None, None, []) if the class is
    unknown."""
    row = access.db.one("SELECT skill_choose_n, skill_from_any FROM class WHERE id=?", class_id)
    if row is None:
        return None, None, []
    pool = [r["skill_id"] for r in access.db.q(
        "SELECT skill_id FROM class_skill_option WHERE class_id=? ORDER BY skill_id", class_id)]
    return row["skill_choose_n"], row["skill_from_any"], pool


def class_primary_abilities(access: GeneratorAccess, class_id: str) -> list:
    """A class's primary-ability rows, as (ability_id, kind) ordered by ability_id. `kind` marks how
    the ability is used (e.g. the attack/spellcasting role)."""
    return access.db.q(
        "SELECT ability_id, kind FROM class_primary_ability WHERE class_id=? ORDER BY ability_id",
        class_id)


def class_saving_throws(access: GeneratorAccess, class_id: str) -> list[str]:
    """The ability ids a class grants saving-throw proficiency in, ordered by ability_id."""
    return [r["ability_id"] for r in access.db.q(
        "SELECT ability_id FROM class_saving_throw WHERE class_id=? ORDER BY ability_id", class_id)]


def class_standard_array(access: GeneratorAccess, class_id: str) -> list:
    """A class's suggested standard-array assignment, as (ability_id, score) rows ordered by
    ability_id. Empty if the class has no suggested assignment."""
    return access.db.q(
        "SELECT ability_id, score FROM class_standard_array WHERE class_id=? ORDER BY ability_id",
        class_id)


def ability_feat_slots(access: GeneratorAccess, class_id: str, level: int) -> int:
    """The number of ability-score-increase / feat slots a class has opened up by ``level`` — the
    count of its slot-granting class features at or below that level. The generic schedule is a slot
    at fixed levels with some classes granting extra ones, so the count is read from the class-feature
    spine (ruleset data), never assumed. Each slot is spent on a general feat or a raw ability-score
    increase — and the raw increase is itself one of the general feats, so the slot count feeds the
    general-feat option pool. Pure DB read."""
    return access.db.scalar(
        "SELECT COUNT(*) FROM class_feature WHERE class_id=? AND level<=? "
        "AND name='Ability Score Improvement'", class_id, level) or 0
