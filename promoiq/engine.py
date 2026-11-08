"""Promo candidate discovery and validation for PromoIQ."""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List

from .parser import TimedLine, parse_screenplay
from .scoring import score_candidate

SYSTEM_PROMPT = """You are a careful promo editor. Find candidate 20-60 second promos from the provided timestamped screenplay blocks. A promo must open with a compelling hook within its first 3 seconds, provide enough context for a new viewer, and end before an unresolved reveal, threat, decision or reversal. Use only events and dialogue in the input. Never invent timestamps or plot facts. Return ONLY JSON: {\"promos\":[{\"start\":number,\"end\":number,\"hook\":string,\"cliffhanger\":string,\"why_it_works\":string,\"standalone_context\":string}]}. Prefer one continuous segment. A promo may have multiple segments only if continuity is still understandable; this prototype expects one segment per promo. Use the numeric start/end seconds of actual timed blocks."""


def _line_text(line: TimedLine) -> str:
    if line.speaker:
        prefix = f"{line.speaker}:"
        if line.text.strip().casefold().startswith(prefix.casefold()):
            return line.text.strip()
        return f"{prefix} {line.text}"
    return line.text


def _is_editorial_content(line: TimedLine) -> bool:
    return line.kind in {"dialogue", "action", "legacy"}


def _pick_hook(window: List[TimedLine], clip_start: float) -> str:
    """Choose the strongest dialogue/action beat in the first 3 seconds."""

    opening = [
        line for line in window
        if line.timestamp < clip_start + 3.0
        and float(line.end_timestamp or line.timestamp) > clip_start
        and _is_editorial_content(line)
    ]

    if not opening:
        return ""

    ranked = [
        (
            score_candidate(
                _line_text(line),
                40,
                start_text=_line_text(line),
            )["hook_score"],
            line,
        )
        for line in opening
    ]

    best_score, best_line = max(
        ranked,
        key=lambda item: (
            item[0],
            -item[1].timestamp,
            -item[1].index,
        ),
    )

    # Reject generic dialogue that has no meaningful attention-grabbing signal.
    if best_score < 40:
        return ""

    return _line_text(best_line)


def _pick_cliffhanger(window: List[TimedLine], clip_end: float) -> str:
    """Return the final editorial beat immediately before the cut."""

    closing = [
        line for line in window
        if float(line.end_timestamp or line.timestamp) >= clip_end - 5.0
        and _is_editorial_content(line)
    ]

    if not closing:
        return ""

    # Preserve chronological order: a later resolved action must not be
    # replaced by an earlier dramatic dialogue line.
    selected = max(
        closing,
        key=lambda line: (
            float(line.end_timestamp or line.timestamp),
            line.index,
        ),
    )

    return _line_text(selected)


def _scene_key(line: TimedLine):
    """Return a stable identity for an explicitly identified scene."""

    if line.scene_number is None and not line.scene_heading:
        return None

    return (
        line.scene_number,
        (line.scene_heading or "").strip().casefold(),
    )


def _candidate_window(
    lines: List[TimedLine],
    start: float,
    end: float,
    reference: TimedLine | None = None,
) -> List[TimedLine]:
    """Return overlapping blocks, optionally restricted to one scene."""

    reference_scene = _scene_key(reference) if reference is not None else None

    return [
        line for line in lines
        if line.timestamp < end
        and float(line.end_timestamp or line.timestamp) > start
        and (
            reference is None
            or _scene_key(line) == reference_scene
        )
    ]



