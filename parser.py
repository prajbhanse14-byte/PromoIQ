"""Parsers for PromoIQ screenplay inputs.

Supports both:
1. Block-format scripts used in the 50-episode input pack:
   **JULIANA (Urgent):**\n   Start: (00:07.00) | End: (00:11.10)\n   "Keep your head down..."
2. Legacy one-line timestamped dialogue/action:
   00:01:12.5 - MAYA: Don't open that door!
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import List, Optional

# MM:SS[.fraction] or HH:MM:SS[.fraction]
_TIME = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,3})?"
_BLOCK_LINE = re.compile(
    rf"^\s*Start\s*:\s*\(?\s*(?P<start>{_TIME})\s*\)?\s*\|\s*"
    rf"End\s*:\s*\(?\s*(?P<end>{_TIME})\s*\)?\s*$",
    re.IGNORECASE,
)
_INLINE_TS = re.compile(rf"(?<![\d:])(?P<stamp>{_TIME})(?![\d:])")
_HEADING = re.compile(r"^\s*\*\*(?P<label>.+?)\*\*\s*:?[ \t]*$")
_SCENE = re.compile(r"^\s*SCENE\s+(?P<number>\d+)\s*$", re.IGNORECASE)
_SCENE_HEADING = re.compile(r"^\s*Scene\s+heading\s*:\s*(?P<heading>.+?)\s*$", re.IGNORECASE)
_STRUCTURAL = re.compile(r"^\s*(?:---\s*SCRIPT\s+END\s*---|SCENE\s+\d+)\s*$", re.IGNORECASE)


@dataclass
class TimedLine:
    # `timestamp` remains the block start for compatibility with the original engine.
    timestamp: float
    timestamp_text: str
    text: str
    index: int
    end_timestamp: Optional[float] = None
    end_timestamp_text: Optional[str] = None
    kind: str = "unknown"
    label: str = ""
    speaker: str = ""
    scene_number: Optional[int] = None
    scene_heading: str = ""

    def __post_init__(self) -> None:
        if self.end_timestamp is None:
            self.end_timestamp = self.timestamp
        if self.end_timestamp_text is None:
            self.end_timestamp_text = self.timestamp_text

    def to_dict(self):
        return asdict(self)


def to_seconds(value: str) -> float:
    """Convert MM:SS or HH:MM:SS timestamps to episode-relative seconds."""
    parts = value.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = int(parts[0]), float(parts[1])
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"Unsupported timestamp: {value!r}")


def _clean_label(raw: str) -> str:
    return raw.strip().strip("*").strip().rstrip(":").strip()


def _classify(label: str) -> tuple[str, str]:
    """Return (kind, speaker) from a screenplay block label."""
    value = _clean_label(label)
    upper = value.upper()
    if upper == "CAMERA":
        return "camera", ""
    if upper == "ACTION":
        return "action", ""
    if upper in {"SOUND FX", "SOUND EFFECT", "SOUND EFFECTS", "SFX"}:
        return "sound", ""
    # Dialogue labels conventionally use a character name, optionally followed
    # by performance direction in parentheses, e.g. JULIANA (Urgent).
    speaker = re.split(r"\s*\(", value, maxsplit=1)[0].strip()
    return "dialogue", speaker


def _previous_heading(lines: list[str], index: int) -> str:
    """Find the nearest preceding nonblank bold heading, if one exists."""
    i = index - 1
    while i >= 0 and not lines[i].strip():
        i -= 1
    if i >= 0:
        match = _HEADING.match(lines[i])
        if match:
            return _clean_label(match.group("label"))
    return ""


def parse_screenplay(text: str) -> List[TimedLine]:
    """Parse screenplay blocks into timed text records.

    In the Kuku input format, the timestamp line is followed by its content on
    the next line. This parser binds those two lines together and preserves the
    full start/end interval, block category, speaker and scene metadata.
    """
    source_lines = text.splitlines()
    parsed: list[TimedLine] = []
    current_scene_number: Optional[int] = None
    current_scene_heading = ""
    i = 0

    while i < len(source_lines):
        raw = source_lines[i]

        scene_match = _SCENE.match(raw)
        if scene_match:
            current_scene_number = int(scene_match.group("number"))
            i += 1
            continue

        scene_heading_match = _SCENE_HEADING.match(raw)
        if scene_heading_match:
            current_scene_heading = scene_heading_match.group("heading").strip()
            i += 1
            continue

        block_match = _BLOCK_LINE.match(raw)
        if block_match:
            start_text = block_match.group("start")
            end_text = block_match.group("end")
            start_seconds = to_seconds(start_text)
            end_seconds = to_seconds(end_text)
            if end_seconds < start_seconds:
                raise ValueError(
                    f"Block end precedes start at input line {i + 1}: {raw.strip()}"
                )

            # Skip blank lines between the interval and its content.
            body_index = i + 1
            while body_index < len(source_lines) and not source_lines[body_index].strip():
                body_index += 1
            body = source_lines[body_index].strip() if body_index < len(source_lines) else ""
            if not body:
                raise ValueError(f"Timed block at input line {i + 1} has no content")

            label = _previous_heading(source_lines, i)
            kind, speaker = _classify(label)
            # Keep original screenplay wording, but remove markdown quote wrapping
            # only when the entire line is a quoted dialogue utterance.
            parsed.append(
                TimedLine(
                    timestamp=start_seconds,
                    timestamp_text=start_text,
                    end_timestamp=end_seconds,
                    end_timestamp_text=end_text,
                    text=body,
                    index=len(parsed),
                    kind=kind,
                    label=label,
                    speaker=speaker,
                    scene_number=current_scene_number,
                    scene_heading=current_scene_heading,
                )
            )
            i = body_index + 1
            continue

        # Backwards-compatible legacy parser for single-line timestamped text.
        # Do not reinterpret block metadata or scene-level start/end metadata.
        if not re.match(r"^\s*(?:Start|End|Scene\s+start|Scene\s+end)\s*:", raw, re.I):
            inline_match = _INLINE_TS.search(raw)
            if inline_match:
                stamp = inline_match.group("stamp")
                remainder = (raw[:inline_match.start()] + raw[inline_match.end():]).strip(
                    " \t-:|[]()"
                )
                if remainder:
                    seconds = to_seconds(stamp)
                    parsed.append(
                        TimedLine(
                            timestamp=seconds,
                            timestamp_text=stamp,
                            end_timestamp=seconds,
                            end_timestamp_text=stamp,
                            text=remainder,
                            index=len(parsed),
                            kind="legacy",
                        )
                    )
        i += 1

    # Stable chronological ordering. Equal-start-time overlapping camera/action/
    # dialogue blocks retain the order in which they appeared in the screenplay.
    parsed.sort(key=lambda item: (item.timestamp, item.index))
    return parsed
