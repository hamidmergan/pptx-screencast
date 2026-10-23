"""ffmpeg helpers: audio length, one clip per slide, concat, faststart."""

import logging
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from .errors import VideoError
from .outro import NOTICE_TEXT
from .process import run_proc

logger = logging.getLogger(__name__)

# Padding on the image length so the audio and not the image decides the end.
_IMAGE_RESERVE = 2.0

# Frames per second for the still, at 1 a slide under a second gets no frame
# at all. The default of the `fps` setting, which every caller may override.
_FRAME_RATE = 5

# Seconds a slide without narration stays on screen.
SILENT_DURATION = 3.0

# Seconds the single steps may take. A run that takes longer is stuck, and a
# stuck ffmpeg has to end as a VideoError and not as a traceback.
PROBE_TIMEOUT = 60
CLIP_TIMEOUT = 300
PAUSE_TIMEOUT = 30
SPEED_TIMEOUT = 120
CONCAT_TIMEOUT = 300
FILTER_LIST_TIMEOUT = 30
BURN_IN_TIMEOUT = 1800
FASTSTART_TIMEOUT = 600


def _concat_entry(path: Path) -> str:
    """One line of an ffmpeg concat list, for any path at all.

    The entry is quoted, and a quote inside the path is closed, escaped and
    reopened the way a shell does it. Inside single quotes nothing else needs
    escaping, so a comma, a colon, a bracket and a backslash come through as
    they are. Measured against real ffmpeg with a path holding each of them.
    """
    quoted = str(Path(path).resolve()).replace("'", "'\\''")
    return f"file '{quoted}'\n"


def _run(cmd: List[str], timeout: int, what: str) -> subprocess.CompletedProcess:
    """Run ffmpeg or ffprobe, every system failure leaves as a VideoError."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise VideoError(f"{what} did not finish within {timeout} seconds.")
    except OSError as exc:
        raise VideoError(f"{what} could not be started: {exc}")


def _proc(cmd: List[str], timeout: int, what: str) -> subprocess.CompletedProcess:
    """The same for the calls that run in their own session."""
    try:
        return run_proc(cmd, timeout=timeout)
    except OSError as exc:
        raise VideoError(f"{what} could not be started: {exc}")


def get_audio_duration(audio_path: Optional[Path]) -> float:
    """Audio length in seconds from the counted packets, 3.0 for silent slides."""
    if audio_path is None:
        return SILENT_DURATION
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "packet=duration_time",
        "-of", "csv=p=0",
        str(audio_path),
    ]
    result = _run(cmd, PROBE_TIMEOUT, "Measuring the audio length")
    if result.returncode != 0:
        raise VideoError(f"ffprobe failed: {result.stderr[:200]}")
    total = 0.0
    for line in result.stdout.splitlines():
        try:
            total += float(line.strip().rstrip(","))
        except ValueError:
            continue
    if total <= 0:
        raise VideoError(f"The audio length cannot be measured: {audio_path}")
    return total


def get_video_duration(video_path: Path) -> float:
    """Length of a finished clip in seconds, it gives the offset of the next slide."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(video_path),
    ]
    result = _run(cmd, PROBE_TIMEOUT, "Measuring the clip length")
    if result.returncode != 0:
        raise VideoError(f"ffprobe failed: {result.stderr[:200]}")
    try:
        return float(result.stdout.strip().rstrip(","))
    except ValueError:
        raise VideoError(f"The clip length cannot be measured: {video_path}")


def apply_speed(audio_path: Path, output_path: Path, speed: float) -> Path:
    """Slow down or speed up locally, so the pitch of the voice stays."""
    stretched = output_path.with_suffix(".speed.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-filter:a", f"atempo={speed}",
        "-c:a", "libmp3lame", "-q:a", "2", str(stretched),
    ]
    result = _proc(cmd, SPEED_TIMEOUT, "Changing the speed")
    if result.returncode != 0:
        logger.warning(
            "Speed %s cannot be applied, taking the audio as it is: %s",
            speed, result.stderr[-200:],
        )
        return audio_path
    return stretched