def _fallback(lines: List[TimedLine], episode: str) -> List[Dict]:
    """
    Generate timestamp-grounded promo candidates.

    Strong candidates are preferred, but lower-confidence candidates
    are retained for editorial review to avoid silently dropping episodes.
    """

    if len(lines) < 2:
        return []

    editorial = [
        line for line in lines
        if _is_editorial_content(line)
    ]

    if not editorial:
        return []

    episode_start = min(line.timestamp for line in lines)
    episode_end = max(
        float(line.end_timestamp or line.timestamp)
        for line in lines
    )

    if episode_end - episode_start < 20:
        return []

    candidates = []
    seen = set()

    # Use dialogue/action timestamps as possible hook anchors.
    anchors = sorted(
        editorial,
        key=lambda line: (
            -score_candidate(
                _line_text(line),
                40,
                start_text=_line_text(line),
            )["hook_score"],
            line.timestamp,
            line.index,
        ),
    )

    for anchor in anchors:
        clip_start = anchor.timestamp

        possible_ends = []

        for last in lines:
            clip_end = float(
                last.end_timestamp or last.timestamp
            )

            duration = clip_end - clip_start

            if 20 <= duration <= 60:
                possible_ends.append((
                    abs(duration - 40),
                    clip_end,
                ))

        if not possible_ends:
            continue

        # Test the duration options nearest to 40 seconds first.
        possible_ends.sort(key=lambda item: item[0])

        for _, clip_end in possible_ends:
            window_key = (
                round(clip_start, 3),
                round(clip_end, 3),
            )

            if window_key in seen:
                continue

            window = _candidate_window(
                lines,
                clip_start,
                clip_end,
            )

            if not window:
                continue

            scene_keys = list(dict.fromkeys(
                _scene_key(line) for line in window
            ))

            # Prefer a maximum of three scenes.
            # Larger transitions are considered only as a fallback.
            if len(scene_keys) > 3:
                continue

            body = " ".join(
                _line_text(line) for line in window
            )

            if len(body.split()) < 12:
                continue

            duration = clip_end - clip_start

            hook = _pick_hook(window, clip_start)

            # Preserve a real timestamped opening beat even when it
            # does not meet the high-confidence hook threshold.
            if not hook:
                hook = _line_text(anchor)

            cliffhanger = _pick_cliffhanger(
                window,
                clip_end,
            )

            if not cliffhanger:
                final_editorial = [
                    line for line in window
                    if _is_editorial_content(line)
                ]

                if not final_editorial:
                    continue

                cliffhanger = _line_text(
                    final_editorial[-1]
                )

            evidence = _scoring_evidence(window, clip_start, clip_end)
            scores = score_candidate(body, duration, evidence["opening_text"], evidence["closing_text"])

            hook_strength = scores["hook_score"]
            cliff_strength = scores["cliffhanger_score"]

            if hook_strength >= 55 and cliff_strength >= 55:
                quality = "high"
            elif hook_strength >= 40 and cliff_strength >= 40:
                quality = "medium"
            else:
                quality = "low"

            review_flags = []

            if hook_strength < 40:
                review_flags.append("weak_or_unconfirmed_hook")

            if cliff_strength < 40:
                review_flags.append("weak_or_resolved_ending")

            if len(scene_keys) > 1:
                review_flags.append("crosses_scene_boundary")

            seen.add(window_key)

            candidates.append({
                "episode": episode,
                "segments": [{
                    "start_seconds": clip_start,
                    "end_seconds": clip_end,
                    "start_timestamp": anchor.timestamp_text,
                    "end_timestamp": _fmt(clip_end),
                }],
                "hook": hook,
                "cliffhanger": cliffhanger,
                "standalone_context": (
                    "Screenplay-only estimate. "
                    f"Confidence tier: {quality}. "
                    "Editor must verify context and footage."
                ),
                "why_it_works": (
                    "Candidate selected from timestamped editorial "
                    f"beats. Confidence tier: {quality}. "
                    "Review the opening, ending and scene transitions."
                ),
                "scores": scores,
                "scoring_evidence": evidence,
                "method": "heuristic_fallback",
                "quality_tier": quality,
                "review_flags": review_flags,
                "scene_count": len(scene_keys),
                "scene_number": anchor.scene_number,
                "scene_heading": anchor.scene_heading,
                "source_excerpt": body,
            })

            # Keep the strongest duration option for this anchor.
            break

    candidates.sort(
        key=lambda item: (
            -item["scores"]["total_score"],
            item["quality_tier"] != "high",
            item["segments"][0]["start_seconds"],
            item["segments"][0]["end_seconds"],
        )
    )

    selected = []

    for candidate in candidates:
        start = candidate["segments"][0]["start_seconds"]
        end = candidate["segments"][0]["end_seconds"]

        diverse = True

        for existing in selected:
            other_start = existing["segments"][0]["start_seconds"]
            other_end = existing["segments"][0]["end_seconds"]

            overlap = max(
                0.0,
                min(end, other_end) - max(start, other_start),
            )

            shorter = min(
                end - start,
                other_end - other_start,
            )

            overlap_ratio = overlap / shorter if shorter > 0 else 0

            if abs(start - other_start) <= 15 or overlap_ratio >= 0.35:
                diverse = False
                break

        if diverse:
            selected.append(candidate)

        if len(selected) == 8:
            break

    # If the three-scene restriction removes every candidate,
    # retry with a wider continuity allowance but retain a review flag.
    if not selected:
        for anchor in anchors:
            clip_start = anchor.timestamp

            possible_ends = sorted(
                (
                    abs(
                        float(line.end_timestamp or line.timestamp)
                        - clip_start - 40
                    ),
                    float(line.end_timestamp or line.timestamp),
                )
                for line in lines
                if 20 <= (
                    float(line.end_timestamp or line.timestamp)
                    - clip_start
                ) <= 60
            )

            if not possible_ends:
                continue

            clip_end = possible_ends[0][1]
            window = _candidate_window(
                lines, clip_start, clip_end
            )

            body = " ".join(
                _line_text(line) for line in window
            )

            if len(body.split()) < 12:
                continue

            final_editorial = [
                line for line in window
                if _is_editorial_content(line)
            ]

            if not final_editorial:
                continue

            hook = _pick_hook(window, clip_start) or _line_text(anchor)
            cliffhanger = (
                _pick_cliffhanger(window, clip_end)
                or _line_text(final_editorial[-1])
            )

            duration = clip_end - clip_start

            evidence = _scoring_evidence(window, clip_start, clip_end)
            scores = score_candidate(body, duration, evidence["opening_text"], evidence["closing_text"])

            scene_keys = {
                _scene_key(line) for line in window
            }

            selected.append({
                "episode": episode,
                "segments": [{
                    "start_seconds": clip_start,
                    "end_seconds": clip_end,
                    "start_timestamp": anchor.timestamp_text,
                    "end_timestamp": _fmt(clip_end),
                }],
                "hook": hook,
                "cliffhanger": cliffhanger,
                "standalone_context": (
                    "Low-confidence continuity fallback. "
                    "Multiple scenes require editorial review."
                ),
                "why_it_works": (
                    "Coverage fallback: a valid continuous duration "
                    "was found, but promotional suitability needs "
                    "manual confirmation."
                ),
                "scores": scores,
                "scoring_evidence": evidence,
                "method": "heuristic_fallback",
                "quality_tier": "low",
                "review_flags": [
                    "fallback_candidate",
                    "multiple_scene_continuity_review",
                ],
                "scene_count": len(scene_keys),
                "scene_number": anchor.scene_number,
                "scene_heading": anchor.scene_heading,
                "source_excerpt": body,
            })

            break

    return selected


