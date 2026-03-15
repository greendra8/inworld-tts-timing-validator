from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


BREAK_TIME_PATTERN = re.compile(
    r"<break\s+time\s*=\s*['\"](?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s)['\"]\s*/?>",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationConfig:
    """
    Standalone Variant C thresholds distilled from labeled production data.

    Defaults are intentionally concrete to match the calibrated ruleset.
    """

    short_segment_max_seconds: float = 4.08

    strong_gap_max_gap_seconds: float = 4.23
    strong_gap_mean_gap_seconds: float = 0.50

    dense_break_gap_max_gap_seconds: float = 3.2
    dense_break_gap_mean_gap_seconds: float = 0.33
    dense_break_min_break_tags: int = 8

    medium_band_min_gap_seconds: float = 2.8
    medium_band_max_gap_seconds: float = 3.1
    medium_band_min_mean_gap_seconds: float = 0.35
    medium_band_max_mean_gap_seconds: float = 0.42
    medium_band_min_break_tags: int = 5
    medium_band_min_duration_seconds: float = 20.0

    # Distilled base branch (surrogate of grouped HGB @ 0.5)
    base_split_max_gap_seconds: float = 4.79
    base_split_max_gap_pos_ratio: float = 0.73
    base_split_break_total_seconds: float = 3.90

    base_hi_gap_split_duration_seconds: float = 19.91
    base_hi_gap_max_gap_seconds: float = 8.93
    base_mid_duration_seconds: float = 37.08
    base_mid_overall_wps_max: float = 1.37


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str
    metrics: dict[str, float] | None = None


def _extract_break_summary(source_text: str | None) -> tuple[int, float, float]:
    if not source_text:
        return 0, 0.0, 0.0

    values: list[float] = []
    for match in BREAK_TIME_PATTERN.finditer(source_text):
        try:
            raw = float(match.group("value"))
        except (TypeError, ValueError):
            continue
        if raw <= 0:
            continue

        unit = (match.group("unit") or "s").lower()
        seconds = raw / 1000.0 if unit == "ms" else raw
        values.append(seconds)

    if not values:
        return 0, 0.0, 0.0

    return len(values), float(sum(values)), float(max(values))


def validate_inworld_timestamps(
    timestamp_info: dict[str, Any] | None,
    source_text: str | None = None,
    config: ValidationConfig = ValidationConfig(),
) -> ValidationResult:
    """Validate Inworld word timing metadata using standalone Variant C."""
    if not timestamp_info:
        return ValidationResult(True, "No timestamp info provided")

    alignment = timestamp_info.get("wordAlignment", {})
    words = alignment.get("words", [])
    starts = alignment.get("wordStartTimeSeconds", [])
    ends = alignment.get("wordEndTimeSeconds", [])

    if not words:
        return ValidationResult(True, "Empty word list")
    if len(words) != len(starts) or len(words) != len(ends):
        return ValidationResult(
            False,
            f"Mismatched array lengths: words={len(words)}, starts={len(starts)}, ends={len(ends)}",
        )

    count = len(words)
    starts_f = [float(v) for v in starts]
    ends_f = [float(v) for v in ends]
    duration_s = ends_f[-1] - starts_f[0]
    if duration_s <= 0:
        return ValidationResult(True, "Zero duration segment")

    gaps = [max(starts_f[i + 1] - ends_f[i], 0.0) for i in range(count - 1)]
    max_gap_s = max(gaps) if gaps else 0.0
    mean_gap_s = (sum(gaps) / len(gaps)) if gaps else 0.0
    max_gap_index = gaps.index(max_gap_s) + 1 if gaps and max_gap_s > 0 else 0
    max_gap_pos_ratio = (max_gap_index / count) if count else 0.0
    overall_wps = count / max(duration_s, 0.001)
    break_tag_count, break_total_s, break_max_s = _extract_break_summary(source_text)

    metrics = {
        "duration_s": duration_s,
        "max_gap_s": max_gap_s,
        "mean_gap_s": mean_gap_s,
        "max_gap_pos_ratio": max_gap_pos_ratio,
        "overall_wps": overall_wps,
        "break_tag_count": float(break_tag_count),
        "break_total_s": break_total_s,
        "break_max_s": break_max_s,
    }

    # Rule 1: abrupt short segments.
    if duration_s <= config.short_segment_max_seconds:
        return ValidationResult(
            False,
            f"Abrupt short segment risk: duration={duration_s:.2f}s",
            metrics=metrics,
        )

    # Rule 2: strong gap profile.
    if (
        max_gap_s >= config.strong_gap_max_gap_seconds
        and mean_gap_s >= config.strong_gap_mean_gap_seconds
    ):
        return ValidationResult(
            False,
            f"Gap profile risk: max_gap={max_gap_s:.2f}s, mean_gap={mean_gap_s:.2f}s",
            metrics=metrics,
        )

    # Rule 3: dense break + moderate gap pattern.
    if (
        max_gap_s >= config.dense_break_gap_max_gap_seconds
        and mean_gap_s <= config.dense_break_gap_mean_gap_seconds
        and break_tag_count >= config.dense_break_min_break_tags
    ):
        return ValidationResult(
            False,
            (
                "Structured-break gap risk: "
                f"max_gap={max_gap_s:.2f}s, mean_gap={mean_gap_s:.2f}s, breaks={break_tag_count}"
            ),
            metrics=metrics,
        )

    # Rule 4: medium-band pacing profile.
    if (
        config.medium_band_min_gap_seconds <= max_gap_s <= config.medium_band_max_gap_seconds
        and config.medium_band_min_mean_gap_seconds <= mean_gap_s <= config.medium_band_max_mean_gap_seconds
        and break_tag_count >= config.medium_band_min_break_tags
        and duration_s >= config.medium_band_min_duration_seconds
    ):
        return ValidationResult(
            False,
            (
                "Medium-band pacing risk: "
                f"max_gap={max_gap_s:.2f}s, mean_gap={mean_gap_s:.2f}s, breaks={break_tag_count}"
            ),
            metrics=metrics,
        )

    # Rule 5: distilled base branch (surrogate of grouped HGB @ 0.5).
    base_fail = False
    if max_gap_s <= config.base_split_max_gap_seconds:
        if (
            max_gap_pos_ratio > config.base_split_max_gap_pos_ratio
            and break_total_s > config.base_split_break_total_seconds
        ):
            base_fail = True
    else:
        if duration_s <= config.base_hi_gap_split_duration_seconds:
            if max_gap_s > config.base_hi_gap_max_gap_seconds:
                base_fail = True
        elif duration_s <= config.base_mid_duration_seconds:
            if overall_wps <= config.base_mid_overall_wps_max:
                base_fail = True

    if base_fail:
        return ValidationResult(
            False,
            (
                "Standalone C risk score: "
                f"max_gap={max_gap_s:.2f}s, mean_gap={mean_gap_s:.2f}s, duration={duration_s:.2f}s"
            ),
            metrics=metrics,
        )

    return ValidationResult(True, "Valid", metrics=metrics)
