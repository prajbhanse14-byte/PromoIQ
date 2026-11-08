from promoiq.quality import evaluate_candidates


def candidate(start, end, score=60, hook=60, cliff=60, standalone=60, episode="Ep 1"):
    return {
        "episode": episode,
        "segments": [{"start_seconds": start, "end_seconds": end}],
        "scores": {"total_score": score, "hook_score": hook,
                   "cliffhanger_score": cliff, "standalone_score": standalone},
        "hook": "A threat is revealed",
        "cliffhanger": "What happens next?",
        "why_it_works": "It creates suspense.",
        "standalone_context": "A character faces a threat.",
    }


def test_weak_components_are_flagged():
    result = evaluate_candidates([candidate(0, 30, score=35, hook=25, cliff=25, standalone=40)])
    flags = result["reviewed_candidates"][0]["quality_flags"]
    assert "weak_hook_signal" in flags
    assert "weak_cliffhanger_signal" in flags
    assert "low_standalone_clarity" in flags
    assert "low_overall_score" in flags
    assert result["needs_review_count"] == 1


def test_duration_out_of_range_is_flagged():
    result = evaluate_candidates([candidate(0, 15)])
    assert "duration_out_of_range" in result["reviewed_candidates"][0]["quality_flags"]
    assert result["duration_out_of_range_count"] == 1


def test_overlapping_candidates_are_flagged():
    result = evaluate_candidates([candidate(0, 30), candidate(10, 35)])
    assert result["overlap_pairs_flagged"] == 1
    assert all("substantial_candidate_overlap" in x["quality_flags"]
               for x in result["reviewed_candidates"])


def test_good_candidate_has_no_flags():
    result = evaluate_candidates([candidate(0, 40)])
    assert result["reviewed_candidates"][0]["quality_flags"] == []
    assert result["screening_candidate_count"] == 1


def test_missing_rationale_is_flagged():
    item = candidate(0, 40)
    item["why_it_works"] = ""
    result = evaluate_candidates([item])
    assert "missing_editorial_rationale" in result["reviewed_candidates"][0]["quality_flags"]
