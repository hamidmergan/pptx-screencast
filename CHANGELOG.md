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
- Subtitles recognized from the spoken audio, written as VTT and SRT and added to the MP4 as its own track, optionally burned into the picture.
- A notice slide at the start and the end of the video, and the same sentence in the metadata of the file.
- Slide selection with `--slides 1-5,8`, speaking speed, pause between slides, resolution and video quality as settings.
- Command line `pptx-screencast` with `--script-only`, `--from-script`, `--notes`, `--translate`, `--subtitles`, `--burn-in` and `--slides`.
- Web page under `pptx-screencast serve`, plus a Dockerfile and a compose file that bring LibreOffice, poppler and ffmpeg with them.
- Separate `base_url`, `model` and `api_key` for chat, speech and speech recognition, each falling back to the chat values.

[0.1.0]: https://github.com/hamidmergan/pptx-screencast/releases/tag/v0.1.0