def _scoring_evidence(window: List[TimedLine], start: float, end: float) -> Dict:
    """Select strongest source-grounded hook and cliffhanger beats.

    Search the opening 8 seconds (or first 25% of the clip) for a hook and
    the final 12 seconds (or final 40%) for a cliffhanger. Select the strongest
    deterministic text signal; ties prefer beats nearest the relevant edge.
    This is screenplay-text triage, not footage review.
    """
    editorial = [line for line in window if _is_editorial_content(line)]
    if not editorial:
        return {"opening_text": "", "closing_text": "", "opening_timestamp": None,
                "closing_timestamp": None, "opening_search_window": None,
                "closing_search_window": None, "selection_method": "no_editorial_blocks"}
    duration = max(0.0, end - start)
    opening_cutoff = start + min(8.0, duration * 0.25)
    closing_cutoff = end - min(12.0, duration * 0.40)
    opening = [x for x in editorial if x.timestamp < opening_cutoff and float(x.end_timestamp or x.timestamp) > start]
    closing = [x for x in editorial if float(x.end_timestamp or x.timestamp) >= closing_cutoff and x.timestamp < end]
    def hook_strength(line):
        txt = _line_text(line)
        return score_candidate(txt, 40, start_text=txt)["hook_score"]
    def cliff_strength(line):
        txt = _line_text(line)
        return score_candidate(txt, 40, end_text=txt)["cliffhanger_score"]
    opening_line = max(opening or editorial, key=lambda x: (hook_strength(x), -x.timestamp, -x.index))
    closing_line = max(closing or editorial, key=lambda x: (cliff_strength(x), float(x.end_timestamp or x.timestamp), x.index))
    return {
        "opening_text": _line_text(opening_line), "closing_text": _line_text(closing_line),
        "opening_timestamp": opening_line.timestamp_text, "closing_timestamp": closing_line.timestamp_text,
        "opening_search_window": f"{_fmt(start)}–{_fmt(opening_cutoff)}",
        "closing_search_window": f"{_fmt(closing_cutoff)}–{_fmt(end)}",
        "selection_method": "strongest_rule_based_signal_with_edge_tiebreak",
    }


