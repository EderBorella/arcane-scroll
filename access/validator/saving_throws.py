"""Saving-throws domain DB facts: which abilities a class grants saving-throw proficiency in."""
from access.validator import ValidatorAccess


def class_save_abilities(access: ValidatorAccess, class_id: str) -> list[str]:
    """The ability ids a class grants saving-throw proficiency in, unordered."""
    return [row["ability_id"] for row in access.db.q(
        "SELECT ability_id FROM class_saving_throw WHERE class_id=?", class_id)]
