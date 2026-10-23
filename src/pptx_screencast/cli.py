import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .core import make_video, write_script
from .errors import ScreencastError
from .selection import parse_slides

LOOPBACK = ("127.0.0.1", "localhost", "::1")

UI_HINT = (
    "The web page needs the extra packages. Install them with "
    "'pip install \"pptx-screencast[ui]\"'."
)

NO_LOGIN = (
    "Warning: the page has no login. On an address other than 127.0.0.1 "
    "everyone who can reach it can use your model servers."
)


def _model_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--base-url", help="URL of the OpenAI-compatible server, e.g. http://localhost:11434/v1")
    p.add_argument("--model", help="Name of the chat model that writes the narration")
    p.add_argument("--api-key", help="API key, if the server requires one")
    p.add_argument("--tts-base-url", help="Server of the text-to-speech model (default: --base-url)")
    p.add_argument("--tts-model", help="Name of the text-to-speech model")
    p.add_argument("--tts-api-key", help="API key of the speech server (default: --api-key)")
    p.add_argument("--stt-base-url", help="Server of the speech recognition model (default: --base-url)")
    p.add_argument("--stt-model", help="Name of the speech recognition model, needed for subtitles")
    p.add_argument("--stt-api-key", help="API key of the recognition server (default: --api-key)")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pptx-screencast",
        description=(
            "Turn a PowerPoint deck into a narrated screencast with any "
            "OpenAI-compatible model server."
        ),
        epilog=(
            "Example: pptx-screencast deck.pptx -o deck.mp4 --voice alloy. "
            "Run 'pptx-screencast serve' for the web page."
        ),
    )
    p.add_argument("file", nargs="?", help="The presentation to narrate (.pptx)")
    p.add_argument("-o", "--output", help="Output file. Default: <name>.mp4 next to the deck")
    p.add_argument(
        "--script-only",
        action="store_true",
        help="Only write the narration as a Markdown file, make no video",
    )
    p.add_argument(
        "--from-script",
        metavar="FILE",
        help="Take the narration from this Markdown file instead of writing it",
    )
    p.add_argument(
        "--notes",
        action="store_true",
        help="Take the narration from the speaker notes of the deck",
    )
    p.add_argument(
        "--translate",
        metavar="LANGUAGE",
        help="Translate the narration into this language before it is spoken, e.g. en",
    )
    p.add_argument("--slides", help="Only these slides, e.g. 1-5,8")
    p.add_argument("--voice", help="Voice of the speech model, e.g. alloy (required for a video)")
    p.add_argument("--speed", type=float, help="Speaking speed, e.g. 0.9 or 1.2 (default 1.0)")
    p.add_argument("--language", help="Language the narration is written in (default en)")
    p.add_argument("--subtitles", action="store_true", help="Add a subtitle track, needs --stt-model")
    p.add_argument("--burn-in", action="store_true", help="Draw the subtitles into the picture as well")
    p.add_argument("--resolution", type=int, help="Slide images in dots per inch (default 100)")
    p.add_argument("--fps", type=int, help="Frames per second of the still image (default 5)")
    p.add_argument("--slide-pause", type=float, help="Seconds of silence after every slide (default 1.0)")
    p.add_argument("--crf", type=int, help="Video quality, lower is better and bigger (default 23)")
    p.add_argument("--min-chars", type=int, help="Characters a rich slide may approach (default 1500)")
    p.add_argument("--max-chars", type=int, help="Characters one narration may never exceed (default 2000)")
    p.add_argument("--max-slides", type=int, help="Most slides a deck may have (default 500)")
    p.add_argument("--max-workers", type=int, help="Slides spoken or cut at the same time (default 4)")
    p.add_argument("--work-dir", help="Keep the slide images, audio and clips in this folder")
    p.add_argument("-q", "--quiet", action="store_true", help="No progress output")
    _model_arguments(p)
    p.add_argument("--version", action="version", version=f"pptx-screencast {__version__}")
    return p


def _serve_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pptx-screencast serve", description="Start the local web page.")
    p.add_argument("--host", default="127.0.0.1", help="Default: 127.0.0.1 (this computer only)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--voice", help="Voice the page starts with")
    p.add_argument("--speed", type=float, help="Speaking speed the page starts with")
    p.add_argument("--language", help="Language the page starts with")
    _model_arguments(p)
    return p


def _serve(argv: List[str]) -> int:
    args = _serve_parser().parse_args(argv)
    try:
        import uvicorn

        from .web.app import create_app
    except ImportError:
        print(UI_HINT, file=sys.stderr)
        return 2
    app = create_app(
        _model_options(args),
        # On loopback only our own host names are accepted, so another web
        # page cannot reach the server through DNS rebinding.
        allowed_hosts=list(LOOPBACK) if args.host in LOOPBACK else None,
    )
    if args.host not in LOOPBACK:
        print(NO_LOGIN, file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _model_options(args) -> dict:
    return {
        "base_url": args.base_url,
        "model": args.model,
        "api_key": args.api_key,
        "tts_base_url": args.tts_base_url,
        "tts_model": args.tts_model,
        "tts_api_key": args.tts_api_key,
        "stt_base_url": args.stt_base_url,
        "stt_model": args.stt_model,
        "stt_api_key": args.stt_api_key,
        "voice": args.voice,
        "speed": args.speed,
        "language": args.language,
    }


def _options(args) -> dict:
    options = _model_options(args)
    options.update(
        subtitles=True if args.subtitles else None,
        burn_in=True if args.burn_in else None,
        resolution=args.resolution,
        fps=args.fps,
        slide_pause=args.slide_pause,
        crf=args.crf,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        max_slides=args.max_slides,
        max_workers=args.max_workers,
        work_dir=args.work_dir,
    )
    return options


def _progress(quiet: bool):
    if quiet:
        return None
    last = {"step": "", "done": -1}

    def report(step: str, done: int, total: int) -> None:
        if (step, done) == (last["step"], last["done"]):
            return
        last["step"], last["done"] = step, done
        print(f"{step}: {done}/{total}", file=sys.stderr)

    return report


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "serve":
        return _serve(argv[1:])
    args = _parser().parse_args(argv)

    if not args.file:
        print("Please provide a presentation.", file=sys.stderr)
        return 2
    deck = Path(args.file)
    if not deck.exists():
        print(f"{deck} does not exist.", file=sys.stderr)
        return 2
    if args.from_script and args.notes:
        print("Please choose either --from-script or --notes, not both.", file=sys.stderr)
        return 2
    if args.script_only and args.from_script:
        print("--script-only writes a script, --from-script reads one.", file=sys.stderr)
        return 2
    if args.burn_in and not args.subtitles:
        print("--burn-in needs --subtitles as well.", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
    )

    try:
        slides = parse_slides(args.slides) if args.slides else None
        if args.script_only:
            written = write_script(
                deck,
                args.output,
                notes=args.notes,
                translate=args.translate or "",
                progress=_progress(args.quiet),
                **_model_options(args),
            )
        else:
            written = make_video(
                deck,
                args.output,
                script=args.from_script,
                notes=args.notes,
                translate=args.translate or "",
                slides=slides,
                progress=_progress(args.quiet),
                **_options(args),
            )
    except ScreencastError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130

    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