def create_slide_video(
    image_path: Path,
    audio_path: Optional[Path],
    output_path: Path,
    pause: float = 0.0,
    crf: int = 23,
    silent_duration: float = SILENT_DURATION,
    speed: float = 1.0,
    fps: int = _FRAME_RATE,
) -> None:
    """Assemble a slide image with its audio into a clip.

    `fps` is the frame rate of the still picture. More frames make scrubbing
    smoother and the file bigger, the picture itself does not change.
    """
    fps = max(1, int(fps or _FRAME_RATE))
    # Missing and empty audio files count the same as None, the slide stays silent.
    if audio_path is not None and (not audio_path.exists() or audio_path.stat().st_size == 0):
        logger.warning("The audio file %s is empty or missing, the slide stays silent", audio_path)
        audio_path = None

    if audio_path is None:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", str(fps), "-i", str(image_path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(silent_duration),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
            "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
            "-shortest",
            str(output_path),
        ]
        result = _proc(cmd, CLIP_TIMEOUT, "Building the silent clip")
        if result.returncode != 0:
            logger.error("The clip could not be built (rc=%s): %s", result.returncode, result.stderr[-500:])
            raise VideoError(f"The silent clip could not be built: {result.stderr[-300:]}")
        return

    # Many servers lower the pitch when they slow a voice down, so it happens here.
    if speed and abs(speed - 1.0) > 0.001:
        audio_path = apply_speed(audio_path, output_path, speed)

    duration = get_audio_duration(audio_path)

    if pause > 0:
        silence_path = output_path.with_suffix(".silence.mp3")
        cmd_silence = [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t", str(pause),
            "-ac", "2", "-ar", "44100",
            "-c:a", "libmp3lame", str(silence_path),
        ]
        silence = _proc(cmd_silence, PAUSE_TIMEOUT, "Making the pause")
        if silence.returncode != 0:
            raise VideoError(f"The pause could not be made: {silence.stderr[-300:]}")

        audio_with_pause_path = output_path.with_suffix(".paused.mp3")
        concat_audio_file = output_path.with_suffix(".audiolist.txt")
        with open(concat_audio_file, "w", encoding="utf-8") as handle:
            # Absolute, because ffmpeg resolves an entry against the list file.
            handle.write(_concat_entry(audio_path))
            handle.write(_concat_entry(silence_path))
        cmd_concat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_audio_file),
            "-c", "copy", str(audio_with_pause_path),
        ]
        joined = _proc(cmd_concat, PAUSE_TIMEOUT, "Putting the pause behind the narration")
        if joined.returncode != 0:
            raise VideoError(
                f"The pause could not be put behind the narration: {joined.stderr[-300:]}"
            )
        final_audio = audio_with_pause_path
        image_duration = duration + pause + _IMAGE_RESERVE
    else:
        final_audio = audio_path
        image_duration = duration + _IMAGE_RESERVE

    # -t only bounds the image, -shortest ends the clip at the end of the audio.
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(fps), "-t", str(image_duration), "-i", str(image_path),
        "-i", str(final_audio),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
        "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-shortest",
        str(output_path),
    ]
    result = _proc(cmd, CLIP_TIMEOUT, "Building the clip")
    if result.returncode != 0:
        logger.error("The clip could not be built (rc=%s): %s", result.returncode, result.stderr[-500:])
        raise VideoError(f"The clip could not be built: {result.stderr[-300:]}")


def concatenate_videos(video_paths: List[Path], output_path: Path) -> None:
    """Put the clips of all slides into one MP4, without re-encoding."""
    concat_file = output_path.parent / "concat_list.txt"
    with open(concat_file, "w", encoding="utf-8") as handle:
        for path in video_paths:
            # Absolute, because ffmpeg resolves an entry against the list file.
            handle.write(_concat_entry(path))

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_path),
    ]
    result = _run(cmd, CONCAT_TIMEOUT, "Joining the clips")
    if result.returncode != 0:
        logger.error("The clips could not be joined: %s", result.stderr[:300])
        raise VideoError(f"The clips could not be joined: {result.stderr[:200]}")


