# English pipeline migration log — 2026-11-04

- Hindi baseline: `43cdb83`; documented snapshot: `1ddcc6b`.
- Rollback tag: `hindi-before-english-2026-11-04`.
- [Full Hindi version log and README](docs/archive/hindi-before-english-2026-11-04-README.md).
- Earlier uncommitted documentary work: `archive/documentary-local-2026-11-04`,
  commit `1610b05`; preserved separately because it predates the Hindi pipeline.
- Replaced the tracked implementation with a direct clone of
  `Asif-Rezan/dudi_dam_tv` at `01c2249`. English lyrics, English audio, models,
  bundled reference assets, metadata, scheduling, Shorts, recovery and cleanup
  follow that exact reference. Reference schedule: 03:00 Asia/Dhaka.
- Destination repository, existing YouTube identity and private Grow with Rezan
  kids Drive folder remain unchanged. GitHub secrets/variables are not replaced.
  Only `storage.py` initialization, `setup_accounts.py`, `verify_connections.py`,
  destination `.env.example` and their integration tests differ for this purpose.
  Existing OAuth privacy/site documents are retained to keep their URLs available.
- Hindi-only ACE experiments, lyric verifier and Facebook workflows are archived
  in the rollback tag and are not active in the English reference implementation.
- Use a fresh run ID for English generation; saved Hindi runs are not translated.

Restore code by creating a restoration commit from the rollback tag; do not
rewrite history. Tags do not restore cloud settings, deleted media or credentials.

Validation before migration commit: `python -m unittest -v` passed all 159
tests, including actual FFmpeg render/audio checks and destination Drive guards.
CLI startup checks passed for generation, publication and Shorts. Reference
tracked-file comparison confirms only the documented integration changes.
Cloud inference/publication are separate from these component checks.

---

# Dudi Dam TV — kids rhyme video automation

