from typing import Optional
from backend.exceptions import VersionConflictError


def validate_expected_version(current_version: int, expected_version: Optional[int]) -> int:
    """
    Validates optimistic concurrency control version check.
    If expected_version is provided and does not match current_version, raises 409 VersionConflictError.
    Returns the next monotonic version number (current_version + 1).
    """
    if expected_version is not None and expected_version != current_version:
        raise VersionConflictError(
            f"Optimistic concurrency check failed: expected version {expected_version}, but authoritative version is {current_version}"
        )
    return current_version + 1
