"""Tests for the web API."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from wish_granter.models.wish import Wish, WishStatus, WishCategory
from wish_granter.engine import WishGranter, WishGranterConfig
from wish_granter.web.app import create_app


@pytest.fixture
def config():
    return WishGranterConfig(
        api_url="http://localhost:11434/v1/chat/completions",
        api_key="test-key",
        model="test-model",
        max_iterations=3,
    )


@pytest.fixture
def app(config):
    return create_app(config)


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAPI:
    def test_root_dashboard(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "WishGranter" in resp.text

    def test_status(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "0.1.0"
        assert data["total_wishes"] == 0
        assert "capabilities" in data

    def test_capabilities(self, client):
        resp = client.get("/api/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "web_search" in data
        assert "code_gen" in data
        assert "knowledge" in data

    def test_list_wishes_empty(self, client):
        resp = client.get("/api/wishes")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_get_nonexistent_wish(self, client):
        resp = client.get("/api/wish/nonexistent")
        assert resp.status_code == 404

    def test_cancel_nonexistent_wish(self, client):
        resp = client.post("/api/wish/nonexistent/cancel")
        assert resp.status_code == 404

    def test_pause_nonexistent_wish(self, client):
        resp = client.post("/api/wish/nonexistent/pause")
        assert resp.status_code == 400

    def test_resume_nonexistent_wish(self, client):
        resp = client.post("/api/wish/nonexistent/resume")
        assert resp.status_code == 400