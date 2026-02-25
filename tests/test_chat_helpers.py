"""
Unit tests for the response cleaner and response sanitiser helpers
in backend/routers/chat.py (no external services needed).
"""
import pytest
from backend.routers.chat import _clean_response, _sanitize_log


class TestCleanResponse:
    def test_strips_python_tag(self):
        raw = "Hello <|python_tag|> some stuff after"
        assert "<|python_tag|>" not in _clean_response(raw)

    def test_strips_function_tags(self):
        raw = "Hello <function name=\"foo\">args</function> world"
        result = _clean_response(raw)
        assert "<function" not in result

    def test_strips_special_tokens(self):
        raw = "text <|endoftext|> more"
        assert "<|" not in _clean_response(raw)

    def test_strips_websearch_artifact(self):
        raw = "Let me websearch that for you"
        assert "websearch" not in _clean_response(raw).lower()

    def test_strips_web_search_artifact(self):
        raw = "web_search({\"query\": \"GDP India 2024\"})"
        assert "web_search" not in _clean_response(raw)

    def test_preserves_normal_text(self):
        raw = "ARIA is an AI business advisor."
        assert _clean_response(raw) == raw

    def test_returns_stripped_string(self):
        assert _clean_response("  hello  ") == "hello"

    def test_empty_string(self):
        assert _clean_response("") == ""


class TestSanitizeLog:
    def test_maps_known_category(self):
        entry = {"category": "tool_start", "message": "Searching", "timestamp": 0}
        result = _sanitize_log(entry)
        assert result["icon"] == "🔎"
        assert result["label"] == "Searching Web"

    def test_falls_back_for_unknown_category(self):
        entry = {"category": "unknown_cat", "message": "foo", "timestamp": 0}
        result = _sanitize_log(entry)
        assert result["icon"] == "💭"
        assert result["label"] == "Thinking"

    def test_replaces_nvidia_nim(self):
        entry = {"category": "api_call", "message": "Connecting to NVIDIA NIM", "timestamp": 0}
        result = _sanitize_log(entry)
        assert "NVIDIA NIM" not in result["message"]
        assert "AI Service" in result["message"]

    def test_preserves_timestamp(self):
        entry = {"category": "thinking", "message": "hi", "timestamp": 12345.6}
        assert _sanitize_log(entry)["timestamp"] == 12345.6
