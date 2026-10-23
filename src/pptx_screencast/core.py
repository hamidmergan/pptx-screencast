"""The two calls this package is for: write a script, and build a video.

`write_script` stops after the narration, so it can be read and corrected
before a single second of audio is paid for. `make_video` goes all the way
from the deck to the finished MP4 and can start from such a script file.
"""

import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Callable, List, Optional, Sequence, Union

from . import config
from .audio import speak_all
from .client import make_stt_client
from .errors import ScreencastError, SlideError, VideoError
from .generation import (
    check_count,
    generate_all_scripts,
    scripts_from_file,
    scripts_from_notes,
    translate_scripts,
)
from .llm import make_llm
from .naming import translate_stem
from .outro import create_outro_image, frame_clips, get_image_dimensions
from .paths import free_path, safe_stem, work_dir
from .script_file import write_script_file
from .selection import clip_pairs, slide_selection
from .slides import extract_notes_per_slide, extract_text_per_slide, pptx_to_images
from .stt import Recogniser
from .subtitles import create_subtitle_track, vtt_language_code
from .subtitle_converter import vtt_to_srt
from .tools import require_tools
from .video import (
    apply_faststart,
    burn_in_subtitles,
    concatenate_videos,
    create_slide_video,
)

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

# Called with the name of the step, the finished units and the total.
Progress = Callable[[str, int, int], None]


def _read_deck(read, pptx: Path) -> List[str]:
    """Read a deck and report an unreadable file as a SlideError.

    python-pptx raises a zipfile or a package error for a renamed .ppt, a
    truncated download or an export from another program. Those are not errors
    of this package, so the caller would see a traceback.
    """
    try:
        return read(pptx)
    except ScreencastError:
        raise
    except Exception as exc:
        raise SlideError(
            f"{pptx.name} could not be read as a PowerPoint file. "
            f"Make sure it is a .pptx saved by PowerPoint or LibreOffice: {exc}"
        )


def _deck_texts(pptx: Path) -> List[str]:
    texts = _read_deck(extract_text_per_slide, pptx)
    if not texts:
        raise SlideError(f"{pptx.name} holds no visible slide.")
    return texts


def _check_size(count: int, settings: config.Settings) -> None:
    if count > settings.max_slides:
        raise SlideError(
            f"The deck has {count} slides, at most {settings.max_slides} are "
            "built at once. Raise max_slides or pick a range with --slides."
        )


def _report(progress: Optional[Progress], step: str, done: int, total: int) -> None:
    if progress is not None:
        progress(step, done, total)


def build_scripts(
    pptx: Path,
    settings: config.Settings,
    *,
    script: Optional[PathLike] = None,
    notes: bool = False,
    translate: str = "",
    glossary: Optional[dict] = None,
    materials: Optional[Sequence[str]] = None,
    client=None,
    progress: Optional[Progress] = None,
) -> List[str]:
    """One narration per visible slide, from a file, the notes or the model.

    `glossary` is a mapping of term to replacement. It holds for the
    narration the model writes and for the translation. `materials` is extra
    text per slide, which the model may use to make the narration concrete.
    """
    slide_texts = _deck_texts(pptx)
    _check_size(len(slide_texts), settings)
    total = len(slide_texts)

    if script is not None:
        scripts = scripts_from_file(script, total)
    elif notes:
        scripts = scripts_from_notes(_read_deck(extract_notes_per_slide, pptx), total)
    else:
        _report(progress, "scripts", 0, total)
        llm = make_llm(settings, client)
        scripts = generate_all_scripts(
            slide_texts, llm, glossary=glossary, materials=materials,
            min_chars=settings.min_chars, max_chars=settings.max_chars,
            target_lang=settings.language,
        )
    scripts = check_count(scripts, total)

    if translate:
        _report(progress, "translate", 0, total)
        scripts = translate_scripts(
            scripts, translate, make_llm(settings, client), glossary=glossary
        )
    _report(progress, "scripts", total, total)
    return scripts


