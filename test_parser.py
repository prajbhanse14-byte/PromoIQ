from pathlib import Path

import pytest

from promoiq.parser import parse_screenplay, to_seconds
from promoiq.engine import analyse_episode
from promoiq.scoring import score_candidate


def test_timestamp_parser_legacy_inline_format():
    lines = parse_screenplay("00:00:01.5 - A: Hello\n[00:00:03] B: Wait!")
    assert len(lines) == 2
    assert lines[0].timestamp == 1.5
    assert lines[1].timestamp == 3
    assert lines[0].end_timestamp == 1.5
    assert lines[0].text == "A: Hello"


def test_block_format_binds_heading_interval_and_body():
    source = '''SCENE 01
Scene heading: INT. ROOM – NIGHT
**JULIANA (Urgent, Whispering):**
Start: (00:07.00) | End: (00:11.10)
"Keep your head down. If anyone recognizes you, everything is over."

**CAMERA:**
Start: (00:11.10) | End: (00:14.20)
Medium close-up of Juliana.
'''
    lines = parse_screenplay(source)
    assert len(lines) == 2
    assert lines[0].timestamp == 7
    assert lines[0].end_timestamp == 11.1
    assert lines[0].kind == "dialogue"
    assert lines[0].speaker == "JULIANA"
    assert "Keep your head down" in lines[0].text
    assert lines[0].scene_number == 1
    assert lines[0].scene_heading == "INT. ROOM – NIGHT"
    assert lines[1].kind == "camera"


def test_scene_metadata_is_not_mistaken_for_timed_content():
    lines = parse_screenplay("SCENE 01\nScene start: 00:00.00\nScene end: 00:42.50\n")
    assert lines == []


def test_rejects_block_with_end_before_start():
    with pytest.raises(ValueError, match="end precedes start"):
        parse_screenplay("**ACTION:**\nStart: (00:12.00) | End: (00:10.00)\nRuns away.")


def test_to_seconds_supports_minute_and_hour_formats():
    assert to_seconds("01:12.5") == 72.5
    assert to_seconds("01:02:03.5") == 3723.5


def test_duration_score_prefers_assignment_range():
    inside = score_candidate("secret reveal", 35)
    outside = score_candidate("secret reveal", 90)
    assert inside["duration_score"] > outside["duration_score"]


def test_all_50_real_episodes_parse_complete_timed_blocks():
    project_root = Path(__file__).resolve().parents[1]
    scripts = sorted((project_root / "input_data").glob("episode-*.txt"))
    assert len(scripts) == 50

    all_lines = []
    category_counts = {"camera": 0, "action": 0, "sound": 0, "dialogue": 0}
    for script in scripts:
        parsed = parse_screenplay(script.read_text(encoding="utf-8"))
        assert parsed, script.name
        for line in parsed:
            assert line.text.strip(), (script.name, line)
            assert line.end_timestamp >= line.timestamp, (script.name, line)
            assert line.kind in category_counts, (script.name, line.kind)
            category_counts[line.kind] += 1
        all_lines.extend(parsed)

    assert len(all_lines) == 3727
    assert category_counts == {
        "camera": 1754,
        "action": 372,
        "sound": 114,
        "dialogue": 1487,
    }


def test_full_pack_analysis_produces_candidates_with_real_script_text():
    project_root = Path(__file__).resolve().parents[1]
    scripts = sorted((project_root / "input_data").glob("episode-*.txt"))
    assert len(scripts) == 50

    analysed_episodes = 0
    candidate_total = 0
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        result = analyse_episode(text, script.stem, use_llm=False)
        assert result["parsed_lines"] > 0, script.name
        assert result["promos"], script.name
        analysed_episodes += 1
        candidate_total += len(result["promos"])
        for promo in result["promos"]:
            segment = promo["segments"][0]
            duration = segment["end_seconds"] - segment["start_seconds"]
            assert 20 <= duration <= 60
            assert promo["source_excerpt"].strip()
            assert promo["hook"].strip()
            assert promo["cliffhanger"].strip()
            assert not promo["hook"].startswith("Start:")
            assert not promo["cliffhanger"].startswith("End:")

    assert analysed_episodes == 50
    assert candidate_total > 0
