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


def test_moderate_gap_can_pass_due_to_severity_gate():
    timestamp_info = {
        "wordAlignment": {
            "words": ["Breathe", "in", "slowly", "Breathe", "out", "slowly"],
            "wordStartTimeSeconds": [0.0, 0.45, 0.75, 3.55, 3.95, 4.25],
            "wordEndTimeSeconds": [0.35, 0.65, 1.05, 3.85, 4.15, 4.55],
        }
    }

    result = validate_inworld_timestamps(timestamp_info)
    assert result.is_valid is True

    # Optional strict mode: disable the severity gate and this shape fails.
    strict = validate_inworld_timestamps(
        timestamp_info,
        config=ValidationConfig(
            anomaly_min_max_word_seconds=0.0,
            anomaly_min_gap_seconds=0.0,
            anomaly_min_word_ratio=0.0,
        ),
    )
    assert strict.is_valid is False
    assert "Gap too large" in strict.reason


def test_severe_gap_still_fails():
    timestamp_info = {
        "wordAlignment": {
            "words": ["Breathe", "in", "slowly", "Breathe", "out", "slowly"],
            "wordStartTimeSeconds": [0.0, 2.6, 2.9, 7.8, 8.1, 8.4],
            "wordEndTimeSeconds": [2.2, 2.8, 3.1, 8.0, 8.3, 8.7],
        }
    }
    result = validate_inworld_timestamps(
        timestamp_info,
        source_text='Breathe in slowly <break time="1s" /> Breathe out slowly.',
    )
    assert result.is_valid is False
    assert "Gap too large" in result.reason


def test_wps_spike_still_fails():
    timestamp_info = {
        "wordAlignment": {
            "words": [
                "If", "you", "lose", "count,", "just", "begin", "again", "at", "one.",
                "If", "you", "lose", "count,", "just", "begin", "again", "at", "one.",
                "This", "is", "the", "end", "of", "the", "audio."
            ],
            "wordStartTimeSeconds": [
                0, 0.201, 0.422, 0.723, 1.447, 2.029, 2.391, 2.692, 2.994,
                3.154, 3.697, 3.898, 4.199, 4.902, 5.445, 5.847, 6.007, 6.068,
                6.168, 6.269, 6.329, 6.409, 6.49, 6.55, 6.63
            ],
            "wordEndTimeSeconds": [
                0.161, 0.362, 0.643, 1.065, 1.788, 2.331, 2.652, 2.793, 3.114,
                3.677, 3.858, 4.119, 4.541, 5.224, 5.766, 5.987, 6.048, 6.148,
                6.248, 6.309, 6.389, 6.469, 6.53, 6.61, 6.751
            ],
        }
    }
    result = validate_inworld_timestamps(timestamp_info)
    assert result.is_valid is False
    assert "WPS spike" in result.reason

