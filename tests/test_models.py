"""Tests for WishGranter data models."""

import time
import pytest

from wish_granter.models.wish import (
    Wish, WishStatus, WishCategory, WishPlan, WishStep, WishResult,
    ThinkingLog, CapabilityType,
)


class TestWishStatus:
    def test_all_statuses(self):
        assert len(WishStatus) == 9
        assert WishStatus.PENDING.value == "pending"
        assert WishStatus.PLANNING.value == "planning"
        assert WishStatus.EXECUTING.value == "executing"
        assert WishStatus.THINKING.value == "thinking"
        assert WishStatus.PAUSED.value == "paused"
        assert WishStatus.GRANTED.value == "granted"
        assert WishStatus.FAILED.value == "failed"
        assert WishStatus.PARTIAL.value == "partial"
        assert WishStatus.CANCELLED.value == "cancelled"


class TestWishCategory:
    def test_all_categories(self):
        assert len(WishCategory) == 10
        assert WishCategory.INFORMATION.value == "information"
        assert WishCategory.CODE.value == "code"
        assert WishCategory.FILE.value == "file"
        assert WishCategory.ANALYSIS.value == "analysis"
        assert WishCategory.WEB.value == "web"
        assert WishCategory.AUTOMATION.value == "automation"
        assert WishCategory.CREATIVE.value == "creative"
        assert WishCategory.KNOWLEDGE.value == "knowledge"
        assert WishCategory.COMPOUND.value == "compound"
        assert WishCategory.UNKNOWN.value == "unknown"


class TestCapabilityType:
    def test_all_capability_types(self):
        assert len(CapabilityType) == 7
        assert CapabilityType.WEB_SEARCH.value == "web_search"
        assert CapabilityType.CODE_GEN.value == "code_gen"
        assert CapabilityType.FILE_IO.value == "file_io"
        assert CapabilityType.DATA_ANALYSIS.value == "data_analysis"
        assert CapabilityType.WEB_SCRAPER.value == "web_scraper"
        assert CapabilityType.SHELL.value == "shell"
        assert CapabilityType.KNOWLEDGE.value == "knowledge"


class TestWishStep:
    def test_create_step(self):
        step = WishStep(
            description="Search the web",
            capability=CapabilityType.WEB_SEARCH,
            params={"query": "quantum computing"},
        )
        assert step.description == "Search the web"
        assert step.capability == CapabilityType.WEB_SEARCH
        assert step.status == WishStatus.PENDING
        assert step.retries == 0
        assert step.max_retries == 3
        assert len(step.step_id) == 8

    def test_mark_started(self):
        step = WishStep(description="test", capability=CapabilityType.KNOWLEDGE)
        step.mark_started()
        assert step.status == WishStatus.EXECUTING
        assert step.started_at is not None

    def test_mark_completed(self):
        step = WishStep(description="test", capability=CapabilityType.KNOWLEDGE)
        step.mark_started()
        step.mark_completed({"answer": "42"})
        assert step.status == WishStatus.GRANTED
        assert step.result == {"answer": "42"}
        assert step.completed_at is not None

    def test_mark_failed_retry(self):
        step = WishStep(description="test", capability=CapabilityType.KNOWLEDGE, max_retries=3)
        step.mark_started()
        step.mark_failed("timeout")
        assert step.retries == 1
        assert step.status == WishStatus.PENDING  # still has retries

    def test_mark_failed_exhausted(self):
        step = WishStep(description="test", capability=CapabilityType.KNOWLEDGE, max_retries=1)
        step.retries = 1
        step.mark_failed("timeout")
        assert step.status == WishStatus.FAILED


class TestWishPlan:
    def test_create_plan(self):
        plan = WishPlan(
            wish_text="I wish to learn Python",
            category=WishCategory.INFORMATION,
            steps=[
                WishStep(description="Search web", capability=CapabilityType.WEB_SEARCH, params={"query": "learn Python"}),
                WishStep(description="Summarize", capability=CapabilityType.KNOWLEDGE, params={"action": "summarize"}),
            ],
            reasoning="Find Python resources and summarize",
        )
        assert plan.total_steps == 2
        assert plan.completed_steps == 0
        assert plan.progress_pct == 0.0
        assert plan.revision == 1

    def test_progress(self):
        plan = WishPlan(
            wish_text="test",
            steps=[
                WishStep(description="s1", capability=CapabilityType.KNOWLEDGE),
                WishStep(description="s2", capability=CapabilityType.KNOWLEDGE),
                WishStep(description="s3", capability=CapabilityType.KNOWLEDGE),
            ],
        )
        plan.steps[0].status = WishStatus.GRANTED
        plan.steps[1].status = WishStatus.GRANTED
        assert plan.completed_steps == 2
        assert plan.progress_pct == pytest.approx(66.67, rel=0.01)


class TestThinkingLog:
    def test_create_log(self):
        log = ThinkingLog(thought="Analyzing wish", action="plan", result="Plan created")
        assert log.thought == "Analyzing wish"
        assert log.action == "plan"
        assert log.iteration == 0
        assert log.is_reflection is False


class TestWish:
    def test_create_wish(self):
        wish = Wish(text="I wish to understand quantum mechanics")
        assert wish.text == "I wish to understand quantum mechanics"
        assert wish.status == WishStatus.PENDING
        assert wish.priority == 5
        assert wish.max_iterations == 50
        assert len(wish.wish_id) == 12
        assert len(wish.thinking_log) == 0

    def test_add_thought(self):
        wish = Wish(text="test wish")
        wish.add_thought("First thought", action="think", result="thought result")
        assert len(wish.thinking_log) == 1
        assert wish.thinking_log[0].thought == "First thought"
        assert wish.thinking_log[0].is_reflection is False

    def test_add_reflection(self):
        wish = Wish(text="test wish")
        wish.add_thought("Reflecting...", is_reflection=True)
        assert wish.thinking_log[0].is_reflection is True

    def test_mark_status(self):
        wish = Wish(text="test wish")
        wish.mark_status(WishStatus.PLANNING)
        assert wish.status == WishStatus.PLANNING
        assert wish.updated_at > wish.created_at


class TestWishResult:
    def test_create_result(self):
        result = WishResult(
            wish_id="abc123",
            status=WishStatus.GRANTED,
            summary="Wish granted successfully",
            total_iterations=5,
            total_time_seconds=12.5,
            plan_revisions=1,
        )
        assert result.status == WishStatus.GRANTED
        assert result.total_iterations == 5