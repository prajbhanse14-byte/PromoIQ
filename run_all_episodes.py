"""Run PromoIQ's parser and deterministic candidate baseline over input_data/."""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from statistics import mean

from promoiq.engine import analyse_episode
from promoiq.parser import parse_screenplay

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input_data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
EPISODE_RE = re.compile(r"^EPISODE NUMBER\s*:\s*Episode\s+(\d+)\s*$", re.I | re.M)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR,
                        help="Folder containing one episode .txt file per script")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR,
                        help="Folder for JSON, CSV and text outputs")
    args = parser.parse_args()

    script_files = sorted(args.input_dir.glob("*.txt"))
    if not script_files:
        raise SystemExit(f"No .txt episode scripts found in {args.input_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    episode_rows = []
    ranked = []
    total_blocks = 0
    scene_keys = set()
    aggregate_kind_counts = {"dialogue": 0, "action": 0, "camera": 0, "sound": 0}

    for path in script_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        match = EPISODE_RE.search(text)
        episode = f"Episode {int(match.group(1))}" if match else path.stem
        parsed = parse_screenplay(text)
        result = analyse_episode(text, episode, use_llm=True)
        total_blocks += len(parsed)
        scene_keys.update((episode, line.scene_number) for line in parsed if line.scene_number is not None)
        counts = {kind: sum(line.kind == kind for line in parsed)
                  for kind in ("dialogue", "action", "camera", "sound")}
        for kind, count in counts.items():
            aggregate_kind_counts[kind] += count
        episode_rows.append({
            "episode": episode,
            "filename": path.name,
            "parsed_blocks": len(parsed),
            "dialogue_blocks": counts["dialogue"],
            "action_blocks": counts["action"],
            "camera_blocks": counts["camera"],
            "sound_blocks": counts["sound"],
            "candidate_count": len(result.get("promos", [])),
            "status": result["status"],
        })
        results.append(result)
        ranked.extend(result.get("promos", []))

    ranked.sort(key=lambda item: item["scores"]["total_score"], reverse=True)
    raw = {
        "project": "PromoIQ",
        "run_type": "corrected_parser_full_pack_heuristic_baseline",
        "source_file_count": len(script_files),
        "parsed_timed_blocks": total_blocks,
        "results": results,
        "ranked_promos": ranked,
    }
    (args.output_dir / "PromoIQ_parserfix_full_run.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with (args.output_dir / "PromoIQ_parserfix_episode_report.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(episode_rows[0].keys()))
        writer.writeheader()
        writer.writerows(episode_rows)

    candidate_rows = []
    for rank, candidate in enumerate(ranked, 1):
        segment = candidate["segments"][0]
        scores = candidate["scores"]
        candidate_rows.append({
            "rank": rank,
            "episode": candidate["episode"],
            "scene_number": candidate.get("scene_number"),
            "scene_heading": candidate.get("scene_heading"),
            "start": segment["start_timestamp"],
            "end": segment["end_timestamp"],
            "start_seconds": segment["start_seconds"],
            "end_seconds": segment["end_seconds"],
            "duration_seconds": round(segment["end_seconds"] - segment["start_seconds"], 2),
            "score": scores["total_score"],
            "hook_score": scores["hook_score"],
            "cliffhanger_score": scores["cliffhanger_score"],
            "standalone_score": scores["standalone_score"],
            "duration_score": scores["duration_score"],
            "hook": candidate["hook"],
            "cliffhanger": candidate["cliffhanger"],
            "why_it_works": candidate.get("why_it_works", ""),
            "standalone_context": candidate.get("standalone_context", ""),
            "quality_tier": candidate.get("quality_tier", "llm_review"),
            "review_flags": ";".join(candidate.get("review_flags", [])),
            "multi_segment_plan": json.dumps(candidate.get("multi_segment_plan"), ensure_ascii=False),
            "method": candidate["method"],
        })
    with (args.output_dir / "PromoIQ_parserfix_ranked_candidates.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(candidate_rows[0].keys()) if candidate_rows else ["rank"])
        writer.writeheader()
        writer.writerows(candidate_rows)

    scores = [c["scores"]["total_score"] for c in ranked]
    durations = [c["segments"][0]["end_seconds"] - c["segments"][0]["start_seconds"] for c in ranked]
    summary = [
        "PromoIQ parser fix — full-pack run",
        "====================================",
        f"Scripts processed: {len(script_files)}",
        f"Scenes detected: {len(scene_keys)}",
        f"Timed screenplay blocks parsed: {total_blocks}",
        f"Block types: {aggregate_kind_counts}",
        f"Candidates generated: {len(ranked)}",
        f"Episodes with candidates: {sum(bool(r.get('promos')) for r in results)} / {len(results)}",
        f"Candidates within 20–60 seconds: {sum(20 <= d <= 60 for d in durations)} / {len(durations)}",
        f"Score range: {min(scores) if scores else 'n/a'}–{max(scores) if scores else 'n/a'}",
        f"Unique score values: {len(set(scores))}",
        f"Mean score: {mean(scores):.1f}" if scores else "Mean score: n/a",
        f"Episode statuses: {dict((status, sum(r['status'] == status for r in results)) for status in sorted({r['status'] for r in results}))}",
        f"Candidate methods: {dict((method, sum(c.get('method') == method for c in ranked)) for method in sorted({c.get('method', 'unknown') for c in ranked}))}",
        "LLM mode: status is reported per episode above; do not infer successful LLM processing from API configuration alone.",
        "Review caveat: heuristic candidates are ranked suggestions, not editor-approved promos.",
        "Video footage is still required to verify cut points, visuals, audio sync and editorial suitability.",
    ]
    (args.output_dir / "PromoIQ_parserfix_run_report.txt").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print("\n".join(summary))
    print("\nTop 10:")
    for candidate in ranked[:10]:
        segment = candidate["segments"][0]
        print(f"{candidate['episode']:>10} | {segment['start_timestamp']}–{segment['end_timestamp']} | "
              f"{candidate['scores']['total_score']:>5} | {candidate['hook'][:100]}")


if __name__ == "__main__":
    main()