def _llm_candidates(lines: List[TimedLine], episode: str, api_key: str, model: str) -> List[Dict]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    # Keep a compact, representative sample to stay within Groq TPM limits.
    relevant = [x for x in lines if x.kind.lower() in {"dialogue", "action"}]
    if not relevant:
        relevant = lines

    max_blocks = 64
    if len(relevant) > max_blocks:
        indices = [
            round(i * (len(relevant) - 1) / (max_blocks - 1))
            for i in range(max_blocks)
        ]
        relevant = [relevant[i] for i in indices]

    payload = [{
        "start_seconds": x.timestamp,
        "end_seconds": x.end_timestamp,
        "kind": x.kind,
        "speaker": x.speaker or "",
        "text": (x.text or "")[:180],
        "scene_number": x.scene_number,
    } for x in relevant]

    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        max_completion_tokens=1600,
        reasoning_effort="low",
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "promoiq_promos",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "promos": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "number"},
                                    "end": {"type": "number"},
                                    "hook": {"type": "string"},
                                    "cliffhanger": {"type": "string"},
                                    "standalone_context": {"type": "string"},
                                    "why_it_works": {"type": "string"}
                                },
                                "required": [
                                    "start", "end", "hook", "cliffhanger",
                                    "standalone_context", "why_it_works"
                                ],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["promos"],
                    "additionalProperties": False
                }
            }
        },
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + "\n\nIMPORTANT: Return ONLY valid JSON. Return one object with a top-level promos array. Every promo must include numeric start and end timestamps, and string hook, cliffhanger, standalone_context, and why_it_works. Every promo MUST span 20 to 60 seconds inclusive. Select timestamps using the supplied screenplay blocks."},
            {"role": "user", "content": json.dumps({"episode": episode, "blocks": payload})},
        ],
    )
    raw = json.loads(resp.choices[0].message.content)
    output = []
    min_start = min(x.timestamp for x in lines)
    max_end = max(float(x.end_timestamp or x.timestamp) for x in lines)

    for promo in raw.get("promos", []):
        start = float(promo["start"])
        end = float(promo["end"])
        duration = end - start
        if duration < 20 or duration > 60 or start < min_start or end > max_end or end <= start:
            continue
        window = _candidate_window(lines, start, end)
        if not window:
            continue

        # Reject LLM suggestions whose cut crosses an identified scene boundary.
        if len({_scene_key(line) for line in window}) > 1:
            continue
        body = " ".join(_line_text(line) for line in window)
        evidence = _scoring_evidence(window, start, end)
        # Score source screenplay evidence, not LLM-generated descriptions.
        scores = score_candidate(
            body,
            duration,
            evidence["opening_text"],
            evidence["closing_text"],
        )
        output.append({
            "episode": episode,
            "segments": [{
                "start_seconds": start,
                "end_seconds": end,
                "start_timestamp": _fmt(start),
                "end_timestamp": _fmt(end),
            }],
            "hook": promo.get("hook", ""),
            "cliffhanger": promo.get("cliffhanger", ""),
            "standalone_context": promo.get("standalone_context", ""),
            "why_it_works": promo.get("why_it_works", ""),
            "scores": scores,
            "scoring_evidence": evidence,
            "method": "llm_plus_rules",
            "source_excerpt": body,
        })
    return output


