"""Base capability interface for WishGranter."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel


class CapabilityResult(BaseModel):
    success: bool
    data: dict[str, Any] = {}
    error: Optional[str] = None
    artifacts: list[dict[str, Any]] = []
    execution_time: float = 0.0
    capability_name: str = ""


class Capability(ABC):
    name: str = "base"
    description: str = "Base capability"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> CapabilityResult:
        ...

    def _result(
        self,
        success: bool,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        start_time: float = 0.0,
    ) -> CapabilityResult:
        return CapabilityResult(
            success=success,
            data=data or {},
            error=error,
            artifacts=artifacts or [],
            execution_time=time.time() - start_time if start_time else 0.0,
            capability_name=self.name,
        )