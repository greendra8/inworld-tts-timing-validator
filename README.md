# Inworld TTS Timing Validator

A fast standalone validator for Inworld TTS responses using timestamp metadata and text structure only (no audio decoding).

## What changed

This repo previously used the legacy “severity-gated gap/WPS” implementation.

It now uses **Standalone Variant C**, distilled from reviewed production labels, with one goal:

- catch as many bad segments as possible
- while dramatically reducing false alarms versus the old baseline

## Variant C (current algorithm)

Computed features:

- `max_gap_s`, `mean_gap_s`, `max_gap_pos_ratio`
- `duration_s`, `overall_wps`
- break structure from text: `break_tag_count`, `break_total_s`

Fail when any rule is true:

1. `duration_s <= 4.08`
2. `max_gap_s >= 4.23 AND mean_gap_s >= 0.50`
3. `max_gap_s >= 3.2 AND mean_gap_s <= 0.33 AND break_tag_count >= 8`
4. `2.8 <= max_gap_s <= 3.1 AND 0.35 <= mean_gap_s <= 0.42 AND break_tag_count >= 5 AND duration_s >= 20`
5. Distilled base branch:
   - if `max_gap_s <= 4.79`, fail when `max_gap_pos_ratio > 0.73 AND break_total_s > 3.90`
   - else if `max_gap_s > 4.79`:
     - if `duration_s <= 19.91`, fail when `max_gap_s > 8.93`
     - if `19.91 < duration_s <= 37.08`, fail when `overall_wps <= 1.37`

Else pass.

## Measured outcomes on latest labeled v2 set

| Method | TP | FP | FN | Recall (bad) | FPR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legacy baseline (`validation_failed` flag style) | 34 | 58 | 3 | 91.9% | 54.2% |
| Standalone Variant C | 37 | 9 | 0 | 100.0% | 8.4% |

So Variant C keeps full bad-sample capture on this set while cutting false alarms by ~84.5% vs baseline.

## Quick start

```bash
python -m pip install -e .
python -m pytest -q
python examples/basic_usage.py
```

## Basic usage

```python
from inworld_timing_validator import validate_inworld_timestamps

result = validate_inworld_timestamps(timestamp_info, source_text=segment_text)
if not result.is_valid:
    print("retry tts:", result.reason, result.metrics)
```

## Notes

- This validator is intentionally standalone: no dependency on external “validator reason” labels.
- Thresholds are configurable in `ValidationConfig` if you want environment-specific tuning.
- Continue collecting labeled samples; recalibrate periodically as voice/model behavior drifts.
