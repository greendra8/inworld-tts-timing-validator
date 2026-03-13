from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Any

BREAK_TAG_PATTERN = re.compile(
    r"<break\s+time\s*=\s*['\"](?P<seconds>\d+(?:\.\d+)?)s['\"]\s*/?>",
    re.IGNORECASE,
)
WORD_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9À-ÖØ-öø-ÿ']+")


@dataclass(frozen=True)
class ValidationConfig:
    max_gap_seconds: float = 2.0
    max_gap_after_sentence_seconds: float = 3.0
    wps_ratio_threshold: float = 3.1
    window_size: int = 6
    break_tolerance_seconds: float = 0.35

    break_word_min_seconds: float = 1.2
    break_word_duration_ratio: float = 3.0
    break_duration_median_window: int = 4

    initial_gap_no_break_seconds: float = 0.5
    initial_gap_short_word_max_seconds: float = 0.8
    initial_gap_second_word_max_seconds: float = 0.3
    initial_gap_delta_seconds: float = 0.1

    # Segment-level severity gate for pause-related failures.
    anomaly_min_max_word_seconds: float = 1.4
    anomaly_min_gap_seconds: float = 3.0
    anomaly_min_word_ratio: float = 2.0


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str
    metrics: dict[str, float] | None = None


def _normalize_word_token(value: str) -> str:
    if not isinstance(value, str):
        return ""
    tokens = WORD_TOKEN_PATTERN.findall(value.lower())
    return tokens[-1] if tokens else ""


def _extract_break_allowances(source_text: str | None) -> dict[tuple[str, str], list[float]]:
    if not source_text:
        return {}

    allowances: dict[tuple[str, str], list[float]] = {}
    for match in BREAK_TAG_PATTERN.finditer(source_text):
        try:
            break_seconds = float(match.group("seconds"))
        except (TypeError, ValueError):
            continue
        if break_seconds <= 0:
            continue

        before = source_text[: match.start()]
        after = source_text[match.end() :]
        prev_tokens = WORD_TOKEN_PATTERN.findall(before.lower())
        next_tokens = WORD_TOKEN_PATTERN.findall(after.lower())
        if not prev_tokens or not next_tokens:
            continue

        key = (prev_tokens[-1], next_tokens[0])
        allowances.setdefault(key, []).append(break_seconds)

    return allowances