def write_script(
    pptx: PathLike,
    output: Optional[PathLike] = None,
    *,
    notes: bool = False,
    translate: str = "",
    glossary: Optional[dict] = None,
    materials: Optional[Sequence[str]] = None,
    client=None,
    progress: Optional[Progress] = None,
    **settings,
) -> Path:
    """Write the narration of a deck as a Markdown file and return its path.

    No audio is made, so no text-to-speech model and no voice are needed.
    """
    deck = Path(pptx)
    resolved = config.resolve(require_voice=False, **settings)
    scripts = build_scripts(
        deck, resolved, notes=notes, translate=translate, glossary=glossary,
        materials=materials, client=client, progress=progress,
    )
    target = Path(output) if output is not None else free_path(deck.with_suffix(".md"))
    return write_script_file(scripts, target, title=deck.stem)


def _slide_images(deck: Path, folder: Path, settings: config.Settings) -> List[Path]:
    return _read_deck(
        lambda path: pptx_to_images(
            path, folder, dpi=settings.resolution, max_workers=settings.max_workers
        ),
        deck,
    )


def _notice_clip(
    images: Sequence[Path], first_slide: int, tmp: Path, settings: config.Settings
) -> Optional[Path]:
    """The notice slide as a clip, or None when it could not be made."""
    try:
        width, height = get_image_dimensions(images[first_slide])
        picture = tmp / "notice.png"
        clip = tmp / "clip_notice.mp4"
        create_outro_image(width, height, picture)
        create_slide_video(
            picture, None, clip, pause=0.0, crf=settings.crf, fps=settings.fps
        )
        return clip
    except Exception as e:
        logger.warning("The notice slide could not be made, the video runs without it: %s", e)
        return None


def _write_subtitle_files(track: Path, output: Path) -> None:
    """The cues next to the video, once as VTT and once as SRT."""
    text = track.read_text(encoding="utf-8")
    output.with_suffix(".vtt").write_text(text, encoding="utf-8")
    output.with_suffix(".srt").write_text(vtt_to_srt(text), encoding="utf-8")


def make_video(
    pptx: PathLike,
    output: Optional[PathLike] = None,
    *,
    script: Optional[PathLike] = None,
    notes: bool = False,
    translate: str = "",
    glossary: Optional[dict] = None,
    materials: Optional[Sequence[str]] = None,
    slides: Optional[List[int]] = None,
    keep_work_dir: bool = False,
    client=None,
    stt_client=None,
    progress: Optional[Progress] = None,
    **settings,
) -> Path:
    """Turn a deck into a narrated MP4 and return the path it was written to.

    `script` reads the narration from a Markdown file instead of writing it,
    `notes` takes the speaker notes, `slides` limits the video to a few
    slides, counted from zero.
    """
    deck = Path(pptx)
    resolved = config.resolve(**settings)
    require_tools(render=True, video=True)

    scripts = build_scripts(
        deck, resolved, script=script, notes=notes, translate=translate,
        glossary=glossary, materials=materials, client=client, progress=progress,
    )
    selection = slide_selection(len(scripts), slides, None)
    if not selection.clip_slides:
        raise SlideError("No slide is left for the video, check --slides.")

    target = _output_path(deck, output, translate, resolved, client)

    with work_dir(resolved.work_dir, keep=keep_work_dir) as tmp:
        images = _slide_images(deck, _fresh(tmp / "images"), resolved)
        count = min(len(images), len(scripts))
        if count == 0:
            raise SlideError("The deck produced no slide image.")
        if len(images) != len(scripts):
            logger.error(
                "%s slide images but %s narrations, the video is cut to %s slides.",
                len(images), len(scripts), count,
            )

        _report(progress, "speak", 0, len(selection.clip_slides))
        audio_paths = speak_all(
            scripts, _fresh(tmp / "audio"), resolved,
            excluded=selection.excluded,
            on_slide_done=lambda done, total, _i: _report(progress, "speak", done, total),
            max_workers=resolved.max_workers,
        )

        pairs = clip_pairs(selection.clip_slides, count)
        clips = [tmp / f"clip_{position:03d}.mp4" for position, _ in pairs]
        total_clips = len(pairs)
        _report(progress, "video", 0, total_clips)
        _cut_clips(pairs, clips, images, audio_paths, resolved, progress, total_clips)

        has_speech = [audio_paths[index] is not None for _, index in pairs]
        # The notice has to come before the subtitles, otherwise every time is off.
        clips, has_speech = frame_clips(
            clips, has_speech, _notice_clip(images, pairs[0][1], tmp, resolved)
        )

        track = None
        if resolved.subtitles:
            _report(progress, "subtitles", 0, len(clips))
            track = _subtitle_track(
                clips, tmp, resolved, has_speech, stt_client,
                on_done=lambda done, total: _report(progress, "subtitles", done, total),
            )
            _report(progress, "subtitles", len(clips), len(clips))

        _report(progress, "join", 0, 1)
        joined = tmp / "joined.mp4"
        concatenate_videos(clips, joined)
        if track is not None and resolved.burn_in:
            joined = burn_in_subtitles(joined, track, tmp / "burned.mp4", crf=resolved.crf)

        final = tmp / "final.mp4"
        data = apply_faststart(
            joined, final,
            subtitle_path=track,
            subtitle_lang=vtt_language_code(translate or resolved.language),
        )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if track is not None:
                _write_subtitle_files(track, target)
        except OSError as exc:
            raise VideoError(f"The video could not be written to {target}: {exc}")
        _report(progress, "join", 1, 1)
    return target


