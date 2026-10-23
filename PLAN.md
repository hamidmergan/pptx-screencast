# pptx-screencast

Turns a PPTX deck into a narrated screencast MP4.

The slides are rendered to images with LibreOffice, every slide gets one
narration (from its speaker notes, from its text through a chat model, or from
a script file), the narration is spoken with a text-to-speech model, subtitles
are written as VTT and SRT and optionally burned into the picture, and ffmpeg
assembles the clips into one MP4. The script can be translated into another
language before it is spoken.

## Shape

- Library with a thin CLI on top, plus a web page (`pptx-screencast serve`).
- Python package `pptx_screencast`, pip package `pptx-screencast`.
- Speech comes from `doc2speech`, which talks to any OpenAI-compatible
  `/audio/speech` endpoint.

## Decisions

- Providers: OpenAI-compatible interface only. Chat, speech and speech
  recognition each have their own `base_url`, `model` and `api_key`, falling
  back to the chat values. No default for `base_url` and `model`.
- System tools: ffmpeg and ffprobe are required for the video, LibreOffice
  (with `pdftoppm` and `pdfinfo`) is required to render the slides. Both are
  checked before the work starts and reported with a clear message.
- Subtitles are recognised from the spoken audio with a speech-to-text model,
  so the cue times match what is really heard. Without a configured
  recognition model the video is built without subtitles.
- The AI notice is drawn as a plain slide at the start and the end of the
  video and is also written into the file metadata.
- No jobs, no database, no queue. One call does one deck.

## Checklist

- [x] 0 Scaffold: repo, LICENSE (MIT), pyproject, `src/pptx_screencast/`, `tests/`, CI, PLAN.md, README skeleton. ffmpeg and LibreOffice as system requirements, checked at start.
- [x] 1 Material: slide text and notes, rendering slides to PNG, slide selection, naming, paths, `config.py`, `errors.py`.
- [x] 2 Script: narration per slide through the model (the count must match), script file (Markdown, one heading per slide), notes as script, translation.
- [x] 3 Audio, subtitles, video: speech per slide, slide duration from the audio, subtitles (VTT, SRT, timing), ffmpeg concat and burn in, outro.
- [x] 4 API and CLI: `make_video`, `write_script`, CLI with `--voice`, `--script-only`, `--from-script`, `--notes`, `--translate`, `--subtitles`, `--burn-in`, `--slides`.
- [x] 5 Tests with a fake server for chat, speech and recognition.
- [x] 6 README, CHANGELOG 0.1.0, local smoke test with a real model.
- [x] 7 English sweep, acceptance checks, final commit.
- [x] 8 Web UI and Docker.

## Deliberate deviations from the source

Copying the source protects behaviour worth keeping, not defects. Three places
were changed on purpose.

- **The retry flag of a gap no longer gets overwritten.** When a batch comes
  back with a slide that has text but no script, that slide is generated on its
  own. The flag that says whether a gap may still be retried shared its name
  with the result of that single call, so a retry that came back empty turned
  the flag falsy and every later gap of the same batch was silenced without
  being asked. The result now has its own name. Covered by
  `test_a_failed_retry_does_not_silence_the_slides_after_it`, which fails
  against the old code.
- **The speech is asked at most four times per slide.** doc2speech makes
  attempts of its own inside every attempt made here, so a server that is down
  for good was asked nine times for one slide, without the growing waits in
  between. `TTS_MAX_RETRIES` is 0, so one attempt here is one request, and the
  policy of a slide lives in `RETRY_DELAYS` alone: four attempts, waiting 2, 5
  and 10 seconds. Covered by
  `test_a_dead_server_is_asked_exactly_once_per_attempt`.
- **A busy speech server is recognised by its status, not by one spelling.**
  The source matched the literal `(503)` its own client produced. doc2speech
  writes `Error code: 503`, so no retry here ever fired and only the attempts
  inside doc2speech were doing the work. Both spellings are matched now, and a
  status that will not change, such as 401, is still not transient.

## Open

- `doc2speech` is declared as a normal version dependency. Until it is on a
  package index, the Docker image cannot resolve it from there. The image was
  built and tested against a locally built wheel of it.
- Burn in needs an ffmpeg built with libass. The image has one, a Homebrew
  ffmpeg on macOS usually does not, and then the cues stay in their own track.