Copied from [Heart-and-Mind](https://github.com/Asif-Rezan/Heart-and-Mind) at `0fca9240b5edf786f09a806401a62dcc386eb0f6`. The first repository commit is the unchanged copy. The kids adaptation retains pinned CPU music/image inference, resumable artifacts, Google account setup, verified YouTube publishing and exact-file Drive cleanup.

## Current behavior

- Default: 600 seconds. Set `VIDEO_DURATION_SECONDS` to 480–720 in five-second steps.
- Sweet adult female singing voice requested, original AI-written English verses alternating with **dudi dudi dam dam dudi dudi dam**. This phrase is a sung refrain, not musical chord notation.
- The first lyrics job runs the pinned local Qwen3-4B CPU model to write a fresh adventure outline, new English verses, and matching visual descriptions. Only the Dudi refrain is fixed. There is no template fallback. Each run ID uses a different generation seed.
- A new SSD-1B cartoon illustration for every five seconds (96–144 images), plus a thumbnail. Sixteen image workers split generation and checkpoint each completed image.
- ACE-Step generates separate sections up to 120 seconds, then FFmpeg joins them. Music is not looped or padded. Short or incorrectly sized sections fail. Section joins and voice/character consistency need listening/viewing review.
- A 30-second excerpt of the user-supplied MP3 is included at `assets/reference/style-reference.mp3`; the full original is not committed. The pinned API exposes `reference_audio`. Inference receives the excerpt for style conditioning; actual influence and singing quality require a model run. Set `REFERENCE_AUDIO_PATH` to a different local file or leave unset to generate without conditioning. Use reference material you have permission to use.
- Storyboard lyrics drive image actions and the pictures change exactly every five seconds. Singing is generative: this is planned timing, **not forced alignment or transcription**. Precise word-level synchronization is not yet implemented.

## Generate before connecting Google

Run **Dudi Dam TV kids rhyme generation** from GitHub Actions with a new `run_id`. The lyrics job checks and reserves lyric originality in private Drive history; connected Drive credentials are required for the production workflow. Local generation without history can run without Google credentials. Download `kids-video-RUN_NUMBER` for the MP4, thumbnail and song/storyboard JSON. Generation is computationally expensive and has not yet been verified end to end on Actions. Existing model revisions and CPU dependencies come from the reference; 120-second sections reload the model for bounded worker isolation. Model memory/time limits may require a larger runner.

Automatic scheduling is off unless repository variable `AUTOMATION_ENABLED=true`. Publishing requires `PUBLISH_ENABLED=true`. The scheduled time inherited from the reference is 03:00 Asia/Dhaka. The workflow defaults to 600 seconds; adjust `VIDEO_DURATION_SECONDS` in its workflow-level env for other durations.

For local AI lyric writing (downloads the pinned Qwen GGUF model):

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-lyrics.txt
python prepare_music.py --run-id first-rhyme --stage lyrics
```

Image preparation also requires CPU PyTorch and `requirements-images-cpu.txt`. Music preparation needs CPU torch/torchaudio, `requirements-music-cpu.txt` and ACE-Step source at revision `ca1e85fe9430179831e6bc6be790c332190a3866` in `.vendor/ace-step`. See the workflow for exact installation. Install FFmpeg for audio joining and video rendering.

## Connect later

1. Configure a Google Cloud OAuth client with YouTube Data API v3 and Google Drive API enabled.
2. Use `python setup_accounts.py --help` for the inherited account setup commands targeting `Asif-Rezan/dudi_dam_tv`. Drive remains restricted to the account in `storage.py`; update it deliberately if using another owner.
3. Add secrets `YOUTUBE_TOKEN_JSON`, `EXPECTED_CHANNEL_ID`, `DRIVE_TOKEN_JSON`, `DRIVE_FOLDER_ID`. Create a new Dudi Dam TV Drive folder with the `dudi_dam_tv_root=v1` application property via setup; do not reuse the reference channel folder.
4. After reviewing a downloaded preview, set `PUBLISH_ENABLED=true`. Uploads declare `selfDeclaredMadeForKids=true`; the configured channel ID must match. Drive stores the scene sources/manifests as `storyboard.tar.gz`, and cleanup removes media only after verified public HD publication.

Google OAuth and the dedicated Drive folder can be checked with the **Verify Google connections** workflow. This only verifies identity, folder privacy and refresh tokens; it does not upload videos. No finished music/video is claimed until inference succeeds and the result is reviewed.

## Verification

`python -m unittest -v` covers duration boundaries, complete contiguous storyboards, cache/shard coverage, missing scene failures, rendering arguments and inherited guarded Drive cleanup. Original reference tests remain in `reference_tests/` as historical specifications; their adult-music assumptions do not describe this adaptation.

## Upload details and scheduling

The workflow dispatch form exposes `upload_mode` (`public` or `scheduled`), `publish_at`, `video_language`, `audio_language`, and `category_id`. Scheduled times must include a timezone (for example `2026-11-01T18:00:00+06:00`) and still be in the future when the upload starts. Allow enough time for generation. With an explicit timestamp, a scheduled upload is private with `publishAt` set; it is verified as scheduled after HD processing. Reusing its run ID checks the same upload rather than creating another one.

`upload_settings.json` stores explicit defaults for English metadata/audio, Music category (10), made for kids, AI disclosure, standard YouTube license, embedding, public statistics, subscriber notifications, and no paid placement. The kids and AI disclosures are enforced for this pipeline. Title, description, tags and thumbnail come from the generated song artifact. Review/edit that artifact before publishing if needed. Comments, cards/end screens and some other Studio-only features are subject to made-for-kids restrictions and are not exposed by this uploader.

Scheduled media is retained on Drive. After its release, rerun the same publishing identity to verify public HD status before cleanup. OAuth Production status removes testing-mode token expiry; it does not guarantee that Google will never revoke a refresh token. Actual upload acceptance/public visibility is always checked rather than assumed from OAuth status.


## Daily 6 AM New York releases

Daily generation starts at 21:00 UTC (03:00 Asia/Dhaka). Once each video finishes uploading, it is scheduled for the first **06:00 America/New_York** slot at least **72 elapsed hours after upload completion**. New York daylight saving changes are handled by the IANA timezone database. The actual wait is 72 hours up to the next qualifying 6 AM slot (normally less than 96 hours). There is an initial three-plus-day buffer before the first release; generation failures/delays can leave gaps.

The default upload is private without a publication timestamp. After YouTube returns its video ID, the pipeline records upload completion, computes and saves the target, then updates YouTube `status.publishAt`. Retry attempts reuse the saved target rather than delaying it again. This step needs `youtube.force-ssl` authorization in addition to the existing upload/read scopes. Default workflow mode is `scheduled` and `publish_at` is empty, so both daily and manual runs follow this policy unless explicitly overridden. `AUTOMATION_ENABLED=true` enables daily generation and `PUBLISH_ENABLED=true` enables uploading.


## Animated picture treatment

Every five-second lyric scene now has continuous 25 fps camera motion: gentle alternating horizontal pan, a slow push-in, a small rhythmic pulse and vertical sway. Translucent bubbles drift independently along the edges for foreground depth. A 0.28-second dissolve uses the previous scene's actual final frame, so scene changes do not add time or shift the soundtrack. The original song is muxed once after the silent clips are joined.

This gives still illustrations a lively storybook presentation; it does not rig character limbs or lip-sync mouths. New episodes request 120 BPM; animation follows that requested tempo, not measured audio beats. Full videos remain 1920×1080 and 8–12 minutes, with a new illustration every five seconds. Rendering is split into small clips to bound memory. `render-state.json` fingerprints the renderer version and inputs so an old static video is regenerated automatically.

For a local short preview without model inference or publishing, run `python preview_motion.py image1.png image2.png --audio song.wav --output output/motion-preview.mp4`. Preview images/audio are supplied locally and are never used as a production fallback.


## Fresh AI lyrics on each new run

`rhyme_writer.py` calls the pinned Qwen CPU model first for an original episode outline/title/description, then for new five-second verse lines and corresponding scene actions in chapters up to two minutes long. A 10-minute episode has 60 original lines alternating with 60 fixed Dudi refrain lines. Drafts checkpoint after the outline and each chapter; retries with the same run ID resume that story. Use a new run ID to request a new song.

Normalized verse lines and four-word phrase overlap are checked against `lyrics-history.json` in the private Drive folder, excluding the shared refrain. New lyric identities are reserved before music/image jobs start, including scheduled or unfinished episodes. Repeated or overly similar verses trigger rewriting, then failure if the bounded retries cannot produce a valid result. This is a practical duplicate check, not a guarantee that every possible phrase is globally unique. The workflow installs `requirements-lyrics.txt` and allows 90 minutes for CPU writing; it never substitutes the former template verses on model failure.

Overlong generated titles and descriptions are shortened at word/sentence boundaries before schema validation. Sung lyrics and scene actions are never truncated. Invalid content receives up to three attempts with the failed constraint and actual length supplied to the model. Failure artifacts include an initial draft and `failure.json` with safe error codes and diagnostics, allowing inspection or checkpoint resumption without exposing credentials.

Verse validation keeps accepted lines and requests only missing replacements, with word-count and duplicate feedback. Up to six repair requests are allowed per chapter per invocation. Partial chapters checkpoint after each response; resuming the same identity preserves accepted lines and advances repair seeds. Exhaustion records `lyrics_verse_validation` with chapter, accepted/required counts and rejection reasons; lyrics are never truncated or replaced with templates.

## Recover a finished upload

Use **Recover finished video publication** with the original GitHub run number and song run ID. It restores music, scene sources, the finished MP4 and render fingerprints, verifies them, then resumes the original Drive/YouTube checkpoint without generating or uploading another video. Publication logs expose exact local guard failures without API bodies. If YouTube omits the synthetic-media readback, the publisher explicitly updates the existing video disclosure while preserving live visibility and schedule, and records a successful write receipt bound to that video. An explicit false readback still fails verification.

## Lyric-led cartoon variety

New episodes choose a story-specific cast (animals, friendly vehicles or gentle fantasy creatures), setting, props and pastel palette instead of always using a yellow duckling and white bunny. The cast description stays consistent within that episode. Each image prompt starts with the lyric-specific action, followed by the episode cast/world and the existing cute 3D storybook style. Recent visual identities are saved alongside lyric history to guide variety in future outlines. This guides the image model; exact character consistency and visual uniqueness still depend on its output.

Use a new `run_id` for this writer version. Finished songs and old storyboards keep their existing lyrics and cast; old writer drafts require a fresh run ID.

Visual planning prose (`characters` and `visual_world`) is normalized at word/sentence boundaries before schema validation, just like titles and descriptions. The saved normalized identity is used for every chapter; sung lyrics and scene actions are never truncated. Character/world limits are 320/240 characters, explicitly included in the outline instructions. Retryable model/schema failures receive up to three request rounds with different seeds, each retaining the existing three validation attempts. Completed chapters and accepted verse lines remain checkpointed. Permanent failures still report safe diagnostics and preserve recovery artifacts instead of publishing invalid content.

## Shorts with native portrait illustrations

Every new generation starts **16 landscape image shards plus 4 separate portrait image shards**, all after lyrics are ready. The portrait shards generate only the eight five-second scenes needed for the default first 40 seconds, at native 576×1024 (9:16). They use the same lyric scene actions and episode character descriptions with vertical composition instructions and separate seeds. Landscape scenes and portrait scenes have separate folders and resumable manifests.

After the long-video, portrait and Shorts music jobs finish, the Shorts workflow animates those portrait images full-screen at 1080×1920 using the existing storybook motion renderer. It uses separately synthesized Shorts audio from `short-audio/clip-START-DURATION/song.wav`. No blurred landscape filler is used. Missing, corrupt or non-9:16 portrait illustrations stop export instead of silently restoring the old layout. Selected lyrics are reused; portrait images and Shorts music are generated separately.

The Short follows the parent's public/scheduled mode. Scheduled remains the default: the existing first 6AM New York slot at least 72 hours after upload. `PUBLISH_ENABLED=true` is required to upload; otherwise a downloadable preview is saved. Kids/AI disclosures remain enabled. The long-video custom-thumbnail upload is skipped for Shorts.

For an older finished video, run **Create and publish a rhyme Short** with its GitHub `source_run` and original song `run_id`. Its `kids-video-SOURCE_RUN` artifact must still be available (seven-day retention). This standalone workflow starts four portrait image shards and one independent music job in parallel. Choose start 0, 10, 20, etc. and duration 20, 30, 40 or 50 seconds. Automatic calls reuse the already prepared portrait shards, avoiding a second generation.

Portrait publication checkpoints use `shorts/RUN_ID/music-portrait-clip-START-DURATION/state.json`, separate from the previous blurred-layout Short. Existing scheduled/uploaded Shorts are not replaced or deleted by this change. Repeating a portrait request with the same inputs resumes its upload; a changed source is refused under that same identity. Unknown upload outcomes require reconciliation rather than risking a duplicate. Private Drive checkpoints remain outside long-video media cleanup.

For a local export, supply `output/RUN_ID/song.json`, `short-audio/clip-START-DURATION/song.wav` and `portrait/scene-NNN-source.png` for the selected range, then run `python shorts.py --run-id RUN_ID --start 0 --seconds 40`. Source/output hashes and a full video/audio decode validate the export before upload. `rhyme-short-*` artifacts contain the finished Short; `short-publication-*` contain publication checkpoints; `short-artwork-*` contain native portrait images and generation manifests.

## Fixed public title, description and blank tags

All new YouTube uploads, including Shorts, use the exact owner-supplied title and description in `upload_metadata.json`. Tags are always `[]`. The description is sent verbatim: no automatic credit line, extra hashtags, or `#Shorts` suffix is added. The fixed title is 97 characters and the description is 3213 characters. Internal story titles/descriptions remain available for lyric planning, novelty checks, and source identification; they are not selected as public metadata. This avoids breaking saved storyboards or treating every song as a duplicate because the public title is shared.

The previous metadata selection is commented out in `pipeline.publish` and `shorts.short_metadata`. To restore story-based metadata, restore the two commented assignment lines in `pipeline.publish` instead of the fixed metadata assignments; in `shorts.short_metadata`, restore the commented return block instead of `fixed_metadata()`. Keep the existing settings, upload checkpointing, disclosures, and verification intact. The original `kids_rhymes.upload_description` and `metadata_tags` helpers remain available.

This selection applies when starting a new upload. Existing uploaded/scheduled video IDs keep their checkpointed metadata, so resuming an upload does not silently change a live video's title or description. Updating existing YouTube videos requires a separate explicit metadata update. No existing video is edited by this code change.

Shorts title override: new Shorts use `shorts_title` in `upload_metadata.json`: `Dudi dudi dum dum 🍼😻#shorts #shortsfeed #dudidudidam`. Long videos retain the fixed `title`. Both formats keep the same fixed description and empty tags. The Shorts publisher explicitly selects the Shorts metadata variant before upload.

## Independent Shorts music

The `short_music` job starts immediately after lyrics, alongside long-form music, the 16 landscape image shards and the 4 portrait image shards. It uses the pinned ACE-Step CPU runtime to synthesize a fresh 40-second female-vocal dance arrangement using the selected eight storyboard lines; no audio is cut from the long video. The audio reference continues to provide the existing channel style. New instrumentation/melody is model-generated and not guaranteed to differ in every detail. The renderer uses that new audio starting at its beginning; `clip_start` selects lyrics/images, not an offset inside the new music.

Music requests and progress are checkpointed separately under `output/RUN_ID/short-audio/clip-START-DURATION/`. Saved outputs are fingerprinted and duration-checked. Too-short results get up to three attempts; no looping/padding is used. `short-music-*` artifacts carry the new audio and checkpoints. Automatic Shorts reuse the prepared music; manual Shorts requests launch their own music job in parallel with portrait generation. New portrait/music uploads use a separate checkpoint namespace so existing uploaded Shorts are not overwritten.

Parallel jobs reduce serial waiting, but runner limits can queue jobs and synthesis time still varies. Workflows already started use their original commit; this change applies to newly started workflows.

## Recover a Shorts scheduling failure

New uploads wait for YouTube processing readiness before automatic scheduling, then confirm the exact frozen timestamp by readback. Temporary server/rate errors and a recent, owned private upload's generic 403 receive bounded readiness retries. Named permission/quota failures, wrong ownership, rejected processing, and changed visibility stop with the original video ID retained. Retries never insert another video or report an unconfirmed schedule as complete.

For an already uploaded Short whose schedule/verification failed, run **Recover existing Shorts publication** with the failed workflow's `source_run` and original song `run_id`. It loads `short-publication-SOURCE_RUN`, requires the same uploaded video ID and source fingerprint in private Drive, and resumes only that existing video. It does not generate images, audio or video. Checkpoints are saved even if recovery fails. YouTube permission changes or service failures cannot be guaranteed away; permanent failures require resolving the reported account/service condition.


## Reference thumbnails, character motion and continuous music

New generations use the same generation pipeline upgrades as
`Asif-Rezan/youtube-motivation-automation` at `73533e7`:

- Five bundled thumbnail references are selected with equal probability using a
  stable generation seed. A retry or another shard reuses the same reference.
  Consecutive generations may select the same picture. Strength defaults to
  `0.50`; `THUMBNAIL_REFERENCE_IMAGE` remains an explicit single-file override.
  Only thumbnails use references. SSD-1B generates at 1344×768, then crops six
  pixels from the top and bottom and exports a 1920×1080 JPEG below 2 MB.
- New lyric outlines keep one or two cute baby animals as the main characters,
  with a small child companion in a dreamy natural setting. The soft, rounded
  3D storybook style and five-second image changes remain.
- Landscape and portrait image shards prepare foreground masks, inpainted
  backgrounds and validated five-second clips. Actors get varied gentle waves,
  waist/leg motion, sways or hops, with conservative blinking where faces are
  detected confidently. Camera/background motion adds depth. This is image
  deformation, not generative video or full skeletal animation. Invalid masks
  use a logged camera-motion recovery; unrelated errors still stop the job.
- New music requests 120 BPM in the prompt and the model parameters, with
  continuous instrumental backing. Mastering targets -14 LUFS / -1.5 dBTP and
  80 ms joins. Bounded edge-silence repair preserves duration without pitch
  shifts; excessive gaps retry only the affected part. Native Shorts audio is
  recovered from valid checkpoints before synthesizing again. These checks
  detect substantial silence; they do not guarantee flawless musical phrasing.
- CPU music workers reserve runner resources, retain failure diagnostics and
  save completed parts. Lyrics retain accepted lines during bounded repairs.
  Cleanup preserves media on metadata mismatches and reports API failures.

Both long videos and Shorts receive the animation and music upgrades. The
existing dedicated Drive folder, channel secrets, fixed public metadata,
72-hour / 6 AM New York scheduling, and bounded package installer are retained.
Use a new run ID on updated main; a retry of an old Actions run uses its old
commit. Existing published videos are not modified. Full model inference is
not part of component checks; a newly generated video still needs visual and
listening review.


## Bounded internal-silence recovery

Music quality checks now distinguish repairable short silence from excessive
missing audio. Internal gaps up to 3.5 seconds are removed only when their total
is at most 5% of that part and combined edge/internal trimming stays within 10%.
Five-millisecond fades soften each edit; pitch-preserving tempo compensation
restores the planned duration, without looping or silent padding. The finished
mix must pass strict silence and duration checks. Larger gaps still regenerate
only the affected part, with at most three quality attempts.

Previously rejected candidates from the same run/part are checked before starting
another CPU synthesis. Valid earlier parts are retained. Checkpoints record the
repair windows, candidate recovery and final mastering settings; each failed
attempt keeps a separate audio candidate. Failure artifacts include `failure.json`
and an explicit `audio_internal_gap` diagnostic instead of a generic error.
The 120-second part failure at 91.61–94.57 seconds is covered by a real FFmpeg
regression including pitch and output-duration checks. Generative audio quality
is still not guaranteed; excessive missing audio remains a visible failure.
