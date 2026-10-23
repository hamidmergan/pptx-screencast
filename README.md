# pptx-screencast

Turn a PowerPoint deck into a narrated screencast MP4. The slides are rendered with LibreOffice, every slide gets one narration, a text-to-speech model speaks it, and ffmpeg assembles the clips into one video.

The narration can come from three places:

- the chat model, which writes it from the text of each slide
- the speaker notes of the deck
- a Markdown script file you wrote or corrected by hand

Subtitles are optional. They are recognised from the spoken audio with a speech recognition model, so the cue times match what is really heard, and they are written as VTT and SRT next to the video.

## Prerequisites

- Python 3.10 or newer
- LibreOffice with `pdftoppm` and `pdfinfo` (poppler), to render the slides
- ffmpeg and ffprobe, to build the video
- A server with an OpenAI-compatible API and a **chat model** for the narration, plus a **text-to-speech model** with at least one voice for the audio. A **speech recognition model** is only needed for subtitles. All three can live on the same server or on three different ones.
- An API key is optional. Many self-hosted servers do not need one.

No vision model is needed. The model reads the text of the slides, not their picture.

If you run your own models, your decks stay on your own network. Nothing leaves your machine or data center.

## Installation

```bash
pip install pptx-screencast
```

Alternatively, you can install it from the source:

```bash
git clone https://github.com/hamidmergan/pptx-screencast.git
cd pptx-screencast
pip install .
```

The web page needs a few extra packages:

```bash
pip install "pptx-screencast[ui]"
```

## Usage

### Command-Line

Build the video, with the narration written by the chat model:

```bash
pptx-screencast deck.pptx -o deck.mp4 --voice alloy \
  --base-url http://localhost:11434/v1 --model your-chat-model --tts-model your-tts-model
```

Without `-o` the video is written as `deck.mp4` next to the deck. If that name is taken, a number is added (`deck (1).mp4`).

Write the narration first, read it, correct it, then build the video from it:

```bash
pptx-screencast deck.pptx --script-only -o deck.md \
  --base-url http://localhost:11434/v1 --model your-chat-model
pptx-screencast deck.pptx --from-script deck.md --voice alloy \
  --base-url http://localhost:11434/v1 --model your-chat-model --tts-model your-tts-model
```

A script file is plain Markdown with one heading per slide. A slide that stays silent keeps its heading and has no text under it:

```markdown
# deck

## Slide 1

Welcome to this short tour.

## Slide 2

The first point is the simplest one.
```

Take the speaker notes instead, which costs no chat request at all:

```bash
pptx-screencast deck.pptx --notes --voice alloy ...
```

Translate the narration before it is spoken:

```bash
pptx-screencast deck.pptx --notes --translate German --voice alloy ...
```

Pin how a term has to come out, for the narration and for a translation:

```bash
pptx-screencast deck.pptx --glossary terms.txt --voice alloy ...
```

A glossary is one `term = replacement` per line, or a JSON object. Lines starting with `#` are comments:

```
Rechenzentrum = data centre
Folie = slide
```

Only a few slides, counted from one:

```bash
pptx-screencast deck.pptx --slides 1-5,8 --voice alloy ...
```

Subtitles as their own track in the MP4, plus `deck.vtt` and `deck.srt` next to it:

```bash
pptx-screencast deck.pptx --subtitles --stt-model your-stt-model --voice alloy ...
```

Add `--burn-in` to draw the cues into the picture as well. That re-encodes the video and needs an ffmpeg built with libass. When the cues are drawn in, the MP4 gets no separate subtitle track, so a player cannot show them twice. The `.vtt` and `.srt` files are written either way.

Progress goes to stderr, the path of the finished file to stdout. `-q` keeps the progress out. The exit code is 1 when the run failed and 2 when the arguments do not fit together.

### Python API

```python
from pptx_screencast import make_video

path = make_video(
    "deck.pptx",
    "deck.mp4",
    voice="alloy",
    base_url="http://localhost:11434/v1",
    model="your-chat-model",
    tts_model="your-tts-model",
)
print(path)
```

Only the narration, as a Markdown file:

```python
from pptx_screencast import write_script

path = write_script(
    "deck.pptx",
    "deck.md",
    base_url="http://localhost:11434/v1",
    model="your-chat-model",
)
```

Extra text per slide, so the narration can be concrete about what is only hinted at on the slide:

```python
from pptx_screencast import write_script

path = write_script(
    "deck.pptx",
    "deck.md",
    materials=["The definition and the example behind slide one.", ""],
    base_url="http://localhost:11434/v1",
    model="your-chat-model",
)
```

One entry per slide, empty where a slide has none. The text has to be plain text, this package reads PPTX files and nothing else. It is trimmed per slide and cleaned of the characters the batch format uses, so it can never shift the narration to another slide.

`make_video` takes the same keywords as the command line, written with underscores (`from_script` is `script`, `--burn-in` is `burn_in`). `slides` counts from zero there, because it is a list of indexes. A `progress` callback is called with the name of the step, the finished units and the total.

### Web UI

```bash
pptx-screencast serve
```