def validate_inworld_timestamps(
    timestamp_info: dict[str, Any] | None,
    source_text: str | None = None,
    config: ValidationConfig = ValidationConfig(),
) -> ValidationResult:
    """Validate Inworld word timing metadata and return pass/fail with reason."""
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

    # Segment-level summary stats used by both checks and the severity gate.
    word_durations = [max(float(ends[i]) - float(starts[i]), 0.0) for i in range(count)]
    positive_word_durations = [d for d in word_durations if d > 0]
    median_word_duration = median(positive_word_durations) if positive_word_durations else 0.0
    max_word_duration = max(positive_word_durations) if positive_word_durations else 0.0
    max_word_ratio = max_word_duration / max(median_word_duration, 0.05) if max_word_duration > 0 else 0.0
    gap_values = [float(starts[i + 1]) - float(ends[i]) for i in range(count - 1)]
    max_gap_observed = max(gap_values) if gap_values else 0.0

    # Pause-related checks (gap/break/initial-gap) are only enforced when the
    # overall segment looks structurally anomalous. This sharply reduces natural
    # pause false positives.
    enforce_pause_anomaly_failure = (
        max_word_duration >= config.anomaly_min_max_word_seconds
        or (
            max_gap_observed >= config.anomaly_min_gap_seconds
            and max_word_ratio >= config.anomaly_min_word_ratio
        )
    )

    break_allowances = _extract_break_allowances(source_text)
    consumed_expected_break_seconds = 0.0
    break_boundaries: list[tuple[int, float]] = []
    sentence_endings = (".", "!", "?")

    # 1) Gap check with sentence-aware thresholds and optional break allowances.
    for i in range(count - 1):
        gap = float(starts[i + 1]) - float(ends[i])
        prev_word = words[i]
        is_after_sentence = any(prev_word.endswith(p) for p in sentence_endings)
        threshold = (
            config.max_gap_after_sentence_seconds
            if is_after_sentence
            else config.max_gap_seconds
        )

        pair_key = (_normalize_word_token(words[i]), _normalize_word_token(words[i + 1]))
        expected_break = 0.0
        pair_allowances = break_allowances.get(pair_key)
        if pair_allowances:
            expected_break = pair_allowances.pop(0)
            consumed_expected_break_seconds += expected_break
            break_boundaries.append((i, expected_break))
            threshold += expected_break + config.break_tolerance_seconds

        if gap > threshold and enforce_pause_anomaly_failure:
            break_context = (
                f" (expected break ~{expected_break:.2f}s)" if expected_break > 0 else ""
            )
            context = " (after sentence)" if is_after_sentence else ""
            return ValidationResult(
                False,
                f"Gap too large: {gap:.2f}s between '{words[i]}' and '{words[i+1]}' "
                f"(word {i+1} of {count}){context}{break_context}",
            )

    # 2) If a break is expected, check that the pre-break word duration is not
    # an extreme outlier versus local neighbors.
    for boundary_index, expected_break in break_boundaries:
        boundary_word_duration = float(ends[boundary_index]) - float(starts[boundary_index])
        if boundary_word_duration < config.break_word_min_seconds:
            continue

        left = max(0, boundary_index - config.break_duration_median_window)
        right = min(count - 1, boundary_index + config.break_duration_median_window)
        neighbor_durations: list[float] = []
        for j in range(left, right + 1):
            if j == boundary_index:
                continue
            duration = float(ends[j]) - float(starts[j])
            if duration > 0:
                neighbor_durations.append(duration)
        if not neighbor_durations:
            continue

        local_median = median(neighbor_durations)
        local_ratio = boundary_word_duration / max(local_median, 0.05)
        if (
            local_ratio > config.break_word_duration_ratio
            and enforce_pause_anomaly_failure
        ):
            return ValidationResult(
                False,
                f"Break-boundary duration anomaly: '{words[boundary_index]}' lasts "
                f"{boundary_word_duration:.2f}s ({local_ratio:.1f}x local median "
                f"{local_median:.2f}s) before expected break ~{expected_break:.2f}s",
            )

    # 3) Special case near the opening boundary: catches hidden repeated opener
    # patterns that manifest as a suspicious first gap.
    if not break_boundaries and count >= 2 and not words[0].endswith((",", ".", "!", "?", ";", ":")):
        first_gap = float(starts[1]) - float(ends[0])
        if first_gap > config.initial_gap_no_break_seconds:
            first_word_duration = float(ends[0]) - float(starts[0])
            second_word_duration = float(ends[1]) - float(starts[1])
            if second_word_duration <= config.initial_gap_second_word_max_seconds:
                following_gaps = []
                for i in range(1, min(count - 1, 8)):
                    gap = float(starts[i + 1]) - float(ends[i])
                    if gap > 0.01:
                        following_gaps.append(gap)
                median_following_gap = median(following_gaps) if following_gaps else 0.0
                delta = first_gap - median_following_gap
                if (
                    (
                        first_word_duration <= config.initial_gap_short_word_max_seconds
                        or delta > config.initial_gap_delta_seconds
                    )
                    and enforce_pause_anomaly_failure
                ):
                    return ValidationResult(
                        False,
                        f"Initial gap anomaly: {first_gap:.2f}s between '{words[0]}' and "
                        f"'{words[1]}' (first {first_word_duration:.2f}s, second "
                        f"{second_word_duration:.2f}s, baseline {median_following_gap:.2f}s, "
                        f"delta {delta:.2f}s)",
                    )

    # 4) WPS spike check remains independent of the pause severity gate so that
    # compressed/truncated pacing anomalies are still caught.
    if count >= config.window_size:
        total_duration = float(ends[-1]) - float(starts[0])
        if total_duration <= 0:
            return ValidationResult(True, "Zero duration segment")

        adjusted_duration = total_duration - consumed_expected_break_seconds
        if adjusted_duration <= 0:
            adjusted_duration = total_duration
        overall_wps = count / adjusted_duration

        max_window_wps = 0.0
        max_wps_index = 0
        for i in range(count - config.window_size + 1):
            window_start = float(starts[i])
            window_end = float(ends[i + config.window_size - 1])
            window_duration = max(window_end - window_start, 0.001)
            window_wps = config.window_size / window_duration
            if window_wps > max_window_wps:
                max_window_wps = window_wps
                max_wps_index = i

        ratio = max_window_wps / max(overall_wps, 0.1)
        if ratio > config.wps_ratio_threshold:
            return ValidationResult(
                False,
                f"WPS spike: {max_window_wps:.1f} wps ({ratio:.1f}x overall {overall_wps:.1f}) "
                f"at word {max_wps_index + 1}",
            )

    return ValidationResult(
        True,
        "Valid",
        metrics={
            "max_word_duration": max_word_duration,
            "median_word_duration": median_word_duration,
            "max_word_ratio": max_word_ratio,
            "max_gap_observed": max_gap_observed,
        },
    )
