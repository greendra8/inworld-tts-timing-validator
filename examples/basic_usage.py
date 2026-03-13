from inworld_timing_validator import validate_inworld_timestamps

timestamp_info = {
    "wordAlignment": {
        "words": ["Two", "a", "little", "more", "awareness"],
        "wordStartTimeSeconds": [0.15, 3.10, 3.40, 3.70, 4.00],
        "wordEndTimeSeconds": [1.95, 3.40, 3.70, 4.00, 4.35],
    }
}

result = validate_inworld_timestamps(
    timestamp_info,
    source_text='Two<break time="1s" /> a little more awareness',
)

print(f"valid={result.is_valid} reason={result.reason}")
if result.metrics:
    print(result.metrics)

