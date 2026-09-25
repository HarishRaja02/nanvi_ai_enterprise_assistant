from __future__ import annotations

import re

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputValidationError(ValueError):
    pass


def validate_non_empty(value: str, field_name: str, max_length: int = 2048) -> str:
    if not isinstance(value, str):
        raise InputValidationError(f"{field_name} must be a string")

    normalized = value.strip()

    if not normalized:
        raise InputValidationError(f"{field_name} cannot be empty")

    if len(normalized) > max_length:
        raise InputValidationError(f"{field_name} exceeds maximum length")

    if CONTROL_CHARACTERS.search(normalized):
        raise InputValidationError(f"{field_name} contains invalid control characters")

    return normalized
