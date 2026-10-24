import json
from decimal import Decimal
from unittest.mock import Mock

import pytest

from backend import pipeline


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------

def test_jdumps_serializes_decimal_values():
    result = pipeline._jdumps({
        "whole": Decimal("3"),
        "fraction": Decimal("2.5"),
    })

    assert json.loads(result) == {
        "whole": 3,
        "fraction": 2.5,
    }


def test_jdumps_rejects_unsupported_types():
    with pytest.raises(TypeError, match="not JSON-serializable"):
        pipeline._jdumps({"value": object()})


# ---------------------------------------------------------------------------
# Step 1: extraction
# ---------------------------------------------------------------------------

def test_extract_returns_structured_model_output(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_converse_tool",
        lambda **kwargs: {
            "question_type": "rumor",
            "claims": [
                {
                    "text": "Shelter SH-A is closed",
                    "entity_ids": ["SH-A"],
                }
            ],
            "cluster_match": "R-1",
            "new_cluster_claim": None,
        },
    )

    result = pipeline.extract(
        "Shelter A is closed",
        [{"id": "R-1", "claim": "Shelter A is closed"}],
        ["SH-A", "SH-D"],
    )

    assert result == {
        "question_type": "rumor",
        "claims": [
            {
                "text": "Shelter SH-A is closed",
                "entity_ids": ["SH-A"],
            }
        ],
        "cluster_match": "R-1",
        "new_cluster_claim": None,
    }


def test_extract_removes_unknown_entity_ids(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_converse_tool",
        lambda **kwargs: {
            "question_type": "rumor",
            "claims": [
                {
                    "text": "A shelter is closed",
                    "entity_ids": ["SH-A", "SH-UNKNOWN"],
                }
            ],
            "cluster_match": None,
            "new_cluster_claim": None,
        },
    )

    result = pipeline.extract("Shelter is closed", [], ["SH-A"])

    assert result["claims"][0]["entity_ids"] == ["SH-A"]


def test_extract_rejects_unknown_cluster_match(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_converse_tool",
        lambda **kwargs: {
            "question_type": "rumor",
            "claims": [],
            "cluster_match": "UNKNOWN",
            "new_cluster_claim": None,
        },
    )

    result = pipeline.extract(
        "A rumor",
        [{"id": "R-1", "claim": "Something happened"}],
        [],
    )

    assert result["cluster_match"] is None


def test_extract_uses_heuristic_when_bedrock_fails(monkeypatch):
    def fail_bedrock(**kwargs):
        raise RuntimeError("AWS unavailable")

    monkeypatch.setattr(pipeline, "_converse_tool", fail_bedrock)

    result = pipeline.extract(
        "Is the shelter open?",
        [],
        ["SH-A"],
    )

    assert result["question_type"] == "status_question"
    assert result["cluster_match"] is None
    assert isinstance(result["claims"], list)


def test_heuristic_extract_matches_existing_cluster():
    clusters = [
        {"id": "R-1", "claim": "Shelter A is closed"},
    ]

    result = pipeline._heuristic_extract(
        "Rumor says Shelter A is closed",
        clusters,
        ["SH-A"],
    )

    assert result["question_type"] == "rumor"
    assert result["cluster_match"] == "R-1"
    assert result["new_cluster_claim"] is None
    assert result["claims"][0]["entity_ids"] == ["SH-A"]


def test_heuristic_extract_proposes_new_cluster():
    result = pipeline._heuristic_extract(
        "People say the water is contaminated",
        [],
        [],
    )

    assert result["question_type"] == "rumor"
    assert result["cluster_match"] is None
    assert result["new_cluster_claim"] == "Tap water is contaminated"


def test_heuristic_extract_classifies_unrelated_message():
    result = pipeline._heuristic_extract(
        "Hello, how are you?",
        [],
        [],
    )

    assert result == {
        "question_type": "other",
        "claims": [],
        "cluster_match": None,
        "new_cluster_claim": None,
    }


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def test_render_extract_user_includes_message_and_context():
    result = pipeline._render_extract_user(
        "Is Shelter A closed?",
        [{"id": "R-1"}],
        ["SH-A"],
    )

    assert "Is Shelter A closed?" in result
    assert "R-1" in result
    assert "SH-A" in result
    assert "<resident_message>" in result
    assert "</resident_message>" in result


