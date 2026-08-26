"""Nondisclosing APP-01 failure types."""

from __future__ import annotations


class App01Error(ValueError):
    """Fail-closed error whose message is safe for local operator diagnostics."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.operator_message = message
        super().__init__(f"{code}: {message}")


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise App01Error(code, message)
