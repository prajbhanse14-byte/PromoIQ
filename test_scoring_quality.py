from promoiq.scoring import score_candidate


def test_high_stakes_opening_beats_ordinary_question():
    dramatic = score_candidate(
        "The guards approach.",
        40,
        start_text="Your husband will hang at dawn unless the ring is returned."
    )

    ordinary = score_candidate(
        "We are having dinner.",
        40,
        start_text="What time is dinner?"
    )

    assert dramatic["hook_score"] > ordinary["hook_score"]


def test_unresolved_threat_beats_resolved_emotional_dialogue():
    unresolved = score_candidate(
        "Alexander is in danger.",
        40,
        end_text="At dawn, Alexander will hang unless Juliana returns."
    )

    resolved = score_candidate(
        "Juliana and Alexander embrace.",
        40,
        end_text="Wait, I didn't lose you. You are safe now."
    )

    assert unresolved["cliffhanger_score"] > resolved["cliffhanger_score"]


def test_ideal_duration_scores_higher_than_boundary_durations():
    ideal = score_candidate("A dramatic confrontation", 40)
    minimum = score_candidate("A dramatic confrontation", 20)
    maximum = score_candidate("A dramatic confrontation", 60)

    assert ideal["duration_score"] > minimum["duration_score"]
    assert ideal["duration_score"] > maximum["duration_score"]


def test_score_is_deterministic():
    first = score_candidate(
        "A villain threatens the heroine.",
        40,
        start_text="You will pay for this.",
        end_text="Tomorrow, your secret will be revealed."
    )

    second = score_candidate(
        "A villain threatens the heroine.",
        40,
        start_text="You will pay for this.",
        end_text="Tomorrow, your secret will be revealed."
    )

    assert first == second


def test_social_humiliation_is_recognized_as_a_hook():
    confrontation = score_candidate(
        "Juliana faces Gerald.",
        40,
        start_text="You look like a servant."
    )

    ordinary = score_candidate(
        "Juliana faces Gerald.",
        40,
        start_text="The weather is pleasant today."
    )

    assert confrontation["hook_score"] > ordinary["hook_score"]


def _sample_lines():
    from promoiq.parser import TimedLine
    texts = [
        "They will arrest Juliana tonight!",
        "Why would they do that?",
        "The council signed the warrant.",
        "The guards are already coming.",
        "She walks toward the locked door.",
        "We have to escape before dawn.",
        "I know who betrayed you.",
        "The traitor is standing behind you!",
    ]
    return [TimedLine(timestamp=i*5.0, timestamp_text=f"00:{i*5:02d}",
                      end_timestamp=(i+1)*5.0, text=t, index=i,
                      kind="dialogue", speaker="JULIANA")
            for i,t in enumerate(texts)]


def test_multi_segment_plan_is_ordered_and_within_promo_duration():
    from promoiq.engine import _build_multi_segment_plan
    candidate = {"segments": [{"start_seconds": 0.0, "end_seconds": 40.0}]}
    plan = _build_multi_segment_plan(candidate, _sample_lines())
    assert plan is not None
    parts = plan["segments"]
    assert len(parts) == 2
    assert parts[0]["end_seconds"] < parts[1]["start_seconds"]
    assert 20 <= plan["total_duration_seconds"] <= 60
    assert plan["selection_method"] == "timestamped_editorial_beat_scoring"
    assert plan["review_required"] is True
    # Cuts align to actual 5-second block boundaries.
    assert all(p["start_seconds"] % 5 == 0 and p["end_seconds"] % 5 == 0 for p in parts)


def test_multi_segment_plan_rejects_too_short_parts():
    from promoiq.engine import _build_multi_segment_plan
    candidate = {"segments": [{"start_seconds": 0.0, "end_seconds": 18.0}]}
    assert _build_multi_segment_plan(candidate, _sample_lines()) is None


def test_multi_segment_plan_requires_real_timed_blocks():
    from promoiq.engine import _build_multi_segment_plan
    candidate = {"segments": [{"start_seconds": 0.0, "end_seconds": 40.0}]}
    assert _build_multi_segment_plan(candidate, []) is None



def test_score_exposes_evidence_completeness_component():
    result = score_candidate(
        "JULIANA: I know what happened. GERALD: But you do not know the truth.",
        35,
        start_text="JULIANA: I know what happened!",
        end_text="GERALD: But you do not know the truth..."
    )
    assert 0 <= result["evidence_completeness_score"] <= 100
    assert 0 <= result["total_score"] <= 100


def test_hidden_identity_reveal_signal_improves_cliffhanger():
    reveal = score_candidate(
        "The room falls silent.",
        35,
        end_text="The real heir is standing behind you."
    )
    ordinary = score_candidate(
        "The room falls silent.",
        35,
        end_text="We should go home now."
    )
    assert reveal["cliffhanger_score"] > ordinary["cliffhanger_score"]



def test_warning_or_imperative_can_signal_cliffhanger():
    warning = score_candidate(
        "Juliana enters the room.",
        30,
        end_text="You should turn around, Juliana."
    )
    ordinary = score_candidate(
        "Juliana enters the room.",
        30,
        end_text="The ceremony is beginning now."
    )
    assert warning["cliffhanger_score"] > ordinary["cliffhanger_score"]


def test_llm_candidate_scores_actual_screenplay_beats_not_generated_summary():
    from promoiq.engine import _scoring_evidence
    from promoiq.parser import TimedLine

    lines = [
        TimedLine(timestamp=7.2, timestamp_text="00:07.20",
                  end_timestamp=9.0, text="Juliana enters the altar.",
                  index=1, kind="action", speaker=None),
        TimedLine(timestamp=10.0, timestamp_text="00:10.00",
                  end_timestamp=12.0, text="JULIANA: Where is Gerald?",
                  index=2, kind="dialogue", speaker="JULIANA"),
        TimedLine(timestamp=30.0, timestamp_text="00:30.00",
                  end_timestamp=33.8, text="MATRIARCH: You should turn around, Juliana.",
                  index=3, kind="dialogue", speaker="MATRIARCH"),
    ]
    evidence = _scoring_evidence(lines, 7.2, 33.8)
    assert evidence["opening_text"] == "Juliana enters the altar."
    assert evidence["closing_text"] == "MATRIARCH: You should turn around, Juliana."


def test_evidence_inspector_selects_strongest_beats_inside_search_windows():
    from promoiq.engine import _scoring_evidence
    from promoiq.parser import TimedLine

    lines = [
        TimedLine(timestamp=1, timestamp_text="00:01.00", end_timestamp=2,
                  text="Juliana smiles at the wedding hall.", index=0, kind="action"),
        TimedLine(timestamp=4, timestamp_text="00:04.00", end_timestamp=5,
                  text="You look like a servant!", index=1, kind="dialogue", speaker="MATRIARCH"),
        TimedLine(timestamp=24, timestamp_text="00:24.00", end_timestamp=26,
                  text="The Matriarch whispers: turn around.", index=2, kind="dialogue", speaker="MATRIARCH"),
        TimedLine(timestamp=30, timestamp_text="00:30.00", end_timestamp=32,
                  text="Juliana walks toward the altar.", index=3, kind="action"),
    ]

    evidence = _scoring_evidence(lines, 1, 33)
    assert evidence["opening_text"] == "MATRIARCH: You look like a servant!"
    assert evidence["closing_text"] == "MATRIARCH: The Matriarch whispers: turn around."
    assert evidence["opening_timestamp"] == "00:04.00"
    assert evidence["closing_timestamp"] == "00:24.00"
    assert evidence["selection_method"] == "strongest_rule_based_signal_with_edge_tiebreak"