def test_render_verify_user_filters_unrelated_records():
    rumor = {
        "id": "R-1",
        "entity_ids": ["SH-A"],
        "claim": "Shelter SH-A is closed",
    }
    shelters = [
        {"id": "SH-A", "status": "open"},
        {"id": "SH-D", "status": "closed"},
    ]
    bulletins = [
        {"title": "SH-A status", "body": "SH-A is open"},
        {"title": "SH-D status", "body": "SH-D is closed"},
    ]
    sources = [{"id": "EOC", "authority": 1}]

    result = pipeline._render_verify_user(
        rumor, shelters, bulletins, sources, "04:35"
    )

    assert "04:35" in result
    assert '"SH-A"' in result
    assert '"SH-D"' not in result
    assert "EOC" in result


# ---------------------------------------------------------------------------
# Bedrock Converse plumbing
# ---------------------------------------------------------------------------

def test_converse_tool_returns_matching_tool_input(monkeypatch):
    fake_client = Mock()
    fake_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "record_extraction",
                            "input": {"question_type": "other", "claims": []},
                        }
                    }
                ]
            }
        }
    }

    monkeypatch.setattr(pipeline, "_client", fake_client)

    result = pipeline._converse_tool(
        system="system prompt",
        user="user prompt",
        tool=pipeline._EXTRACT_TOOL,
        tool_name="record_extraction",
    )

    assert result == {"question_type": "other", "claims": []}

    kwargs = fake_client.converse.call_args.kwargs
    assert kwargs["modelId"] == pipeline.DEFAULT_MODEL_ID
    assert kwargs["toolConfig"]["toolChoice"] == {
        "tool": {"name": "record_extraction"}
    }


def test_converse_tool_raises_if_expected_tool_is_missing(monkeypatch):
    fake_client = Mock()
    fake_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "No tool call"}]
            }
        }
    }

    monkeypatch.setattr(pipeline, "_client", fake_client)

    with pytest.raises(RuntimeError, match="missing toolUse"):
        pipeline._converse_tool(
            system="system",
            user="user",
            tool=pipeline._EXTRACT_TOOL,
            tool_name="record_extraction",
        )


# ---------------------------------------------------------------------------
# Step 2: verification orchestration
# ---------------------------------------------------------------------------

@pytest.fixture
def verification_context():
    return {
        "rumor": {
            "id": "R-1",
            "claim": "Shelter SH-003 is open",
            "entity_ids": ["SH-003"],
        },
        "shelters": [
            {"id": "SH-003", "address": "123 Main Street", "status": "open"}
        ],
        "bulletins": [],
        "sources": [
            {"id": "EOC", "authority": 1},
        ],
        "sim_clock": "04:35",
    }


def valid_draft():
    return {
        "verdict": "confirmed",
        "current_status_known": True,
        "evidence": [
            {
                "source_id": "EOC",
                "ref": "B-1",
                "published_at": "04:10",
                "last_verified_at": "04:10",
                "expires_at": "05:00",
            }
        ],
        "reply_text": "Shelter SH-003 is open as of 04:10.",
        "clarification_text": "Shelter SH-003 is open as of 04:10.",
    }


def test_verify_returns_expected_output_shape(
    monkeypatch, verification_context
):
    draft = valid_draft()

    monkeypatch.setattr(
        pipeline, "_attempt_verify", lambda *args, **kwargs: (draft, 25, False)
    )
    monkeypatch.setattr(
        pipeline._validator, "validate", lambda draft, ctx: (draft, [])
    )
    monkeypatch.setattr(
        pipeline._validator, "_source_authority", lambda source_id, sources: 1
    )
    monkeypatch.setattr(
        pipeline._validator, "_not_expired", lambda expires_at, clock: True
    )

    result = pipeline.verify(**verification_context)

    assert result["verdict"] == "confirmed"
    assert result["current_status_known"] is True
    assert result["evidence"] == draft["evidence"]
    assert result["reply_text"] == draft["reply_text"]
    assert result["clarification_text"] == draft["clarification_text"]
    assert result["validator"] == {
        "passed": True,
        "flags": [],
        "fallback_used": False,
    }
    assert result["auto_send_ok"] is True
    assert result["latency_ms"] == 25