# The filter's own option parser reads these, so they need the inner level.
_OPTION_SPECIAL = ("\\", ":", "=", "'")

# The filter graph around it reads these, which is the outer level.
_GRAPH_SPECIAL = ("\\", "'", "[", "]", ",", ";")


def _escape_filter_path(path: Path) -> str:
    """A path the way the ffmpeg filter graph wants to read it.

    ffmpeg takes a filter description apart twice. The graph parser splits on
    the commas and semicolons and reads the brackets and the quoting, then the
    filter's option parser splits the rest on the colons and equal signs and
    reads the quoting again. A colon in a path therefore has to arrive as two
    backslashes and a colon, and a quote as three backslashes and a quote.
    Measured against real ffmpeg with paths holding each of these characters.
    """
    text = str(path)
    for char in _OPTION_SPECIAL:
        text = text.replace(char, "\\" + char)
    for char in _GRAPH_SPECIAL:
        text = text.replace(char, "\\" + char)
    return text


@lru_cache(maxsize=1)
def has_burn_in_support() -> bool:
    """True when this ffmpeg was built with the subtitles filter.

    The filter needs libass. A build without it can still write a subtitle
    track into the file, it just cannot draw the cues into the picture.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=FILTER_LIST_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.split()[1:2] == ["subtitles"] for line in result.stdout.splitlines())


def burn_in_subtitles(
    input_path: Path, subtitle_path: Path, output_path: Path, crf: int = 23
) -> Path:
    """Draw the cues into the picture, which means the video is encoded again."""
    if not has_burn_in_support():
        logger.warning(
            "This ffmpeg has no subtitles filter, so the cues stay in their own "
            "track instead of being drawn into the picture."
        )
        return input_path
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"subtitles=filename={_escape_filter_path(subtitle_path)}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-c:a", "copy",
        str(output_path),
    ]
    try:
        result = _run(cmd, BURN_IN_TIMEOUT, "Burning the subtitles in")
    except VideoError as exc:
        # The cues stay in their own track, which is a video the user can watch.
        logger.warning("The subtitles could not be burned in: %s", exc)
        return input_path
    if result.returncode != 0:
        logger.warning(
            "The subtitles could not be burned in, the video keeps its own track: %s",
            result.stderr[-300:],
        )
        return input_path
    return output_path


def apply_faststart(
    input_path: Path,
    output_path: Path,
    subtitle_path: Optional[Path] = None,
    subtitle_lang: str = "",
    notice: str = NOTICE_TEXT,
) -> bytes:
    """Faststart for the network, the subtitle track comes in without re-encoding."""
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    if subtitle_path is not None:
        cmd += ["-i", str(subtitle_path)]
    cmd += ["-map", "0"]
    if subtitle_path is not None:
        cmd += ["-map", "1:0", "-c:s", "mov_text"]
        if subtitle_lang:
            cmd += ["-metadata:s:s:0", f"language={subtitle_lang}"]
    # A mark on the file so it can be read without watching the video.
    if notice:
        cmd += ["-metadata", f"comment={notice}"]
    cmd += ["-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", str(output_path)]
    try:
        result = _run(cmd, FASTSTART_TIMEOUT, "The faststart pass")
    except VideoError as exc:
        # Faststart is for streaming only, the file itself plays without it.
        logger.warning("The faststart pass failed: %s", exc)
        return _read(input_path)
    if result.returncode != 0:
        logger.warning("The faststart pass failed (rc=%s): %s", result.returncode, result.stderr[:300])
        return _read(input_path)
    return _read(output_path)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise VideoError(f"The finished video could not be read from {path}: {exc}")
