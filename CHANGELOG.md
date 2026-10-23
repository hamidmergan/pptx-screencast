# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-23

### Added

- `make_video` turns a PPTX into a narrated MP4: slides rendered with LibreOffice, one narration per slide, speech from any OpenAI-compatible text-to-speech model, assembly with ffmpeg.
- `write_script` writes the narration as a Markdown file with one heading per slide, so it can be read and corrected before anything is spoken.
- Three sources for the narration: the chat model, the speaker notes of the deck, or a script file.
- Translation of a finished narration through the chat model.
- Subtitles recognised from the spoken audio, written as VTT and SRT and added to the MP4 as its own track, optionally burned into the picture.
- A notice slide at the start and the end of the video, and the same sentence in the metadata of the file.
- Slide selection with `--slides 1-5,8`, speaking speed, pause between slides, resolution and video quality as settings.
- Command line `pptx-screencast` with `--script-only`, `--from-script`, `--notes`, `--translate`, `--subtitles`, `--burn-in` and `--slides`.
- Web page under `pptx-screencast serve`, plus a Dockerfile and a compose file that bring LibreOffice, poppler and ffmpeg with them.
- Separate `base_url`, `model` and `api_key` for chat, speech and speech recognition, each falling back to the chat values.
- A glossary that pins how a term has to come out, as `--glossary FILE` or as a `dict`, applied to the narration and to the translation.
- Extra text per slide as `materials`, which the model may use to make a narration concrete.
- A warning naming the slides a translation handed back unchanged.
- `--stt-timeout` bounds the whole subtitle step, and the step reports every recognised clip.

### Fixed

- A relative `--work-dir` broke every clip and the join, because ffmpeg reads a concat entry relative to the list file. The work directory is resolved and the lists hold absolute paths.
- A reused `--work-dir` could build the video from the slide images of an earlier run.
- The retry ladder for the voice sits on the spoken part instead of the whole slide, and a part that gives up for good stops the rest of the run.
- The `fps` setting now decides the frame rate of the clips. Nothing read it before.
- The clips are cut side by side, as `--max-workers` promises.
- The speech step counts only the slides it speaks, so the progress no longer jumps backwards.
- An unticked box on the page switches subtitles or burn in off, even when the environment switches them on, and `/api/info` reports the pause, the resolution and both boxes from the environment.
- A deck that cannot be read is reported as an error instead of a traceback.
- A stuck or missing LibreOffice, poppler or ffmpeg is reported as an error of this package.
- A retry of the recogniser is decided from the status code alone, never from the message text.
- The corrected copy of the deck is written into the work folder, so a deck on a read-only share renders as well.
- A path with a quote, a colon or an equal sign in it is escaped for both levels ffmpeg reads a filter at.
- A quote in a folder name no longer breaks the ffmpeg concat list.
- Burned-in cues are no longer also added as a separate subtitle track.

[0.1.0]: https://github.com/hamidmergan/pptx-screencast/releases/tag/v0.1.0