def test_verify_retries_when_validator_rejects_first_draft(
    monkeypatch, verification_context
):
    first_draft = valid_draft()
    second_draft = valid_draft()
    second_draft["reply_text"] = "Corrected reply as of 04:10."

    attempts = []

    def fake_attempt(user, retry=False):
        attempts.append(retry)
        return (second_draft if retry else first_draft, 10, False)

    validation_calls = []

    def fake_validate(draft, ctx):
        validation_calls.append(draft)
        if len(validation_calls) == 1:
            return draft, ["test_flag"]
        return draft, []

    monkeypatch.setattr(pipeline, "_attempt_verify", fake_attempt)
    monkeypatch.setattr(pipeline._validator, "validate", fake_validate)
    monkeypatch.setattr(
        pipeline._validator, "_source_authority", lambda source_id, sources: 1
    )
    monkeypatch.setattr(
        pipeline._validator, "_not_expired", lambda expires_at, clock: True
    )

    result = pipeline.verify(**verification_context)

    assert attempts == [False, True]
    assert result["reply_text"] == "Corrected reply as of 04:10."
    assert result["validator"]["passed"] is True
    assert result["validator"]["flags"] == []
    assert result["validator"]["fallback_used"] is False


def test_verify_uses_template_after_both_drafts_fail(
    monkeypatch, verification_context
):
    first_draft = valid_draft()
    fallback_text = "Last official update 04:10 — current status can't be confirmed."

    monkeypatch.setattr(
        pipeline,
        "_attempt_verify",
        lambda *args, **kwargs: (first_draft, 10, False),
    )

    # Both the initial draft and retry are rejected.
    monkeypatch.setattr(
        pipeline._validator,
        "validate",
        lambda draft, ctx: (draft, ["rejected"]),
    )
    monkeypatch.setattr(
        pipeline.templates,
        "cant_confirm",
        lambda clock: fallback_text,
    )

    result = pipeline.verify(**verification_context)

    assert result["verdict"] == "unverified"
    assert result["current_status_known"] is False
    assert result["reply_text"] == fallback_text
    assert result["clarification_text"] == fallback_text
    assert result["validator"]["fallback_used"] is True
    assert result["validator"]["passed"] is False
    assert result["auto_send_ok"] is False


def test_verify_uses_heuristic_if_bedrock_fails(
    monkeypatch, verification_context
):
    monkeypatch.setattr(
        pipeline,
        "_converse_tool",
        Mock(side_effect=RuntimeError("AWS unavailable")),
    )
    monkeypatch.setattr(
        pipeline._validator, "validate", lambda draft, ctx: (draft, [])
    )

    result = pipeline.verify(**verification_context)

    assert result["verdict"] == "unverified"
    assert result["current_status_known"] is False
    assert result["evidence"] == []
    assert result["validator"]["passed"] is True
    assert result["validator"]["fallback_used"] is True
    assert result["auto_send_ok"] is False


# ---------------------------------------------------------------------------
# Automatic-send policy
# ---------------------------------------------------------------------------

def test_auto_send_denied_without_evidence():
    assert pipeline._auto_send_ok(
        {"evidence": []},
        [{"id": "EOC", "authority": 1}],
        "04:35",
    ) is False


def test_auto_send_denied_for_low_authority_source(monkeypatch):
    monkeypatch.setattr(
        pipeline._validator,
        "_source_authority",
        lambda source_id, sources: 4,
    )
    monkeypatch.setattr(
        pipeline._validator,
        "_not_expired",
        lambda expires_at, clock: True,
    )

    assert pipeline._auto_send_ok(
        {
            "evidence": [
                {"source_id": "RESIDENT", "expires_at": "05:00"}
            ]
        },
        [{"id": "RESIDENT", "authority": 4}],
        "04:35",
    ) is False


def test_auto_send_denied_for_expired_evidence(monkeypatch):
    monkeypatch.setattr(
        pipeline._validator,
        "_source_authority",
        lambda source_id, sources: 1,
    )
    monkeypatch.setattr(
        pipeline._validator,
        "_not_expired",
        lambda expires_at, clock: False,
    )

    assert pipeline._auto_send_ok(
        {
            "evidence": [
                {"source_id": "EOC", "expires_at": "04:00"}
            ]
        },
        [{"id": "EOC", "authority": 1}],
        "04:35",
    ) is False


def test_auto_send_allowed_for_authoritative_unexpired_evidence(monkeypatch):
    monkeypatch.setattr(
        pipeline._validator,
        "_source_authority",
        lambda source_id, sources: 2,
    )
    monkeypatch.setattr(
        pipeline._validator,
        "_not_expired",
        lambda expires_at, clock: True,
    )

    assert pipeline._auto_send_ok(
        {
            "evidence": [
                {"source_id": "OFFICIAL", "expires_at": "05:00"}
            ]
        },
        [{"id": "OFFICIAL", "authority": 2}],
        "04:35",
    ) is True
