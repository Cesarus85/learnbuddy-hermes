"""Tests for the two-stage child-intent classifier."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from learnbuddy_core.child_intent import (
    IntentClassifierConfig,
    _normalize,
    _parse_llm_response,
    classify_child_intent,
    classify_preflight,
    classify_semantic,
)


# ---------------------------------------------------------------------------
# Preflight / phrase-based tests
# ---------------------------------------------------------------------------


class TestPreflightExactMatch:
    """Exact phrase matches from the original watcher phrase lists."""

    @pytest.mark.parametrize(
        "text,intent",
        [
            ("Nochmal", "repeat"),
            ("nochmal bitte", "repeat"),
            ("Noch mal", "repeat"),
            ("Bitte nochmal", "repeat"),
            ("Wiederholen", "repeat"),
            ("Nochmal senden", "repeat"),
            ("Hilfe", "help"),
            ("Ich weiß nicht", "help"),
            ("Ich weiss nicht", "help"),
            ("Keine Ahnung", "help"),
            ("Ich komme nicht weiter", "help"),
            ("Ich brauche Hilfe", "help"),
            ("Noch eine", "next"),
            ("noch eine bitte", "next"),
            ("Noch ne", "next"),
            ("Nächste", "next"),
            ("Neue Aufgabe", "next"),
            ("Noch eine Aufgabe", "next"),
            ("Noch ne Aufgabe", "next"),
            ("Weiter", "next"),
        ],
    )
    def test_exact_match(self, text, intent):
        assert classify_preflight(text) == intent

    @pytest.mark.parametrize(
        "text",
        [
            "42",
            "das Haus",
            "201",
            "Bonjour",
            "Ich habe fertig",
            "Der Apfel ist rot",
        ],
    )
    def test_not_a_control_message(self, text):
        assert classify_preflight(text) is None

    def test_empty_string(self):
        assert classify_preflight("") is None

    def test_whitespace_only(self):
        assert classify_preflight("   ") is None

    def test_punctuation_stripped(self):
        assert classify_preflight("Nochmal!!!") == "repeat"
        assert classify_preflight("Hilfe???") == "help"
        assert classify_preflight("Noch eine.") == "next"

    def test_case_insensitive(self):
        assert classify_preflight("NOCHMAL") == "repeat"
        assert classify_preflight("HILFE") == "help"
        assert classify_preflight("NOCH EINE") == "next"

    def test_extra_whitespace_collapsed(self):
        assert classify_preflight("  Nochmal   bitte  ") == "repeat"
        assert classify_preflight("  Noch   eine  ") == "next"


class TestPreflightNewPhrases:
    """Phrases added in the child_intent module beyond the original lists."""

    @pytest.mark.parametrize(
        "text,intent",
        [
            ("Weiter bitte", "next"),
            ("Noch mehr", "next"),
            ("Mehr bitte", "next"),
            ("Noch eins", "next"),
            ("Nächstes", "next"),
            ("Zeig nochmal", "repeat"),
            ("Nochmal die Aufgabe", "repeat"),
        ],
    )
    def test_extended_phrases(self, text, intent):
        assert classify_preflight(text) == intent


class TestNormalize:
    def test_umlaut_normalization(self):
        assert _normalize("Nächste") == "naechste"
        assert _normalize("Übung") == "uebung"
        assert _normalize("Öffnen") == "oeffnen"

    def test_sharp_s(self):
        assert _normalize("groß") == "gross"


# ---------------------------------------------------------------------------
# Semantic (LLM) classifier tests
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    def test_valid_repeat(self):
        assert _parse_llm_response({"choices": [{"message": {"content": "repeat"}}]}) == "repeat"

    def test_valid_help(self):
        assert _parse_llm_response({"choices": [{"message": {"content": "help"}}]}) == "help"

    def test_valid_next(self):
        assert _parse_llm_response({"choices": [{"message": {"content": "next"}}]}) == "next"

    def test_answer_returns_none(self):
        assert _parse_llm_response({"choices": [{"message": {"content": "answer"}}]}) is None

    def test_garbage_returns_none(self):
        assert _parse_llm_response({"choices": [{"message": {"content": "banana"}}]}) is None

    def test_empty_choices(self):
        assert _parse_llm_response({"choices": []}) is None

    def test_no_choices(self):
        assert _parse_llm_response({}) is None

    def test_case_insensitive(self):
        assert _parse_llm_response({"choices": [{"message": {"content": "Repeat"}}]}) == "repeat"


class TestSemanticClassifier:
    def test_disabled_returns_none(self, monkeypatch):
        config = IntentClassifierConfig(enabled=False)
        assert classify_semantic("Ich will noch was rechnen", config) is None

    def test_missing_api_key_returns_none(self, monkeypatch):
        config = IntentClassifierConfig(enabled=True, api_key_env="NONEXISTENT_KEY")
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        assert classify_semantic("Ich will noch was rechnen", config) is None

    def test_llm_returns_repeat(self, monkeypatch):
        config = IntentClassifierConfig(enabled=True, api_key_env="TEST_KEY")
        monkeypatch.setenv("TEST_KEY", "test-secret")

        def fake_transport(url, payload, request, timeout):
            assert "Bearer test-secret" in request.get_header("Authorization")
            return {"choices": [{"message": {"content": "next"}}]}

        result = classify_semantic("ich will noch was machen", config, transport=fake_transport)
        assert result == "next"

    def test_llm_returns_answer_treated_as_none(self, monkeypatch):
        config = IntentClassifierConfig(enabled=True, api_key_env="TEST_KEY")
        monkeypatch.setenv("TEST_KEY", "test-secret")

        def fake_transport(url, payload, request, timeout):
            return {"choices": [{"message": {"content": "answer"}}]}

        result = classify_semantic("42", config, transport=fake_transport)
        assert result is None

    def test_llm_failure_returns_none(self, monkeypatch):
        config = IntentClassifierConfig(enabled=True, api_key_env="TEST_KEY")
        monkeypatch.setenv("TEST_KEY", "test-secret")

        def failing_transport(url, payload, request, timeout):
            raise ConnectionError("network down")

        result = classify_semantic("irgendwas", config, transport=failing_transport)
        assert result is None


# ---------------------------------------------------------------------------
# Unified two-stage classifier tests
# ---------------------------------------------------------------------------


class TestClassifyChildIntent:
    def test_preflight_hit_skips_llm(self, monkeypatch):
        """If preflight matches, LLM is never called."""
        config = IntentClassifierConfig(enabled=True, api_key_env="TEST_KEY")
        monkeypatch.setenv("TEST_KEY", "test-secret")

        call_count = 0

        def counting_transport(url, payload, request, timeout):
            nonlocal call_count
            call_count += 1
            return {"choices": [{"message": {"content": "help"}}]}

        result = classify_child_intent("Nochmal", config, transport=counting_transport)
        assert result == "repeat"
        assert call_count == 0

    def test_preflight_miss_uses_llm(self, monkeypatch):
        """If preflight misses and LLM is configured, LLM is consulted."""
        config = IntentClassifierConfig(enabled=True, api_key_env="TEST_KEY")
        monkeypatch.setenv("TEST_KEY", "test-secret")

        def fake_transport(url, payload, request, timeout):
            return {"choices": [{"message": {"content": "next"}}]}

        result = classify_child_intent("ich will noch was rechnen", config, transport=fake_transport)
        assert result == "next"

    def test_preflight_miss_no_config_returns_none(self):
        result = classify_child_intent("ich will noch was rechnen")
        assert result is None

    def test_preflight_miss_llm_returns_none(self, monkeypatch):
        config = IntentClassifierConfig(enabled=True, api_key_env="TEST_KEY")
        monkeypatch.setenv("TEST_KEY", "test-secret")

        def fake_transport(url, payload, request, timeout):
            return {"choices": [{"message": {"content": "answer"}}]}

        result = classify_child_intent("Hallo!", config, transport=fake_transport)
        assert result is None


class TestSemanticFreeformCases:
    """Real-world-ish freeform child messages that the phrase list misses."""

    @pytest.mark.parametrize(
        "text,expected_intent",
        [
            ("ich will noch was rechnen", "next"),
            ("kann ich noch eins machen", "next"),
            ("bitte noch eine runde", "next"),
            ("ich checks nicht", "help"),
            ("ganz schwer das", "help"),
            ("kannst du mir helfen", "help"),
            ("zeige mal die aufgabe", "repeat"),
            ("was war die frage nochmal", "repeat"),
        ],
    )
    def test_llm_classifies_freeform(self, text, expected_intent, monkeypatch):
        config = IntentClassifierConfig(enabled=True, api_key_env="TEST_KEY")
        monkeypatch.setenv("TEST_KEY", "test-secret")

        def fake_transport(url, payload, request, timeout):
            # Simulate LLM returning the expected intent
            return {"choices": [{"message": {"content": expected_intent}}]}

        result = classify_child_intent(text, config, transport=fake_transport)
        assert result == expected_intent
