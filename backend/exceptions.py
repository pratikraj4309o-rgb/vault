class VaultException(Exception):
    """Base exception for NexStore VAULT."""

    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class ObjectNotFoundError(VaultException):
    def __init__(self, object_id: str):
        super().__init__(
            f"Object '{object_id}' not found",
            status_code=404,
            error_code="OBJECT_NOT_FOUND",
        )


class NodeNotFoundError(VaultException):
    def __init__(self, node_id: str):
        super().__init__(
            f"Storage node '{node_id}' not found",
            status_code=404,
            error_code="NODE_NOT_FOUND",
        )


class RepairJobNotFoundError(VaultException):
    def __init__(self, repair_id: str):
        super().__init__(
            f"Repair job '{repair_id}' not found",
            status_code=404,
            error_code="REPAIR_NOT_FOUND",
        )


class VersionConflictError(VaultException):
    def __init__(self, message: str = "Version conflict detected during concurrent update"):
        super().__init__(message, status_code=409, error_code="VERSION_CONFLICT")


class InsufficientNodesError(VaultException):
    def __init__(self, required: int, available: int):
        super().__init__(
            f"Insufficient healthy storage nodes: required {required}, available {available}",
            status_code=409,
            error_code="INSUFFICIENT_HEALTHY_NODES",
        )


class InvalidConfigurationError(VaultException):
    def __init__(self, message: str):
        super().__init__(message, status_code=422, error_code="INVALID_CONFIGURATION")


class StorageUnavailableError(VaultException):
    def __init__(self, object_id: str, reason: str = "All replicas are unavailable or corrupted"):
        super().__init__(
            f"Object '{object_id}' unavailable: {reason}",
            status_code=503,
            error_code="STORAGE_UNAVAILABLE",
        )
