"""Data models for the WishGranter system."""

from __future__ import annotations

import uuid
import time
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class WishStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    THINKING = "thinking"
    PAUSED = "paused"
    GRANTED = "granted"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class WishCategory(str, Enum):
    INFORMATION = "information"
    CODE = "code"
    FILE = "file"
    ANALYSIS = "analysis"
    WEB = "web"
    AUTOMATION = "automation"
    CREATIVE = "creative"
    KNOWLEDGE = "knowledge"
    COMPOUND = "compound"
    UNKNOWN = "unknown"


class CapabilityType(str, Enum):
    WEB_SEARCH = "web_search"
    CODE_GEN = "code_gen"
    FILE_IO = "file_io"
    DATA_ANALYSIS = "data_analysis"
    WEB_SCRAPER = "web_scraper"
    SHELL = "shell"
    KNOWLEDGE = "knowledge"


class WishStep(BaseModel):
    step_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str
    capability: CapabilityType
    params: dict[str, Any] = Field(default_factory=dict)
    status: WishStatus = WishStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retries: int = 0
    max_retries: int = 3

    def mark_started(self):
        self.status = WishStatus.EXECUTING
        self.started_at = time.time()

    def mark_completed(self, result: dict[str, Any]):
        self.status = WishStatus.GRANTED
        self.result = result
        self.completed_at = time.time()

    def mark_failed(self, error: str):
        self.retries += 1
        if self.retries >= self.max_retries:
            self.status = WishStatus.FAILED
        else:
            self.status = WishStatus.PENDING
        self.error = error
        self.completed_at = time.time()


class WishPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    wish_text: str
    category: WishCategory = WishCategory.UNKNOWN
    steps: list[WishStep] = Field(default_factory=list)
    reasoning: str = ""
    revision: int = 1
    created_at: float = Field(default_factory=time.time)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == WishStatus.GRANTED)

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100


class ThinkingLog(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    thought: str
    action: str = ""
    result: str = ""
    iteration: int = 0
    is_reflection: bool = False


class WishResult(BaseModel):
    wish_id: str
    status: WishStatus
    summary: str = ""
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    thinking_log: list[ThinkingLog] = Field(default_factory=list)
    total_iterations: int = 0
    total_time_seconds: float = 0.0
    plan_revisions: int = 0


class Wish(BaseModel):
    wish_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    text: str
    status: WishStatus = WishStatus.PENDING
    category: WishCategory = WishCategory.UNKNOWN
    plan: Optional[WishPlan] = None
    result: Optional[WishResult] = None
    thinking_log: list[ThinkingLog] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    priority: int = 5
    max_iterations: int = 50
    current_iteration: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_thought(self, thought: str, action: str = "", result: str = "", is_reflection: bool = False):
        entry = ThinkingLog(
            thought=thought,
            action=action,
            result=result,
            iteration=self.current_iteration,
            is_reflection=is_reflection,
        )
        self.thinking_log.append(entry)
        self.updated_at = time.time()

    def mark_status(self, status: WishStatus):
        self.status = status
        self.updated_at = time.time()