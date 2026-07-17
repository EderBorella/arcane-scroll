"""Skills-domain DB facts: display names and ability mapping for the skill dimension.

Pure DB reads — the resolver maps display name -> id; this maps the reverse (id -> display name)
for emitting a gained skill key on a sheet."""
from access.validator import ValidatorAccess


def skill_name(access: ValidatorAccess, skill_id: str) -> str | None:
    """The display name of a skill, or None if the id is unknown."""
    return access.db.scalar("SELECT name FROM skill WHERE id=?", skill_id)
