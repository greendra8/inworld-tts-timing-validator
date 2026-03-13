# Inworld TTS Timing Validator

A small, fast, timing-only validator for Inworld TTS responses.

It catches common glitch patterns from timestamp metadata (no audio decoding needed):
- repeated/looped pauses
- break-boundary duration anomalies
- suspicious opening-word pause pattern
- compressed/truncated pacing spikes

This implementation was tuned from real labeled samples and is designed to run on hundreds of segments in seconds.

## Why this exists

Inworld can occasionally return audio that sounds wrong while still returning a valid response.

Timing metadata (`wordAlignment`) is cheap to validate and gives a good first-pass filter before expensive audio checks.

## What is the core improvement?

Many pause-related false positives come from natural speaking pauses.

So pause-family failures (gap/break/initial-gap) are only enforced when a segment-level severity gate is met:

```text
max_word_duration >= 1.4
OR
(max_gap >= 3.0 AND max_word_duration / median_word_duration >= 2.0)
```

This reduced false positives on our labeled set while keeping bad-sample recall unchanged.

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
    print("retry tts:", result.reason)
```

## Included dataset

This repo includes a curated dataset:

- `datasets/validation_failures.json`

It contains labeled fail examples with:
- voice/model metadata (`voice_id`, `model_id`, `temperature`, `speaking_rate`)
- prompt excerpts
- failure category (`repeated_words_or_pause_loop`, `dragged_out_characters`)
- timing metrics (`max_gap`, `max_word_duration`, `max_word_ratio`)

## Config knobs

All thresholds live in `ValidationConfig`:

- `max_gap_seconds`, `max_gap_after_sentence_seconds`
- `break_word_duration_ratio`, `break_word_min_seconds`
- `initial_gap_*`
- `wps_ratio_threshold`, `window_size`
- `anomaly_min_max_word_seconds`
- `anomaly_min_gap_seconds`
- `anomaly_min_word_ratio`

## How to apply this in your project

1. Call validator immediately after each TTS response.
2. On `invalid`, retry generation (bounded retry count).
3. Log `reason` + metrics for calibration.
4. Sample and label both passing and failing outputs weekly.
5. Re-tune thresholds by provider/voice/content-type if needed.

## Costs and benefits

### Benefits

- **Very fast**: O(n words), no waveform processing.
- **Simple rollout**: pure Python + timestamp JSON.
- **High recall oriented** when tuned against your labels.

### Costs / limitations

- **Needs labeled data** to tune well.
- **Not universal**: thresholds can drift by voice/model/content style.
- **Timing-only blind spots**: some audio defects need waveform checks.
- **Trade-off remains**: improving precision can reduce recall if over-tuned.
