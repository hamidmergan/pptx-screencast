"""Subtitle track for the screencast: recognise per slide, shift, merge."""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Sequence

from .subtitle_converter import segments_to_srt, segments_to_vtt, split_long_segments

logger = logging.getLogger(__name__)

# Code of the subtitle track in the MP4, ISO 639-2.
_LANGUAGE_CODES = {
    "DE": "deu", "EN": "eng", "FR": "fra", "ES": "spa",
    "IT": "ita", "TR": "tur", "AR": "ara", "RU": "rus",
}

# Concurrent requests to the speech recogniser.
_PARALLEL = 4


def vtt_language_code(target_lang: str) -> str:
    """Three-letter code for the track, empty when the language is unknown."""
    return _LANGUAGE_CODES.get((target_lang or "").split("-")[0].upper(), "")


def transcribe_slides(audio_paths: Sequence[Optional[Path]], client) -> List[List[dict]]:
    """The timestamped segments per slide, an error yields an empty list."""
    def _one(path: Optional[Path]) -> List[dict]:
        if path is None or not path.exists() or path.stat().st_size == 0:
            return []
        try:
            segments, _ = client.transcribe_verbose(str(path))
            return segments or []
        except Exception as e:
            logger.warning("No subtitles recognised for %s: %s", path.name, e)
            return []

    with ThreadPoolExecutor(max_workers=_PARALLEL) as pool:
        return list(pool.map(_one, audio_paths))


def shift_segments(
    slide_segments: Sequence[Sequence[dict]], clip_durations: Sequence[float]
) -> List[dict]:
    """Move every segment behind the clips that run before it."""
    shifted: List[dict] = []
    offset = 0.0
    for i, segments in enumerate(slide_segments):
        for seg in segments or []:
            if not str(seg.get("text", "")).strip():
                continue
            shifted.append({
                "start": seg["start"] + offset,
                "end": seg["end"] + offset,
                "text": str(seg["text"]).strip(),
            })
        offset += clip_durations[i] if i < len(clip_durations) else 0.0
    return shifted


def build_subtitle_vtt(
    slide_segments: Sequence[Sequence[dict]], clip_durations: Sequence[float]
) -> str:
    """Shift segments, split overlong cues and output them as one VTT."""
    shifted = shift_segments(slide_segments, clip_durations)
    if not shifted:
        return ""
    return segments_to_vtt(split_long_segments(shifted))


def build_subtitle_srt(
    slide_segments: Sequence[Sequence[dict]], clip_durations: Sequence[float]
) -> str:
    """The same cues as SRT."""
    shifted = shift_segments(slide_segments, clip_durations)
    if not shifted:
        return ""
    return segments_to_srt(split_long_segments(shifted))


def audio_of_clip(clip: Path, target: Path) -> Optional[Path]:
    """Take the audio track out of a finished clip without re-encoding it."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-vn", "-c:a", "copy", str(target)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not target.exists():
        logger.warning("The audio of %s cannot be read: %s", clip.name, result.stderr[-200:])
        return None
    return target


def create_subtitle_track(
    clip_paths: Sequence[Path],
    tmp: Path,
    client,
    has_speech: Optional[Sequence[bool]] = None,
) -> Optional[Path]:
    """Recognise subtitles per clip and store them as VTT, silent slides stay out."""
    from .video import get_video_duration

    try:
        audios = [
            audio_of_clip(clip, tmp / f"stt_{i:03d}.m4a")
            if has_speech is None or (i < len(has_speech) and has_speech[i])
            else None
            for i, clip in enumerate(clip_paths)
        ]
        slide_segments = transcribe_slides(audios, client)
        durations = [get_video_duration(p) for p in clip_paths]
        track_text = build_subtitle_vtt(slide_segments, durations)
    except Exception as e:
        logger.warning("The subtitles could not be made: %s", e)
        return None
    if not track_text:
        logger.warning("Subtitles: the speech recogniser returned nothing")
        return None
    track = tmp / "subtitles.vtt"
    track.write_text(track_text, encoding="utf-8")
    return track
