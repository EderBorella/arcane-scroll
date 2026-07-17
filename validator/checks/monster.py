"""MONSTER domain (monster-sheet:1 shape): validates a STANDALONE monster sheet
against DB facts, owner-less.

A materialised monster is a concrete creature with no owner, so this check reuses
the CONCRETE companion field-checks verbatim (:mod:`validator.checks.companion`) —
every fixed-stat field (AC, HP, hit dice, speed, senses, abilities, saves, skills,
passive perception, attacks, defences) is INDEPENDENTLY re-derived from the creature
catalog and compared to the sheet. It NEVER reads the deriver's output.

There is NO owner context: the creature id is carried on each ``monsters[]`` entry
(``creature_id``), not via a CORE.companions[] index, and no owner GRIMOIRE is
consulted. TEMPLATED (owner-scaled) creatures are rejected here as they are in the
deriver — they have no stand-alone stat block, so a monster sheet claiming one is
flagged illegal rather than validated against un-scaled zeros.

The reused field-checks are the SINGLE SOURCE of the re-derivation math. They are
parametrised with a domain / code-prefix, so a monster finding carries a NATIVE
``monster`` domain and a native ``monster-*`` code straight from the shared helper —
the codes are NOT rewritten after the fact. Only the companion-shaped PATH and
MESSAGE prefixes are rewritten post-hoc (``companion_modifiers.<idx>`` ->
``monsters.<idx>.stat_block``; ``companion <idx>:`` -> ``monster <idx>:``).

NOT in ALL_CHECKS — monster-sheet:1-specific, run via POST /validate-monster.
"""
from validator.checks import companion as comp_check
from validator.report import Violation

DOMAIN = "monster"
CODE_PREFIX = "monster"


def _retag_paths(raw: list[Violation], idx: int) -> list[Violation]:
    """Rewrite the companion-shaped PATH and MESSAGE prefixes of findings from the
    reused shared helpers into monster terms: path prefix
    'companion_modifiers.<idx>' -> 'monsters.<idx>.stat_block', message prefix
    'companion <idx>:' -> 'monster <idx>:'. The domain and code arrive NATIVE from
    the parametrised helpers (domain 'monster', code 'monster-*') and are preserved
    as-is — codes are never rewritten. Any finding not matching a prefix is passed
    through unchanged (safe no-op)."""
    path_from = f"companion_modifiers.{idx}"
    path_to = f"monsters.{idx}.stat_block"
    msg_from = f"companion {idx}:"
    msg_to = f"monster {idx}:"
    out = []
    for x in raw:
        path = x.path
        if isinstance(path, str) and path.startswith(path_from):
            path = path_to + path[len(path_from):]
        message = x.message
        if isinstance(message, str) and message.startswith(msg_from):
            message = msg_to + message[len(msg_from):]
        out.append(Violation(x.domain, x.code, x.kind, message, path))
    return out


def _check_concrete_fields(access, cm: dict, creature_id: str, row, idx: int) -> list[Violation]:
    """Re-derive every fixed-stat field via the reused shared field-checks, asking
    them to emit native monster codes (domain / code-prefix parametrised)."""
    raw: list[Violation] = []
    tag = {"domain": DOMAIN, "code_prefix": CODE_PREFIX}
    comp_check._check_hp(cm, row, raw, idx, **tag)
    comp_check._check_hit_dice(cm, row, raw, idx, **tag)
    comp_check._check_ac(cm, row, raw, idx, **tag)
    comp_check._check_speed(access, cm, creature_id, raw, idx, **tag)
    comp_check._check_senses(access, cm, creature_id, raw, idx, **tag)
    comp_check._check_abilities(access, cm, creature_id, raw, idx, **tag)
    comp_check._check_saves(access, cm, creature_id, raw, idx, **tag)
    comp_check._check_skills(access, cm, creature_id, raw, idx, **tag)
    comp_check._check_passive(access, cm, creature_id, raw, idx, **tag)
    comp_check._check_attacks(access, cm, creature_id, raw, idx, **tag)
    comp_check._check_defenses(access, cm, creature_id, raw, idx, **tag)
    return _retag_paths(raw, idx)


def check(monster_sheet: dict, access) -> list[Violation]:
    v: list[Violation] = []
    monsters = monster_sheet.get("monsters")
    if not isinstance(monsters, list):
        return v

    for idx, entry in enumerate(monsters):
        if not isinstance(entry, dict):
            continue
        creature_id = entry.get("creature_id")
        cm = entry.get("stat_block")
        if not isinstance(cm, dict):
            v.append(Violation(DOMAIN, "monster-stat-block-missing", "illegal",
                               f"monster {idx}: stat_block is missing or not an object",
                               f"monsters.{idx}.stat_block"))
            continue

        # State validity is shape-level and always checked (reused; native code).
        state_raw: list[Violation] = []
        comp_check._check_states(access, cm, state_raw, idx, domain=DOMAIN, code_prefix=CODE_PREFIX)
        v.extend(_retag_paths(state_raw, idx))

        if not creature_id:
            v.append(Violation(DOMAIN, "monster-creature-missing-id", "illegal",
                               f"monster {idx}: entry has no creature_id",
                               f"monsters.{idx}.creature_id"))
            continue

        row = comp_check.creature_q.creature_row(access, creature_id)
        if row is None:
            v.append(Violation(DOMAIN, "monster-creature-unknown", "illegal",
                               f"monster {idx}: creature_id {creature_id!r} does not resolve",
                               f"monsters.{idx}.creature_id"))
            continue

        if comp_check._is_templated(access, creature_id):
            # A templated (owner-scaled) creature has no stand-alone stat block; it must
            # never be validated against un-scaled zeros — reject it outright.
            v.append(Violation(DOMAIN, "monster-templated-not-standalone", "illegal",
                               f"monster {idx}: creature {creature_id!r} is owner-scaled "
                               f"(templated) and cannot be materialised as a standalone monster",
                               f"monsters.{idx}.creature_id"))
            continue

        v.extend(_check_concrete_fields(access, cm, creature_id, row, idx))

    return v
