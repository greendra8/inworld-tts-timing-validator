from inworld_timing_validator import ValidationConfig, validate_inworld_timestamps


def test_mismatched_arrays_fail():
    result = validate_inworld_timestamps(
        {
            "wordAlignment": {
                "words": ["hello", "world"],
                "wordStartTimeSeconds": [0.0, 0.5],
                "wordEndTimeSeconds": [0.4],
            }
        }
    )
    assert result.is_valid is False
    assert "Mismatched array lengths" in result.reason


def test_short_segment_rule_fails():
    timestamp_info = {
        "wordAlignment": {
            "words": ["one", "more", "time", "now"],
            "wordStartTimeSeconds": [0.0, 1.1, 2.2, 3.1],
            "wordEndTimeSeconds": [0.3, 1.4, 2.5, 3.4],
        }
    }
    result = validate_inworld_timestamps(timestamp_info)
    assert result.is_valid is False
    assert "short segment risk" in result.reason


def test_strong_gap_profile_fails():
    timestamp_info = {
        "wordAlignment": {
            "words": ["Breathe", "in", "slowly", "Breathe", "out", "slowly"],
            "wordStartTimeSeconds": [0.0, 2.6, 2.9, 7.8, 8.1, 8.4],
            "wordEndTimeSeconds": [2.2, 2.8, 3.1, 8.0, 8.3, 8.7],
        }
    }
    result = validate_inworld_timestamps(timestamp_info)
    assert result.is_valid is False
    assert "Gap profile risk" in result.reason


def test_dense_break_moderate_gap_rule_fails():
    words = [f"w{i}" for i in range(20)]
    starts = []
    ends = []
    t = 0.0
    for i in range(20):
        starts.append(round(t, 2))
        ends.append(round(t + 0.25, 2))
        t += 0.25
        if i == 8:
            t += 3.2

    timestamp_info = {
        "wordAlignment": {
            "words": words,
            "wordStartTimeSeconds": starts,
            "wordEndTimeSeconds": ends,
        }
    }
    source_text = " ".join([f"w{i}<break time=\"600ms\" />" for i in range(12)])
    result = validate_inworld_timestamps(timestamp_info, source_text=source_text)
    assert result.is_valid is False
    assert "Structured-break gap risk" in result.reason


def test_medium_band_rule_fails():
    n = 60
    words = [f"m{i}" for i in range(n)]
    starts = []
    ends = []
    t = 0.0
    for _ in range(n):
        starts.append(round(t, 2))
        ends.append(round(t + 0.2, 2))
        t += 0.55
    for j in range(21, n):
        starts[j] += 2.55
        ends[j] += 2.55

    timestamp_info = {
        "wordAlignment": {
            "words": words,
            "wordStartTimeSeconds": starts,
            "wordEndTimeSeconds": ends,
        }
    }
    source_text = " ".join([f"m{i}<break time=\"600ms\" />" for i in range(10)])
    result = validate_inworld_timestamps(timestamp_info, source_text=source_text)
    assert result.is_valid is False
    assert "Medium-band pacing risk" in result.reason


def test_normal_segment_passes():
    timestamp_info = {
        "wordAlignment": {
            "words": ["That", "is", "a", "steady", "gentle", "breath", "now", "continue", "softly", "here", "and", "settle"],
            "wordStartTimeSeconds": [0.0, 0.6, 1.1, 1.6, 2.1, 2.6, 3.1, 3.6, 4.1, 4.6, 5.1, 5.6],
            "wordEndTimeSeconds": [0.3, 0.9, 1.4, 1.9, 2.4, 2.9, 3.4, 3.9, 4.4, 4.9, 5.4, 5.9],
        }
    }
    result = validate_inworld_timestamps(timestamp_info)
    assert result.is_valid is True
    assert result.reason == "Valid"


def test_config_override_works_for_short_segment_threshold():
    timestamp_info = {
        "wordAlignment": {
            "words": ["one", "more", "time", "now"],
            "wordStartTimeSeconds": [0.0, 1.1, 2.2, 3.1],
            "wordEndTimeSeconds": [0.3, 1.4, 2.5, 3.4],
        }
    }
    # Default should fail (short segment). Raising threshold lower should allow pass.
    strict = validate_inworld_timestamps(
        timestamp_info,
        config=ValidationConfig(short_segment_max_seconds=2.0),
    )
    assert strict.is_valid is True
