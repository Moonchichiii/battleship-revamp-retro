from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class ServiceResult(Generic[T]):
    success: bool
    data: T | None = None
    error: str = ""

    @classmethod
    def ok(cls, data: T = None) -> ServiceResult[T]:
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, message: str) -> ServiceResult[T]:
        return cls(success=False, error=message)
