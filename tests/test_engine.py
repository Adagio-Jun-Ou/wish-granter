"""Tests for the WishGranter engine."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from wish_granter.engine import WishGranter, WishGranterConfig
from wish_granter.models.wish import Wish, WishStatus, WishCategory, WishPlan, WishStep, CapabilityType
from wish_granter.capabilities.base import CapabilityResult


class TestWishGranterConfig:
    def test_default_config(self):
        config = WishGranterConfig()
        assert config.api_url == "https://api.ohmyapi.com/v1/chat/completions"
        assert config.model == "glm-5.1"
        assert config.max_iterations == 50

    def test_custom_config(self):
        config = WishGranterConfig(api_url="http://localhost:11434/v1/chat/completions", model="qwen2.5:3b")
        assert config.api_url == "http://localhost:11434/v1/chat/completions"
        assert config.model == "qwen2.5:3b"


class TestWishGranter:
    @pytest.fixture
    def granter(self):
        return WishGranter(WishGranterConfig(
            api_url="http://localhost:11434/v1/chat/completions",
            api_key="test",
            model="test-model",
            max_iterations=5,
        ))

    def test_initialization(self, granter):
        assert len(granter.capabilities) == 7
        assert "web_search" in granter.capabilities
        assert "code_gen" in granter.capabilities
        assert "file_io" in granter.capabilities
        assert "data_analysis" in granter.capabilities
        assert "web_scraper" in granter.capabilities
        assert "shell" in granter.capabilities
        assert "knowledge" in granter.capabilities

    def test_get_wish_not_found(self, granter):
        assert granter.get_wish("nonexistent") is None

    def test_list_wishes_empty(self, granter):
        assert granter.list_wishes() == []

    @pytest.mark.asyncio
    async def test_cancel_wish(self, granter):
        wish = Wish(text="test wish")
        granter.wishes[wish.wish_id] = wish
        result = await granter.cancel_wish(wish.wish_id)
        assert result is True
        assert wish.status == WishStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, granter):
        result = await granter.cancel_wish("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_pause_resume_wish(self, granter):
        wish = Wish(text="test wish")
        wish.status = WishStatus.EXECUTING
        granter.wishes[wish.wish_id] = wish

        paused = await granter.pause_wish(wish.wish_id)
        assert paused is True
        assert wish.status == WishStatus.PAUSED

        resumed = await granter.resume_wish(wish.wish_id)
        assert resumed is not None
        assert resumed.status == WishStatus.EXECUTING

    def test_parse_json_valid(self, granter):
        result = WishGranter._parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_in_code_block(self, granter):
        text = '```json\n{"key": "value"}\n```'
        result = WishGranter._parse_json(text)
        assert result == {"key": "value"}

    def test_parse_json_invalid(self, granter):
        result = WishGranter._parse_json("not json at all")
        assert result is None

    def test_event_handler_registration(self, granter):
        handler_called = []
        def handler(data):
            handler_called.append(data)

        granter.on("test_event", handler)
        assert "test_event" in granter._event_handlers
        assert len(granter._event_handlers["test_event"]) == 1

    @pytest.mark.asyncio
    async def test_grant_wish_integration(self, granter):
        async def mock_llm(system, user, temperature=0.5):
            if "plan" in system.lower() or "wish" in system.lower():
                return json.dumps({
                    "category": "knowledge",
                    "steps": [
                        {"description": "Research the topic", "capability": "knowledge", "params": {"action": "ask", "query": "test query"}, "reasoning": "Direct knowledge query"}
                    ],
                    "reasoning": "Use knowledge capability",
                    "success_criteria": "Response is informative"
                })
            elif "reflect" in system.lower():
                return json.dumps({
                    "status": "granted",
                    "granted": True,
                    "progress_pct": 100,
                    "analysis": "Wish fulfilled",
                    "next_steps": [],
                    "plan_revision": None,
                    "reflection": "The wish has been granted"
                })
            else:
                return "Your wish has been granted. Here is the comprehensive answer."

        with patch.object(granter, "_call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = mock_llm

            with patch.object(granter.capabilities["knowledge"], "execute", new_callable=AsyncMock) as mock_cap:
                mock_cap.return_value = CapabilityResult(
                    success=True,
                    data={"answer": "Comprehensive response", "query": "test query"},
                    capability_name="knowledge",
                )

                wish = await granter.grant_wish("I wish to learn about AI", priority=7)
                assert wish.wish_id in granter.wishes
                assert wish.text == "I wish to learn about AI"
                assert wish.priority == 7
                assert len(wish.thinking_log) > 0


class TestWishStepExecution:
    @pytest.fixture
    def granter(self):
        config = WishGranterConfig(
            api_url="http://localhost:11434/v1/chat/completions",
            max_iterations=3,
        )
        return WishGranter(config)

    @pytest.mark.asyncio
    async def test_execute_step_unknown_capability(self, granter):
        step = WishStep(description="test", capability=CapabilityType.KNOWLEDGE, params={"action": "ask", "query": "test"})
        step.capability = CapabilityType.KNOWLEDGE

        with patch.object(granter.capabilities["knowledge"], "execute", new_callable=AsyncMock) as mock:
            mock.return_value = CapabilityResult(success=True, data={"answer": "42"})
            result = await granter._execute_step(Wish(text="test"), step)
            assert result.success