"""Transparent rule-based candidate quality checks for PromoIQ."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List


def evaluate_candidates(candidates: List[Dict]) -> Dict:
    """Flag review risks; this is triage, not ground-truth quality measurement."""
    reviewed = []
    for source in candidates:
        item = dict(source)
        scores = item.get("scores", {})
        segments = item.get("segments", [])
        duration = 0.0
        if segments:
            duration = sum(
                max(0.0, float(s.get("end_seconds", 0)) - float(s.get("start_seconds", 0)))
                for s in segments
            )
        flags = list(item.get("quality_flags", []))
        hook = float(scores.get("hook_score", 0))
        cliff = float(scores.get("cliffhanger_score", 0))
        standalone = float(scores.get("standalone_score", 0))
        total = float(scores.get("total_score", 0))

        if hook < 40:
            flags.append("weak_hook_signal")
        if cliff < 40:
            flags.append("weak_cliffhanger_signal")
        if standalone < 50:
            flags.append("low_standalone_clarity")
        if total < 45:
            flags.append("low_overall_score")
        if not item.get("hook"):
            flags.append("missing_hook_description")
        if not item.get("cliffhanger"):
            flags.append("missing_cliffhanger_description")
        if not item.get("why_it_works"):
            flags.append("missing_editorial_rationale")
        if not item.get("standalone_context"):
            flags.append("missing_context_summary")
        if duration and not 20 <= duration <= 60:
            flags.append("duration_out_of_range")
        plan = item.get("multi_segment_plan")
        if plan:
            flags.extend(plan.get("continuity_warnings", []))
        item["quality_flags"] = sorted(set(flags))
        item["quality_tier"] = (
            "needs_review" if flags else "screening_candidate"
        )
        reviewed.append(item)

    # Detect temporal overlap within the same episode. This is a warning,
    # not an automatic rejection: adjacent promos may intentionally share beats.
    by_episode: Dict[str, List[Dict]] = {}
    for item in reviewed:
        segs = item.get("segments", [])
        if not segs:
            continue
        s = segs[0]
        by_episode.setdefault(item.get("episode", "Unknown"), []).append(
            (float(s.get("start_seconds", 0)), float(s.get("end_seconds", 0)), item)
        )
    overlap_count = 0
    for episode_items in by_episode.values():
        episode_items.sort(key=lambda x: x[0])
        for i, (start, end, item) in enumerate(episode_items):
            for other_start, other_end, other in episode_items[i + 1:]:
                if other_start >= end:
                    break
                intersection = max(0.0, min(end, other_end) - max(start, other_start))
                shorter = min(end - start, other_end - other_start)
                if shorter > 0 and intersection / shorter >= 0.5:
                    item["quality_flags"].append("substantial_candidate_overlap")
                    other["quality_flags"].append("substantial_candidate_overlap")
                    item["quality_tier"] = other["quality_tier"] = "needs_review"
                    overlap_count += 1

    counts = Counter(flag for item in reviewed for flag in item["quality_flags"])
    tiers = Counter(item["quality_tier"] for item in reviewed)
    durations = []
    for item in reviewed:
        if item.get("segments"):
            durations.append(sum(
                max(0.0, float(s.get("end_seconds", 0)) - float(s.get("start_seconds", 0)))
                for s in item["segments"]
            ))
    return {
        "candidate_count": len(reviewed),
        "needs_review_count": tiers.get("needs_review", 0),
        "screening_candidate_count": tiers.get("screening_candidate", 0),
        "overlap_pairs_flagged": overlap_count,
        "flag_counts": dict(sorted(counts.items())),
        "duration_compliant_count": sum(20 <= d <= 60 for d in durations),
        "duration_out_of_range_count": sum(not 20 <= d <= 60 for d in durations),
        "reviewed_candidates": reviewed,
        "interpretation": (
            "Rule-based quality triage only. Flags identify candidates for human review; "
            "they do not establish that a promo is objectively good or bad."
        ),
    }
