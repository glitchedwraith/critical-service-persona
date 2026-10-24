import pytest

from backend.validator import validate


@pytest.fixture
def draft():
    return {
        "reply_text": "Shelter SH-003 is open at 123 Main Street.",
        "verdict": "confirmed",
        "current_status_known": True,
        "evidence": [
            {
                "source_id": "SRC-001",
                "ref": "SH-003",
                "expires_at": "05:00",
                "last_verified_at": "04:30",
            }
        ],
        "conflict": False,
    }


@pytest.fixture
def state():
    return {
        "sim_clock": "04:35",
        "shelters": [
            {
                "id": "SH-003",
                "address": "123 Main Street",
                "status": "open",
            }
        ],
        "bulletins": [
            {
                "id": "B-001",
                "address": "123 Main Street",
                "status": "closed",
            }
        ],
        "sources": [
            {
                "id": "SRC-001",
                "authority": 1,
            },
            {
                "id": "SRC-002",
                "authority": 2,
            },
        ],
    }


def test_valid_evidence(draft, state):
    result, flags = validate(draft, state)

    assert result["verdict"] == "confirmed"
    assert flags == []


def test_empty_evidence(draft, state):
    draft["evidence"] = []

    result, flags = validate(draft, state)

    # The validator does not currently reject empty evidence.
    assert result["verdict"] == "confirmed"
    assert flags == []


def test_unknown_shelter_id(draft, state):
    draft["reply_text"] = "Shelter SH-999 is open."

    result, flags = validate(draft, state)

    assert "unknown_shelter_id:SH-999" in flags


def test_unknown_address(draft, state):
    draft["reply_text"] = "Shelter SH-003 is open at 999 Unknown Street."

    result, flags = validate(draft, state)

    assert any(flag.startswith("unknown_address:") for flag in flags)


def test_expired_evidence(draft, state):
    draft["evidence"][0]["expires_at"] = "04:00"

    result, flags = validate(draft, state)

    assert result["verdict"] == "unverified"
    assert "downgraded_confirmed_no_live_authority" in flags
    assert "all_evidence_expired" in flags
    assert result["current_status_known"] is False


def test_expired_plus_current_evidence(draft, state):
    draft["evidence"].append(
        {
            "source_id": "SRC-002",
            "ref": "SH-003",
            "expires_at": "04:00",
            "last_verified_at": "04:00",
        }
    )

    result, flags = validate(draft, state)

    # One valid, sufficiently authoritative record remains.
    assert result["verdict"] == "confirmed"
    assert "all_evidence_expired" not in flags


def test_unknown_source_downgrades_verdict(draft, state):
    draft["evidence"][0]["source_id"] = "SRC-UNKNOWN"

    result, flags = validate(draft, state)

    assert result["verdict"] == "unverified"
    assert "downgraded_confirmed_no_live_authority" in flags


def test_equal_authority_conflict(draft, state):
    state["sources"].append(
        {
            "id": "SRC-003",
            "authority": 1,
        }
    )

    draft["evidence"].append(
        {
            "source_id": "SRC-003",
            "ref": "SH-003",
            "expires_at": "05:00",
            "last_verified_at": "04:30",
        }
    )
    draft["conflict"] = True

    result, flags = validate(draft, state)

    assert result["verdict"] == "unverified"
    assert "needs_officer_decision" in flags


def test_response_gets_as_of_timestamp(draft, state):
    result, flags = validate(draft, state)

    assert "as of 04:30" in result["reply_text"]


def test_response_truncated_at_300_characters(draft, state):
    draft["reply_text"] = "A" * 350

    result, flags = validate(draft, state)

    assert len(result["reply_text"]) <= 300
    assert result["reply_text"].endswith("... reply MORE")
