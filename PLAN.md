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

Copying the source protects behaviour worth keeping, not defects. Everything
below is a behaviour change that was made on purpose, with the reason.

### Scripts and the chat model

- **The retry flag of a gap no longer gets overwritten.** When a batch comes
  back with a slide that has text but no script, that slide is generated on its
  own. The flag that says whether a gap may still be retried shared its name
  with the result of that single call, so a retry that came back empty turned
  the flag falsy and every later gap of the same batch was silenced without
  being asked. The result now has its own name. Covered by
  `test_a_failed_retry_does_not_silence_the_slides_after_it`, which fails
  against the old code.
- **Translation through the chat model instead of a dedicated service.** The
  dedicated service is on the not-carried list. The finished narration is
  translated with the chat model, one request per slide, temperature 0, a
  failed slide keeps its original.
- **A glossary is an input, not a stored setting.** The source read the term
  mapping out of its database. Here it is a `dict` in the Python API and a
  file for `--glossary`. It is applied to the narration the model writes and,
  unlike the source's screencast route, also by value to every translation
  request.
- **A translation says which slides it left alone.** `review.find_unchanged_slides`
  is carried, and `translate_scripts` logs a warning naming those slides. The
  source used the same check on its PPTX-level translation.
- **Material is supplied by the caller as plain text.** The source turned PDF
  and Word files into text with a document converter that is on the
  not-carried list, and it sized the material to the model's window by asking
  a provider profile for `window_tokens`. There is no provider table here, so
  `material.MATERIAL_CHARS` is a plain character ceiling per slide instead.
  The source's guard against a forged batch separator inside material is
  carried as `material.clean_material`.
- **The slide ceiling is 500, not 50.** The source had a per-user quota behind
  it, this is a local tool with none. 500 is a guard against a deck nobody
  meant to narrate, and the README says so. It has not been run at that size.

### Speech

- **The retry ladder sits on the spoken part, not on the slide.** A narration
  may be up to `max_chars` characters, and doc2speech sends one request per
  400 characters, so one slide is several requests. Retrying the slide threw
  away the parts that had already been paid for. The real numbers, measured
  against the test server with a 1980 character narration, which is 6 parts:

  | Case | Requests |
  | --- | --- |
  | Server answers | 6 |
  | One part needs one more try | 7 |
  | Server is down, one worker | 4 |
  | Server is down, four workers | 4 to 16 |
  | Server is down, 40 slides, four workers | 4 to 16 |

  Four attempts per part, waiting 2, 5 and 10 seconds. `TTS_MAX_RETRIES` is 0,
  so one attempt is one request.
- **A part that has given up for good stops the rest of the run.** Without it
  a deck of 40 slides against a server that is down cost 960 requests. Now the
  first part to exhaust its ladder sets a flag, and no other part starts or
  retries after that. Covered by
  `test_a_whole_deck_against_a_dead_server_costs_one_ladder`.
- **One pool over the parts of all slides.** The source bounded the total
  number of open speech requests. An earlier version here ran 4 slides at a
  time and let doc2speech run 4 parts inside each, so up to 16 requests could
  be open. Now `max_workers` is the real number.
- **A busy speech server is recognised by the verdict on the error.** The
  source matched the literal `(503)` its own client produced. doc2speech words
  the same failure differently, so no retry here ever fired. doc2speech now
  reports the verdict itself, so `is_transient` reads `exc.transient` and no
  message text at all. No answer, 408, 429 and every 5xx are worth another
  try, every other answer is final, and so is anything that is not the
  server's fault, such as a missing setting or an empty text.
- **The slides are released in order.** `speak_all` waits for slide one before
  it reports slide two, even when slide two finished first, so a progress
  display fills front to back. The source's `_melde` did the same.
- **The progress of the speech step counts only the slides it speaks.** With
  `--slides 1,3` the step used to open at 0 of 2 and then count to 4 of 4.
- **The speed is applied locally.** `_tempo_anpassen` existed in the source but
  no caller ever passed a speed to it, so the user's choice was collected,
  written into the statistics and discarded. Here the speed reaches
  `create_slide_video` and `atempo` applies it, which keeps the pitch of the
  voice.

### Rendering and the video

- **The work directory is always absolute.** ffmpeg resolves an entry of a
  concat list against the directory of the list file, so a relative
  intermediate path was looked for one folder too deep. Both concat lists now
  hold absolute paths as well.
- **A concat entry is quoted for any path.** The source wrote `file '<path>'`,
  so a quote in a folder name ended the entry in the middle of the path. The
  quote is now closed, escaped and reopened the way a shell does it. Found by
  a real run in the image with a work folder called `o'brien, c:x work`.
- **A run never picks up a file of an earlier run.** The source collected the
  slide images with `sorted(glob("slide-*.png"))`, and `pdftoppm` pads the page
  number to the digit width of the document, so a 12 slide run left
  `slide-01 .. slide-12` and a later 3 slide run left `slide-1 .. slide-3` in
  the same folder, sorted in front of the new ones. Every page now renders
  under a prefix of its own and the list comes back in page order, the images
  folder is emptied before a run, and the audio folder with it.
- **The corrected copy of the deck goes into the work folder.** The source
  always worked on a temp copy under the job folder, so writing the copy next
  to the input was harmless there. Here the input is the user's own file,
  which may sit on a read-only share.
- **The clips are cut side by side.** The source rendered them in a thread
  pool, an earlier version here did it one at a time while the CLI help said
  `--max-workers  Slides spoken or cut at the same time`.
- **The frame rate is the `fps` setting.** It had a constant, a field, an
  environment variable, a validator entry, a CLI flag and a README row, and
  nothing read it.