This opens a page on <http://127.0.0.1:8000> with the same fields as the command line: the deck, where the narration comes from, the voice, the language, subtitles and the slide range. The result is shown on the page and can be downloaded. Settings come from the environment or from the fields on the page.

The page has no login. On an address other than 127.0.0.1 everyone who can reach it can use your model servers.

### Docker

The image brings LibreOffice, poppler and ffmpeg with it, so nothing has to be installed on the host:

```bash
docker compose up
```

The page is then on <http://127.0.0.1:8000>. Put your server and model names into the environment variables in `docker-compose.yml` or into a `.env` file next to it.

### Settings

Order: argument, then environment variable, then default.

| Argument / flag | Environment variable | Default |
| --- | --- | --- |
| `base_url` / `--base-url` | `PPTX_SCREENCAST_BASE_URL` | none, required |
| `model` / `--model` | `PPTX_SCREENCAST_MODEL` | none, required |
| `api_key` / `--api-key` | `PPTX_SCREENCAST_API_KEY` (then `OPENAI_API_KEY`) | optional |
| `tts_base_url` / `--tts-base-url` | `PPTX_SCREENCAST_TTS_BASE_URL` | `base_url` |
| `tts_model` / `--tts-model` | `PPTX_SCREENCAST_TTS_MODEL` | none, required for a video |
| `tts_api_key` / `--tts-api-key` | `PPTX_SCREENCAST_TTS_API_KEY` | `api_key` |
| `stt_base_url` / `--stt-base-url` | `PPTX_SCREENCAST_STT_BASE_URL` | `base_url` |
| `stt_model` / `--stt-model` | `PPTX_SCREENCAST_STT_MODEL` | none, required for subtitles |
| `stt_api_key` / `--stt-api-key` | `PPTX_SCREENCAST_STT_API_KEY` | `api_key` |
| `stt_timeout` / `--stt-timeout` | `PPTX_SCREENCAST_STT_TIMEOUT` | 900 seconds for the whole subtitle step |
| `voice` / `--voice` | `PPTX_SCREENCAST_VOICE` | none, required for a video |
| `speed` / `--speed` | `PPTX_SCREENCAST_SPEED` | 1.0 |
| `language` / `--language` | `PPTX_SCREENCAST_LANGUAGE` | en |
| `subtitles` / `--subtitles` | `PPTX_SCREENCAST_SUBTITLES` | off |
| `burn_in` / `--burn-in` | `PPTX_SCREENCAST_BURN_IN` | off |
| `resolution` / `--resolution` | `PPTX_SCREENCAST_RESOLUTION` | 100 dpi |
| `fps` / `--fps` | `PPTX_SCREENCAST_FPS` | 5 |
| `slide_pause` / `--slide-pause` | `PPTX_SCREENCAST_SLIDE_PAUSE` | 1.0 seconds |
| `crf` / `--crf` | `PPTX_SCREENCAST_CRF` | 23 |
| `min_chars` / `--min-chars` | `PPTX_SCREENCAST_MIN_CHARS` | 1500 |
| `max_chars` / `--max-chars` | `PPTX_SCREENCAST_MAX_CHARS` | 2000 |
| `batch_size` | `PPTX_SCREENCAST_BATCH_SIZE` | 10 slides per chat request |
| `batch_max_workers` | `PPTX_SCREENCAST_BATCH_MAX_WORKERS` | 3 |
| `batch_timeout` | `PPTX_SCREENCAST_BATCH_TIMEOUT` | 600 seconds |
| `max_slides` / `--max-slides` | `PPTX_SCREENCAST_MAX_SLIDES` | 500 |
| `max_workers` / `--max-workers` | `PPTX_SCREENCAST_MAX_WORKERS` | 4 |
| `work_dir` / `--work-dir` | `PPTX_SCREENCAST_WORK_DIR` | a temporary folder |

`glossary` / `--glossary` is not a setting but an input, so it has no environment variable. On the command line it is a file, in the Python API a `dict` of term to replacement.

The speech and recognition routes fall back to the chat values, so one server can serve all three and a second one only needs the values it differs in.

`min_chars` and `max_chars` are a ceiling, not a target. A slide with one line of content gets two or three sentences, not a padded paragraph.

A missing program or setting is reported before the first long step, naming what to install or set.

## Limitations

Quality depends on the chosen models. A small chat model may misread dense tables and diagrams, and a small voice may stumble over names and numbers. Check important results.

LibreOffice renders a deck a little differently than PowerPoint authored it. Fonts that are not installed are substituted, and animations, transitions and embedded video are not part of the picture. Hidden slides are left out.

Subtitle times come from a speech recognition model and are as good as that model. Without one, the video is built without subtitles. The whole subtitle step is bounded by `stt_timeout`. When a recognition server keeps asking for patience and the time runs out, the remaining clips get no cues and the run goes on.

`--burn-in` needs an ffmpeg built with libass. Without it the cues stay in their own track, which every common player can switch on, and a warning says so. The ffmpeg in the Docker image has libass, a Homebrew ffmpeg on macOS usually does not.

## Running Tests

```bash
pip install -e ".[test]"
pytest
```

The tests run against a local fake server and need no real model. Tests that need LibreOffice or ffmpeg skip when the program is not installed.

## License

MIT