def _cut_clips(
    pairs: Sequence[tuple],
    clips: Sequence[Path],
    images: Sequence[Path],
    audio_paths: Sequence[Optional[Path]],
    settings: config.Settings,
    progress: Optional[Progress],
    total: int,
) -> None:
    """One clip per slide, `max_workers` of them at the same time.

    Every clip is an encode of a still picture and does not depend on any
    other, so they are cut side by side, just like the rendering and the
    speaking.
    """
    done = [0]
    lock = Lock()

    def _one(item) -> None:
        (_position, index), clip = item
        create_slide_video(
            images[index], audio_paths[index], clip,
            pause=settings.slide_pause, crf=settings.crf, speed=settings.speed,
            fps=settings.fps,
        )
        if progress is None:
            return
        with lock:
            done[0] += 1
            _report(progress, "video", done[0], total)

    work = list(zip(pairs, clips))
    workers = max(1, min(settings.max_workers, len(work) or 1))
    if workers == 1:
        for item in work:
            _one(item)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(_one, work):
            pass


def _fresh(folder: Path) -> Path:
    """An empty folder, so a reused work directory holds nothing older."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _output_path(
    deck: Path, output: Optional[PathLike], translate: str, settings: config.Settings, client
) -> Path:
    """Where the MP4 goes, with a translated name when the language changed."""
    if output is not None:
        return Path(output)
    stem = safe_stem(deck.name)
    if translate:
        llm = make_llm(settings, client)
        stem = translate_stem(deck.name, translate, lambda text, lang: llm.translate_text(text, lang))
    return free_path(deck.with_name(f"{stem}.mp4"))


def _subtitle_track(
    clips: Sequence[Path],
    tmp: Path,
    settings: config.Settings,
    has_speech: Sequence[bool],
    stt_client,
    on_done=None,
) -> Optional[Path]:
    """The recognised cues of the whole video, or None without a model.

    The whole step is bounded by `stt_timeout`, so a recogniser that keeps
    asking for patience cannot hold the run for hours.
    """
    if stt_client is None and not settings.has_stt:
        logger.warning(
            "No speech recognition model is configured, so the video gets no "
            "subtitles. Set stt_model (--stt-model or PPTX_SCREENCAST_STT_MODEL)."
        )
        return None
    client = stt_client if stt_client is not None else make_stt_client(settings)
    recogniser = Recogniser(
        client, settings.stt_model, deadline=time.monotonic() + settings.stt_timeout
    )
    return create_subtitle_track(clips, tmp, recogniser, has_speech, on_done=on_done)


__all__ = ["build_scripts", "make_video", "write_script"]
