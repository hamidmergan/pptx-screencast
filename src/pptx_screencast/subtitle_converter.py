"""Subtitles: write segments as VTT or SRT, split them and read VTT back."""

from __future__ import annotations

import re

# Broadcast standard limits for one cue.
MAX_CHARS_PER_LINE = 42
MAX_LINES_PER_CUE = 2

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _fmt_vtt_time(seconds: float) -> str:
    """Format seconds as a WebVTT timestamp ``HH:MM:SS.mmm``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _fmt_srt_time(seconds: float) -> str:
    """The same timestamp the way SRT writes it, with a comma."""
    return _fmt_vtt_time(seconds).replace(".", ",")


def segments_to_vtt(segments: list[dict]) -> str:
    """Convert segments to a WebVTT string."""
    lines: list[str] = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_vtt_time(seg['start'])} --> {_fmt_vtt_time(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def segments_to_srt(segments: list[dict]) -> str:
    """Convert segments to an SRT string."""
    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(seg['start'])} --> {_fmt_srt_time(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def _parse_vtt_time(s: str) -> float:
    """Read a WebVTT or SRT timestamp (``HH:MM:SS.mmm`` or ``MM:SS.mmm``) as seconds."""
    parts = s.replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, sec = parts
        return int(h) * 3600 + int(m) * 60 + float(sec)
    if len(parts) == 2:
        m, sec = parts
        return int(m) * 60 + float(sec)
    return float(s)


def vtt_to_segments(raw: str) -> list[dict]:
    """Read a WebVTT string back into ``{start, end, text}`` segments."""
    segments: list[dict] = []
    lines = raw.replace("\r", "").split("\n")
    i = 0
    while i < len(lines):
        arrow = lines[i].find("-->")
        if arrow == -1:
            i += 1
            continue
        try:
            start = _parse_vtt_time(lines[i][:arrow].strip())
            end = _parse_vtt_time(lines[i][arrow + 3:].strip().split(" ")[0])
        except (ValueError, IndexError):
            i += 1
            continue
        i += 1
        text_lines: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            text_lines.append(lines[i])
            i += 1
        if text_lines:
            segments.append({"start": start, "end": end, "text": " ".join(text_lines).strip()})
        i += 1
    return segments


def vtt_to_srt(raw: str) -> str:
    """The same cues as SRT, for players that cannot read VTT."""
    return segments_to_srt(vtt_to_segments(raw))


def _lines(text: str, max_line: int) -> list[str]:
    """Pack words into lines, a single overlong word stays whole."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and len(candidate) > max_line:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _pieces(text: str, max_line: int, max_lines: int) -> list[str]:
    """Split text into cues, preferably at the end of a sentence."""
    parts: list[list[str]] = []
    for sentence in _SENTENCE_END.split(text):
        if not sentence.strip():
            continue
        lines = _lines(sentence, max_line)
        for i in range(0, len(lines), max_lines):
            parts.append(lines[i:i + max_lines])
    joined: list[list[str]] = []
    for part in parts:
        # Two short sentences may share one cue.
        if joined and len(joined[-1]) + len(part) <= max_lines:
            joined[-1] = joined[-1] + part
        else:
            joined.append(part)
    return ["\n".join(p) for p in joined]


def split_long_segments(
    segments: list[dict],
    max_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES_PER_CUE,
) -> list[dict]:
    """Split long segments into short cues, the time shared by character count."""
    out: list[dict] = []
    for seg in segments:
        text = " ".join(str(seg.get("text", "")).split())
        if not text:
            continue
        lines = _lines(text, max_line)
        if len(lines) <= max_lines:
            out.append({**seg, "text": "\n".join(lines)})
            continue
        pieces = _pieces(text, max_line, max_lines)
        total = sum(len(p) for p in pieces)
        start, end = float(seg["start"]), float(seg["end"])
        span = end - start
        run = 0
        edge = start
        for i, piece in enumerate(pieces):
            run += len(piece)
            following = end if i == len(pieces) - 1 else start + span * run / total
            out.append({**seg, "start": edge, "end": following, "text": piece})
            edge = following
    return out
