"""Machine-readable fail-closed PIPE-01 errors."""


class ConformanceError(ValueError):
    """A mandatory PIPE-01 conformance rule failed."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ConformanceError(code, message)