def _fmt(sec: float) -> str:
    minutes = int(sec // 60)
    seconds = sec % 60
    return f"{minutes:02d}:{seconds:05.2f}"



def _build_multi_segment_plan(candidate: Dict, lines: List[TimedLine] | None = None) -> Dict | None:
    """Select whole timestamped editorial beats instead of fractional cuts."""
    if not candidate.get("segments") or not lines:
        return None
    source = candidate["segments"][0]
    start, end = float(source["start_seconds"]), float(source["end_seconds"])
    if end - start < 20:
        return None
    blocks = sorted((line for line in lines if _is_editorial_content(line)
                     and line.timestamp >= start - 0.01
                     and float(line.end_timestamp or line.timestamp) <= end + 0.01
                     and float(line.end_timestamp or line.timestamp) > line.timestamp),
                    key=lambda x: (x.timestamp, x.index))
    if len(blocks) < 4:
        return None
    def strength(line: TimedLine, key: str) -> float:
        txt = _line_text(line)
        return float(score_candidate(txt, 40, start_text=txt, end_text=txt)[key])
    options = []
    for i in range(1, len(blocks)-2):
        a, b = blocks[0].timestamp, float(blocks[i].end_timestamp)
        if b-a < 8:
            continue
        for j in range(i+2, len(blocks)-1):
            c, d = blocks[j].timestamp, float(blocks[-1].end_timestamp)
            total = b-a+d-c
            if c <= b + 0.05 or d > end + 0.01 or d-c < 8 or not 20 <= total <= 60:
                continue
            hook = max(strength(x, "hook_score") for x in blocks[:i+1])
            cliff = max(strength(x, "cliffhanger_score") for x in blocks[j:])
            quality = .5*hook + .5*cliff - .12*(c-b) - .08*abs(total-35)
            options.append((quality, i, j, a, b, c, d))
    if not options:
        return None
    _, i, j, a, b, c, d = max(options, key=lambda x: (x[0], -x[1], -x[2]))
    def segment(st: float, en: float, role: str) -> Dict:
        return {"start_seconds": round(st, 2), "end_seconds": round(en, 2),
                "start_timestamp": _fmt(st), "end_timestamp": _fmt(en), "role": role}
    flags = ["video_and_audio_continuity_unverified", "omitted_dialogue_or_action_requires_review"]
    if blocks[j].kind == "dialogue":
        flags.append("second_segment_opens_with_dialogue_check_references")
    if _scene_key(blocks[i]) != _scene_key(blocks[j]):
        flags.append("scene_transition_requires_review")
    return {
        "segments": [segment(a, b, "hook_and_setup"), segment(c, d, "payoff_or_cliffhanger")],
        "total_duration_seconds": round((b-a)+(d-c), 2),
        "selection_method": "timestamped_editorial_beat_scoring",
        "opening_beat": _line_text(blocks[0]),
        "closing_beat": _line_text(blocks[-1]),
        "omitted_block_count": len(blocks[i+1:j]),
        "review_flags": flags,
        "edit_note": "Selected at complete screenplay-block boundaries. Check omitted dialogue, scene transitions and video/audio continuity.",
        "review_required": True,
    }


def _attach_edit_plans(promos: List[Dict], lines: List[TimedLine]) -> List[Dict]:
    for promo in promos:
        plan = _build_multi_segment_plan(promo, lines)
        promo["multi_segment_plan"] = plan
        if plan:
            flags = promo.setdefault("review_flags", [])
            for flag in plan["review_flags"]:
                if flag not in flags:
                    flags.append(flag)
    return promos


def analyse_episode(text: str, episode: str, use_llm: bool = True) -> Dict:
    lines = parse_screenplay(text)
    if len(lines) < 2:
        return {
            "episode": episode,
            "status": "needs_timestamped_input",
            "parsed_lines": len(lines),
            "promos": [],
            "message": "No usable timestamped screenplay blocks found. Check Start/End intervals and the content line that follows each interval.",
        }

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if use_llm and api_key:
        try:
            promos = _attach_edit_plans(_llm_candidates(lines, episode, api_key, model), lines)
            return {
                "episode": episode,
                "status": "ok_llm",
                "parsed_lines": len(lines),
                "promos": sorted(
                    promos,
                    key=lambda x: (
                        x["scores"]["total_score"],
                        x["scores"].get("hook_score", 0),
                        x["scores"].get("cliffhanger_score", 0),
                        x["scores"].get("standalone_score", 0),
                    ),
                    reverse=True,
                ),
            }
        except Exception as exc:
            promos = _attach_edit_plans(_fallback(lines, episode), lines)
            return {
                "episode": episode,
                "status": "fallback_after_llm_error",
                "parsed_lines": len(lines),
                "llm_error": str(exc)[:240],
                "promos": promos,
            }
    return {
        "episode": episode,
        "status": "ok_heuristic_demo",
        "parsed_lines": len(lines),
        "promos": _attach_edit_plans(_fallback(lines, episode), lines),
    }