- **Burned-in cues are not in the file twice.** When the cues are drawn into
  the picture the MP4 gets no `mov_text` track, so a player that switches
  subtitles on cannot show them twice. A burn-in that failed keeps the track,
  because then the picture has no cues at all.
- **A filter path is escaped for both levels.** ffmpeg takes a filter
  description apart twice, once in the graph parser and once in the filter's
  option parser, so a colon needs two backslashes and a quote three. Measured
  against real ffmpeg with paths holding a quote, a colon, an equal sign, a
  comma, a semicolon, brackets and a backslash.
- **The notice slide is drawn with Pillow.** The source loaded a PNG asset and
  raised `FileNotFoundError` when it was missing.
- **No re-voice-single-slide flow.** `speak_again` is accepted by
  `slide_selection` and always empty. The audio cache, the resume, the
  heartbeats, the watchdog and the statistics are storage features.
- **The subtitle step has a deadline.** In the source the recogniser ran inside
  a stage with a clock, a heartbeat and a watchdog, all of which are storage
  features. The ladder of `5, 15, 60, 180, 300, 420, 600` seconds is up to 1580
  seconds per file, so 40 clips could hold a run for hours with nothing to
  interrupt it. `stt_timeout` bounds the whole step, a wait that would run past
  it is not taken, and the step reports every recognised clip.
- **Every retry policy is this package's own.** The openai client is built with
  `max_retries=0`, so one attempt is one request for the chat model and for
  the recogniser as well, and the waits are the ones in `BACKOFFS`.

### Errors

- **A deck that cannot be read is a `SlideError`.** `python-pptx` raises a
  zipfile or a package error for a renamed `.ppt`, a truncated download or an
  export from another program, and the CLI printed the traceback.
- **A stuck or missing program stays inside the error contract.** Every
  `subprocess.run` carries a timeout, and `TimeoutExpired` is not a
  `ScreencastError`. The rendering calls now leave as `SlideError` and the
  ffmpeg calls as `VideoError`, the two steps that can degrade gracefully, the
  burn-in and the faststart pass, keep doing that. `prs.save` and the write of
  the finished video are covered the same way. The recogniser raises
  `ModelError` instead of `RuntimeError`.
- **LibreOffice gets 600 seconds, not 120.** A deck of a hundred slides with
  large pictures takes minutes.
- **A retry of the recogniser is decided from the status alone.** The source
  also searched the message text, and its list held the bare substrings
  `connection` and `timeout`, so a 400 whose message mentions either would
  have started a ladder of waits that cannot help. The status is read off the
  error, off its response and along its cause chain, never parsed out of
  prose. A refused connection or a timeout carries no status and counts as
  transient.
- **The return code of every ffmpeg call is checked.** The source ignored the
  two calls that build the pause, so a failure there only surfaced later as a
  missing input file.
- **The cancel watcher is not carried.** `process.kill_run_procs` and the
  process registry only made sense with a job that could be cancelled from
  outside. `run_proc` still starts every call in its own session and kills the
  whole group on a timeout, which is what the timeout needs.
- **The text-based busy check is not carried.** `upstream.is_upstream_busy` and
  `upstream_error_code` returned a key for a frontend that is not here, and
  they decided from the message text. `upstream.is_provider_refusal`, which
  reads the status first, is carried and used by the batch generation.

## Known properties

Faithful to the source, no user visible harm, worth knowing.

- **The cue offsets are summed clip lengths.** The offsets come from the
  `format=duration` of each clip, not from the joined timeline, and the two
  differ by about 8 milliseconds per clip. Six clips drift under a tenth of a
  second, which `test_the_summed_clips_stay_close_to_the_joined_timeline`
  pins. A deck of 60 slides drifts about half a second by the end, well below
  what a viewer notices.
- **`DOC2SPEECH_SPEED` is the one value that can still reach the speech
  server.** Everything doc2speech works with is passed in explicitly, but
  "send no speed at all" cannot be expressed through its public call, because
  passing `None` means "take the environment". A set variable is pointed out
  with a warning naming `--speed` instead.
- **Carried helpers without a call site in the pipeline.** `selection.audio_slots`,
  `selection.slides_to_speak` and `Selection.old_audio_allowed` belong to the
  re-voice flow that is not carried, `naming.build_artifact_stem`,
  `script_file.numbered_headings` and `subtitles.build_subtitle_srt` are part of
  the library surface and are exported and tested.
- **The subtitles stay next to the video even when they are burned in.** The
  `.vtt` and `.srt` files are written in both cases, because they are useful
  on their own.
- **A silent slide stays on screen for three seconds.** `SILENT_DURATION` is
  the source's value and is not a setting.
- **The notice slide frames the video at both ends and is stamped into the
  file metadata as a comment.**

## Open

- `doc2speech` is declared as a normal version dependency. Until it is on a
  package index, neither the CI workflow nor the Docker build can resolve it
  from there. Both now install it as a step of their own, controlled by
  `DOC2SPEECH_SOURCE`: a repository variable in the workflow and a build
  argument in the Dockerfile and the compose file. Set it to a pip
  requirement, for example a git URL or the path of a wheel inside the build
  context. The default is the plain name `doc2speech`, which works as soon as
  a version is published.
- Burn in needs an ffmpeg built with libass. The image has one, a Homebrew
  ffmpeg on macOS usually does not, and then the cues stay in their own track.
  The README says so.
- `max_slides` defaults to 500 and has not been run at that size.
- Material has no place on the web page. The source read it from storage, and
  a page would need an upload per slide.
