"""The shared completeness-report composer for the orchestrator's document endpoints (F07 D5/D6).

``compose_report(envelope, access)`` is written once and used by BOTH ``/v1/derive`` and
``/validate-document``. Given a ``character-document`` envelope it:

1. runs the per-sheet validator service functions over the sheets that are PRESENT (CORE is always
   present; the rest are folded in only when the envelope carries them),
2. folds their independent verdicts into one ``{legal, complete, violations[], summary}`` (legal /
   complete are AND-ed; violations are concatenated; the summary is re-tallied),
3. rebuilds the choice-grammar inputs from the CORE sheet and emits the typed completeness
   ``manifest`` via ``engine.build_manifest``, plus ``awaiting_choices``.

Two-layer doctrine: this module COMPOSES the validator services and the model-free engine — it never
re-implements a rule. The rule math (required counts) stays in ``engine.choices.options`` behind
``build_manifest``; the filled counts are read from the document. Reconstructing the manifest inputs
from the envelope (rather than from an in-memory choices object) is deliberate: it makes the two
routes deterministic against each other — a document produced by ``/v1/derive`` yields the identical
report when POSTed to ``/validate-document``.

FLAG-ONLY (liability): the manifest names a generic resource KIND plus counts only; the candidate
pools stay inside ``options.py`` and are never enumerated into the response.
"""
from engine.choices import RequestSpec, awaiting_choices, build_manifest
from validator.validate_companion import validate_companion
from validator.validate_core import validate_core
from validator.validate_grimoire import validate_grimoire
from validator.validate_inventory import validate_inventory
from validator.validate_modifier import validate_modifier


def _run_validators(envelope: dict, access) -> list[dict]:
    """Each present sheet's validator verdict. CORE is authoritative and always run; GRIMOIRE,
    INVENTORY, MODIFIER and COMPANION are run only when the envelope carries them. The per-sheet
    functions are the validator SERVICE (composed, not re-implemented) — the same functions the
    ``/validate-*`` routes expose."""
    core = envelope.get("core") or {}
    grimoire = envelope.get("grimoire")
    inventory = envelope.get("inventory")
    modifier = envelope.get("modifier")
    companion = envelope.get("companion")

    reports = [validate_core(core, access)]
    if grimoire is not None:
        reports.append(validate_grimoire(core, grimoire, access))
    if inventory is not None:
        reports.append(validate_inventory(core, inventory, modifier, access))
    if modifier is not None:
        reports.append(validate_modifier(core, inventory, grimoire, modifier, access))
    if companion is not None:
        reports.append(validate_companion(core, grimoire, companion, access))
    return reports


def _fold_reports(reports: list[dict]) -> dict:
    """Fold several per-sheet verdicts into one. ``legal`` / ``complete`` hold only if every sheet
    holds; the findings are concatenated and the summary re-tallied from the folded set."""
    violations = [v for r in reports for v in (r.get("violations") or [])]
    errors = sum(1 for v in violations if v.get("severity") == "ERROR")
    return {
        "legal": all(r.get("legal") for r in reports),
        "complete": all(r.get("complete") for r in reports),
        "violations": violations,
        "summary": {"total": len(violations), "errors": errors,
                    "warnings": len(violations) - errors},
    }


def _spells_from_grimoire(grimoire) -> dict:
    """The build's picked cantrips / leveled spells as the manifest reads them ({cantrips, spells}),
    read off the GRIMOIRE sheet (spell ``level`` 0 = cantrip). Presence is all the manifest needs — a
    caster with a non-empty pool but nothing chosen is what it flags."""
    if not isinstance(grimoire, dict):
        return {"cantrips": [], "spells": []}
    spells = [s for s in (grimoire.get("spells") or []) if isinstance(s, dict)]
    return {
        "cantrips": [s for s in spells if s.get("level") == 0],
        "spells": [s for s in spells if (s.get("level") or 0) >= 1],
    }


def _manifest_inputs(core: dict, grimoire, access):
    """Rebuild ``(spec, resolved, choices)`` for :func:`build_manifest` from a finished document.

    An inverse adapter (no rule math — the required counts live in ``options.py``): display names are
    resolved back to ids via ``access.resolve`` and each choice's FILLED count is read off the sheet.
    The document faithfully preserves subclass, the background ability-boost distribution, skill and
    expertise picks, chosen languages, feat / boon slots and picked spells, so those reconstruct
    exactly. ``tools`` is the one lossy field — a finished CORE merges chosen and granted tool
    proficiencies into one list with no per-tool source — so it is passed through best-effort (see the
    tool caveat carded for the document path)."""
    identity = core.get("identity") or {}

    resolved: list[tuple] = []
    class_choices: list[dict] = []
    for c in identity.get("classes") or []:
        if not isinstance(c, dict):
            continue
        cid = access.resolve("class", c.get("class"))
        if cid is None:
            continue
        level = int(c.get("level") or 0)
        sub_id = access.resolve("subclass", c.get("subclass")) if c.get("subclass") else None
        resolved.append((cid, level, sub_id))
        class_choices.append({"class": cid, "level": level, "subclass": sub_id})

    spec = RequestSpec(
        species=access.resolve("species", identity.get("species")),
        classes=[(cid, lv) for cid, lv, _sub in resolved],
        subclasses={cid: sub for cid, _lv, sub in resolved if sub},
        background=access.resolve("background", identity.get("background")),
    )

    skills = core.get("skills") or {}
    # A pool / choose-grant pick is attributed to "class" or "feature" by the CORE deriver; fixed
    # grants carry "species" / "background" / "feat". Only the picks count toward the skill manifest.
    skill_picks = [name for name, s in skills.items()
                   if isinstance(s, dict) and s.get("proficient")
                   and s.get("source") in ("class", "feature")]
    expertise = [name for name, s in skills.items()
                 if isinstance(s, dict) and s.get("expertise")]

    abilities = core.get("abilities") or {}
    background_increase = {k: e.get("background_bonus") for k, e in abilities.items()
                           if isinstance(e, dict) and e.get("background_bonus")}

    # The background origin feat is added by CORE automatically and is not one of the grammar's feat
    # slots, so it is excluded here; boons keep their source so the manifest can split slot vs boon.
    feats = [{"feat": f.get("name"), "source": f.get("source")}
             for f in (core.get("feats") or [])
             if isinstance(f, dict) and f.get("source") != "background"]

    choices = {
        "classes": class_choices,
        "background_increase": background_increase,
        "skills": skill_picks,
        "expertise": expertise,
        "tools": list((core.get("proficiencies") or {}).get("tools") or []),
        "languages": list(core.get("languages") or []),
        "feats": feats,
        "spells": _spells_from_grimoire(grimoire),
    }
    return spec, resolved, choices


def compose_report(envelope: dict, access) -> dict:
    """The ``completeness-report`` for a ``character-document`` envelope: the folded validator verdict
    plus the typed completeness manifest and ``awaiting_choices``. Used by both document routes."""
    base = _fold_reports(_run_validators(envelope, access))
    spec, resolved, choices = _manifest_inputs(envelope.get("core") or {},
                                               envelope.get("grimoire"), access)
    manifest = build_manifest(access, spec, resolved, choices)
    return {
        "schema_version": 1,
        "legal": base["legal"],
        "complete": base["complete"],
        "awaiting_choices": awaiting_choices(manifest),
        "violations": base["violations"],
        "manifest": manifest,
        "summary": base["summary"],
    }
