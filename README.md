# Reference migration — 2026-11-09

- Destination: `Asif-Rezan/youtube-dark-psychology-automation`.
- Reference: [successful run 42540767777](https://github.com/Asif-Rezan/youtube-motivation-automation/actions/runs/42540767777), pinned to `44f8a3384a4e4e02d4f67e94929195cbe225c637`.
- Previous code: `9768a2b`; backup documentation commit: `6a7dbe3`.
- Rollback tag: `before-motivation-reference-2026-11-09`.
- [Previous README and complete historical logs](docs/archive/before-motivation-reference-2026-11-09-README.md).
- Music, 240-second default (180–300 allowed), chorus-first lyrics, video, character animation, title/description/tags, opening-scene thumbnail, audio mastering, retry handling, Shorts and publication follow the pinned reference.
- Destination YouTube fallback `UCYjz7d66SsshimfpxZahlhQ`, Facebook Page `301624356367343`, existing private Drive namespace, account setup and OAuth pages are preserved. Existing secrets and repository variables are not copied from the source.
- Destination finished-publication recovery retains independent Facebook retry and guarded cleanup; destination credential verification is retained.
- Source-only legacy project and one-off recovery triggers referring to source run IDs are excluded. No historical source episode is requested by this migration.
- Reference v1 rollback tags mentioned below belong to the source repository; use this destination's rollback tag to restore this project.

Restore the previous implementation without rewriting history:

```sh
git switch -c codex/restore-before-reference
git restore --source before-motivation-reference-2026-11-09 -- .
git commit -m "Restore generator before reference migration"
```

Code rollback does not restore credentials, cloud settings or deleted/published media.
Use a fresh run ID after migration; previous 600-second artifacts are not converted.

Validation: all 204 component tests pass, including real FFmpeg audio/motion checks,
metadata/retention tests, credential guards and destination storage tests. Sixteen
core generation/configuration files were compared byte-for-byte with the pinned
reference. `git diff --check` passes. Local actionlint could not be downloaded
(GitHub returned HTTP 504); the component-check workflow runs pinned actionlint.
A full destination cloud generation/publication has not been run as part of this migration.

---

## Version log (how to go back)

| Version | Commit / tag | What it is |
|---|---|---|
| v2 retention (current) | this PR | 4-minute chorus-first verse-chorus song, opening scene = thumbnail, punch-in hook motion, two dance moves per scene, consistent lighting, SEO titles without sound-alike names, real chapters; 130 BPM bouncy kids-pop groove, a NEW Qwen-written chorus hook every episode (no fixed Dudi refrain), short energetic final chorus with a button ending |
| v1 baseline | tag `v1-pre-retention-2026-11-07` (commit `c1b61b2`) | 10-minute song with the refrain after every line, 8-step ACE-Step, best-scene thumbnail |

Why v2: video `r2gjHCPxpEU` kept 80% of viewers at 0:06, 36% at 0:24 and 8% at 1:55
(average 0:42 of 10:01, 25% likes), with 95.6% of traffic from Suggested next to other
channels' "Duri Duri Dum Dum" videos.

To return to v1 for new episodes, restore the old code on a branch and merge it:

```bash
git switch -c rollback/v1 && git restore --source v1-pre-retention-2026-11-07 -- . && git commit -m "Roll back to v1 generator"
```

`VIDEO_DURATION_SECONDS` (`.github/workflows/music.yml`) controls length: 180–300 seconds in v2,
480–720 in v1. `ACESTEP_INFERENCE_STEPS` (default 8, max 20) tunes the turbo music model, which
upstream distills for 8 steps.

## Retention-focused episodes (v2)

- **Hook first:** every song opens with the full four-line chorus (0:00–0:20), sung with
  ACE-Step `[Chorus - high energy]` / `[Verse]` tags and "starts instantly, no intro" in the caption.
- **Thumbnail = first frames:** the package must pick scene 0 for the thumbnail, and the scene-0
  clip is animated from `thumbnail-source.png`, so viewers see exactly what they clicked.
- **Faster opening:** the first three clips (15 s) cut from a wide shot to a punch-in at 2.5 s,
  with a livelier pan and 1.5x larger dance moves.
- **More dance:** each dance scene switches to a second move at 2.5 s; chorus scenes rotate
  eight dance poses; every scene and the thumbnail share one lighting/time of day.
- **Structure:** four-line verses alternate with the fixed channel chorus
  (`dudi dudi dam dam dudi dudi dam`, `clap your hands and dance with me`, ...).
- **SEO:** titles start with the real search phrase (animal + action + "Song for Kids"), never
  other channels' song names or sound-alikes (Dodi/Duri/Duty/Dum Dum, enforced in code), and
  descriptions get real chapter timestamps from the storyboard.
- **Checks:** `episode-packaging-check.yml` runs real Qwen on PRs; `episode-preview.yml` builds a
  full video without publishing on any `preview/**` branch and verifies length and the opening frame.

## Cute animals with a child playmate

New episodes keep cute baby animals as the leads, with a small child playmate
in the original soft, pastel 3D storybook style. Shared refrains get separate
dancing compositions and varied gentle movement guided by the new 130-BPM request. Image model, image
size, step counts and guidance are unchanged. See [cast and dance details](docs/toddler-animal-dance.md).

## Lyric word-bound recovery

Sung lines retain a compact 4–12 plain-word constraint in the native Qwen grammar,
while large prose character bounds remain outside the native parser. The prompt
aims for 4–8 words. Contractions/hyphens are avoided so generation and validation
count words consistently. Rejected candidates are saved and supplied to targeted
rewrites alongside their constraints; accepted lines and completed chapters stay
in the checkpoint. Lyrics are never truncated or replaced with canned text.

The lyrics stage retries explicitly retryable model/content failures up to three
times using the same run ID and saved draft, with bounded backoff. Fatal errors
and non-lyrics stages are not replayed. Successful recovery clears that stage's
stale failure marker. A real CPU-model regression tests an adversarial 13-word
request and a complete twelve-line chapter before production dispatch.

## Automatic character animation

Every newly generated landscape and portrait scene now uses CPU character
segmentation (BiRefNet Lite), background completion (LaMa), and layered puppet animation.
Original 3D storybook artwork stays intact in the foreground. Characters breathe,
sway and make gentle hops with landing squash; rabbit scenes additionally bend
the upper ears and move the tail region. The main connected character/group is animated;
this is not full 3D rigging, action understanding or speech lip-sync. Automated
mattes/inpainting can vary from the hand-prepared demo and require visual review.
Implausible empty or oversized masks stop the affected image shard for review.

Sixteen landscape and four portrait workers prepare layers and exact five-second
1080p scene clips after image generation exits, releasing diffusion model memory.
Final assembly requires current verified character-motion clips; it cannot silently
fall back to the old zoom-and-bubbles slideshow. Clip/source hashes invalidate
stale or corrupt caches. Layer PNGs and MP4 clips travel in the same seven-day
artifacts as their source images, so retries reuse finished work. Old runs without
these clips must regenerate their image shards using the new workflow.

Install CPU PyTorch, `requirements.txt`, and `requirements-motion-cpu.txt`, then
run `python character_motion.py --root output/RUN_ID` with the same IMAGE_SHARD,
IMAGE_SHARDS and IMAGE_VARIANT values used to generate that worker's artwork.
The first run downloads public BiRefNet Lite and LaMa model weights. No paid image/video
inference API or GPU runner is used. Model sources: [rembg](https://github.com/danielgatis/rembg)
and [LaMa CPU wrapper/model](https://github.com/enesmsahin/simple-lama-inpainting).

## Facebook Page cross-posting

Facebook integration setup and recovery: [docs/facebook-publishing.md](docs/facebook-publishing.md). The destination is Rezan Relaxation (`297892583408910`). Existing YouTube generation/upload remains active; Facebook requires its own Page authorization and `FACEBOOK_PAGE_ACCESS_TOKEN` secret. Facebook is enabled independently with `FACEBOOK_PUBLISH_ENABLED=true` after the authorized live test. Do not treat the code installation as a completed Meta connection.

## Automatic upload restored for the existing channel

The existing destination is `UCztvMrNCT34DO3DtzLPgWaw`, preserved from the archived Ancient Humans workflow. All active workflows resolve `EXPECTED_CHANNEL_ID` from an existing secret, then an optional repository variable, then that original channel ID. The uploader still verifies that OAuth belongs to this exact destination. No new OAuth token is required for this migration.

`PUBLISH_ENABLED=true` enables long/Short uploads, and `AUTOMATION_ENABLED=true` enables daily generation at 03:00 Asia/Dhaka. Uploaded videos use the reference automatic scheduling policy: first 06:00 America/New_York slot at least 72 hours after upload completion. These are repository Actions variables, not secrets. Explicit false disables the corresponding behavior. Existing token and Drive secrets are reused.

## Shorts preview recovery and publication preflight

Preview generation (`PUBLISH_ENABLED` unset or false) does not require YouTube credentials. Reusable Shorts workflow secrets are optional at dispatch time; enabling publication requires all four existing repository secrets, checked before model generation and before Shorts rendering. Missing values produce a diagnostic listing names only. No credentials or publication variables are changed automatically.

If long video/music/portrait jobs completed but Shorts orchestration failed, run **Create and publish a rhyme Short** on the current main branch with `source_run=40902873254`, `run_id=kids-rhyme-20261029-2134`, `prepared_music=true`, `prepared_portraits=true`, start 0, duration 40. This reuses the saved music/portrait artifacts instead of running the models again. Artifacts expire after seven days. Rerunning an old workflow uses its old workflow definition, so dispatch the corrected workflow for this recovery.

## Repository account compatibility fix

This repository uses its existing `DRIVE_TOKEN_JSON`, `DRIVE_FOLDER_ID`, `YOUTUBE_TOKEN_JSON` and `EXPECTED_CHANNEL_ID` secrets, not the reference project's hardcoded account/channel. The authenticated Drive user must own the configured active private folder; shared/foreign/trashed folders are rejected. A private `Kids Rhymes - YouTube Automation` child folder marked `youtube_kids_rhymes_root=v1` is created once and reused. Kids history/checkpoints and cleanup stay inside that child, leaving Ancient Humans data untouched. Connection verification may initialize this child folder; it never uploads videos. YouTube continues to require an exact match with `EXPECTED_CHANNEL_ID`. Account setup requires an explicitly supplied channel ID, without requiring the reference channel handle. Older reference-specific account/folder instructions below are superseded by this section.

# YouTube Motivation Automation — kids rhymes migration

This repository now runs the kids rhymes pipeline copied from [dudi_dam_tv](https://github.com/Asif-Rezan/dudi_dam_tv/tree/6add42d9d315c4f73ec0d40c51c128fb2be76c15) at commit `6add42d9d315c4f73ec0d40c51c128fb2be76c15`.
The active reference files are unchanged except this README and `setup_accounts.py`, whose GitHub secret destination is this repository.

## Preserved Ancient Humans project

Previous main commit: `1db8f8262ff00570a4496c919511491357fbabe3` ([view original](https://github.com/Asif-Rezan/youtube-motivation-automation/tree/1db8f8262ff00570a4496c919511491357fbabe3)).
Every tracked file from that commit is preserved byte-for-byte under `legacy/ancient-humans/`, including its README, tests, assets and workflows. This directory is an inactive archive: the former workflows are outside `.github/workflows/` and the active pipeline never imports it. The old files are preserved as working source rather than adding comment markers that would damage Python/YAML/assets. Do not run old scripts from this archive against production credentials.

To inspect the original project without changing the kids pipeline:

```sh
git fetch origin
git worktree add ../ancient-humans-restored 1db8f8262ff00570a4496c919511491357fbabe3
```

To prepare a reversible restoration of the original project as a new branch:

```sh
git fetch origin
git switch -c restore-ancient-humans origin/main
git restore --source=1db8f8262ff00570a4496c919511491357fbabe3 --staged --worktree -- .
git commit -m "Restore Ancient Humans pipeline"
git push -u origin restore-ancient-humans
```

Run these commands from a clean checkout. Review and merge that branch through a pull request to restore the old project. This preserves the kids migration in Git history; no reset or force push is needed. Review repository Actions variables/secrets before enabling old uploads again. Uncommitted work in other local checkouts is untouched and is not part of this remote snapshot.

## Configure this repository

- Run account setup in this repository: `setup_accounts.py` writes secrets to `Asif-Rezan/youtube-motivation-automation`.
- Configure its own `YOUTUBE_TOKEN_JSON`, `EXPECTED_CHANNEL_ID`, `DRIVE_TOKEN_JSON`, and `DRIVE_FOLDER_ID` Actions secrets. Git cloning does not copy repository secrets or variables.
- The copied setup retains the reference channel guard (`@dudi_dum_tv`), Drive account guard and `dudi_dam_tv_root=v1` folder lookup. It can reuse the reference folder for the same account. For isolated history/artifacts, configure a separate private folder with the required app property and set this repository's `DRIVE_FOLDER_ID` explicitly. Review `storage.py` and `setup_accounts.py` before using another channel/account.
- Set `AUTOMATION_ENABLED=true` for daily generation and `PUBLISH_ENABLED=true` for uploads only when these repository credentials are ready. Existing repository variable values still apply after merging; they are not reset by this migration.
- Use **Verify Google connections** first, then manually generate a fresh run ID and review the result. The same reference long-video/Shorts generation and publishing workflows are included. No live generation or YouTube upload is performed by this code migration.
- Install `requirements.txt` and run `python -m unittest -v` for component verification. Full model inference additionally requires the pinned CPU dependencies, model downloads and FFmpeg documented below.

The original reference README follows; its project names, channel branding and behavior are retained intentionally. Any reference to account setup targeting `Asif-Rezan/dudi_dam_tv` below is superseded by the destination above.

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

This gives still illustrations a lively storybook presentation; it does not rig character limbs or lip-sync mouths. Motion follows the requested tempo (130 BPM for new episodes, 100 for older ones) as a visual guide, not measured audio beats. Full videos remain 1920×1080 and 8–12 minutes, with a new illustration every five seconds. Rendering is split into small clips to bound memory. `render-state.json` fingerprints the renderer version and inputs so an old static video is regenerated automatically.

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

## Story-based SEO metadata and matching thumbnails

New generation IDs run one additional local Qwen packaging pass after the lyrics.
It writes three truthful title candidates, chooses one, and creates a unique
story-specific description and 5–15 relevant tags. The topic/action and natural
kids-rhyme search phrases lead the title and opening description. Tags are
secondary discovery metadata, not a ranking guarantee. Title/description/tag
limits, selected-title membership and a source fingerprint are checked before
upload. Invalid output receives bounded retries, preserving the finished lyrics.
No hosted packaging API, live keyword-volume lookup or paid vidIQ call is needed
in production. The prompt uses qualitative title-thumbnail design guidance;
it does not predict or promise CTR.

The saved `song.json` contains `packaging.video`, `packaging.shorts`, three title
candidates and the selected thumbnail scene/focus. Shorts metadata describes only
the first 40 seconds; manually selected other clips derive metadata from their
actual lyrics. Retries reuse this saved package. Existing uploaded/scheduled IDs
retain their durable upload body and thumbnail receipt. `upload_metadata.json`
and its old fixed-metadata helper remain as historical files, unused by new
publication. Existing unpublished artifacts without a package fall back to their
own story metadata, never the shared fixed text.

The thumbnail uses an actual generated scene from the same episode as its img2img
reference (strength 0.35), emphasizing an existing baby-and-animal interaction
with expressive faces, clear silhouettes and a simple mobile-readable composition.
The scene's own image worker creates the thumbnail after the anchor exists,
without generating another reference image or using the previous external pool.
Source pixel checksums invalidate stale thumbnail caches. Native 1344×768
inference and 1920×1080 JPEG export remain. Full-model image quality and CTR still
need review after a real generation.

Facebook uses the verified YouTube upload body's matching title/description.
Account identities, language, music, animation, publishing schedule, disclosures
and cleanup guards keep their current settings.

## Independent Shorts music

The `short_music` job starts immediately after lyrics, alongside long-form music, the 16 landscape image shards and the 4 portrait image shards. It uses the pinned ACE-Step CPU runtime to synthesize a fresh 40-second female-vocal dance arrangement using the selected eight storyboard lines; no audio is cut from the long video. The audio reference continues to provide the existing channel style. New instrumentation/melody is model-generated and not guaranteed to differ in every detail. The renderer uses that new audio starting at its beginning; `clip_start` selects lyrics/images, not an offset inside the new music.

Music requests and progress are checkpointed separately under `output/RUN_ID/short-audio/clip-START-DURATION/`. Saved outputs are fingerprinted and duration-checked. Too-short results get up to three attempts; no looping/padding is used. `short-music-*` artifacts carry the new audio and checkpoints. Automatic Shorts reuse the prepared music; manual Shorts requests launch their own music job in parallel with portrait generation. New portrait/music uploads use a separate checkpoint namespace so existing uploaded Shorts are not overwritten.

Parallel jobs reduce serial waiting, but runner limits can queue jobs and synthesis time still varies. Workflows already started use their original commit; this change applies to newly started workflows.

## Recover a Shorts scheduling failure

New uploads allow up to 30 minutes (90 polls, 20 seconds apart) for YouTube processing readiness before automatic scheduling, within a shared 40-minute scheduling/HD-verification budget. Normal processing longer than two minutes no longer prematurely fails the upload. Pending checkpoints retain the same video ID and frozen release time for recovery. The uploader confirms the exact frozen timestamp by readback. Temporary server/rate errors and a recent, owned private upload's generic 403 receive bounded readiness retries. Named permission/quota failures, wrong ownership, rejected processing, and changed visibility stop with the original video ID retained. Retries never insert another video or report an unconfirmed schedule as complete.

For an already uploaded Short whose schedule/verification failed, run **Recover existing Shorts publication** with the failed workflow's `source_run` and original song `run_id`. It loads `short-publication-SOURCE_RUN`, requires the same uploaded video ID and source fingerprint in private Drive, and resumes only that existing video. It does not generate images, audio or video. Checkpoints are saved even if recovery fails. YouTube permission changes or service failures cannot be guaranteed away; permanent failures require resolving the reported account/service condition.

## Higher-resolution thumbnails

Thumbnails generate at 1344×768 with the same SSD-1B storybook model, using an actual scene from their own episode as the image reference. Export removes six source pixels from the top and bottom to produce a 1344×756 crop, then scales to a 1920×1080 JPEG using Lanczos. JPEG quality starts at 95 and is reduced only when needed to stay under a conservative 2 MB byte budget. Scene and portrait generation dimensions stay unchanged. Thumbnail-specific settings are `THUMBNAIL_IMAGE_WIDTH`, `THUMBNAIL_IMAGE_HEIGHT`, and `THUMBNAIL_IMAGE_STEPS`; the defaults are 1344, 768, and 20. The image manifest includes these settings so old low-resolution thumbnails are regenerated when a job resumes with this code. Export resolution is 1920×1080; this is not native 1920×1080 diffusion generation.

## Cute animal scenes and continuous upbeat music

New episodes restore the original rounded, expressive pastel 3D animal-story look, with a small child playmate alongside the animal leads in dreamy natural scenery. The same image model and resolution settings remain. Original lyrics use a 120 BPM generation request (previously 100), with the same sweet female vocal style and a continuous instrumental backing caption. Refrain animation uses the requested tempo while retaining per-scene movement variety.

New long and Short mixes use -14 LUFS loudness normalization with a -1.5 dB true-peak target. Natural silent onset/outro is trimmed before mastering. Long parts receive 80 ms crossfades; a bounded pitch-preserving adjustment restores the planned duration without looping or silent padding. Edge trimming plus overlap may consume at most 10 percent of the duration; larger deficits require a new generation. This can slightly change the resulting tempo, while the synthesis request remains 120 BPM. A real FFmpeg silence check distinguishes repairable silent edges from internal quiet gaps of at least 0.65 seconds below -45 dB. Finished masters are checked again, allowing only a short onset (150 ms) or natural outro release (350 ms). Only the affected generated part is retried (up to three attempts); repeated failure keeps completed parts and stops publication rather than shipping a silent gap. This checks mixed-audio silence, not vocal breathing or accompaniment pauses while a vocal is still audible. Already generated/published episodes are not remastered automatically.

Generation uses the pinned [ACE-Step BPM parameter](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/acestep/inference.py) and [FFmpeg loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm). Caption/BPM requests guide the model; exact musical tempo and the new visual appearance still need review on an actual new episode.

Failed Shorts retain per-attempt reason codes and rejected candidates. On resume, valid saved native syntheses are inspected and reused before any model call; legacy v1 checkpoints are supported. `audio-continuity-regression.yml` is a manual diagnostic for a recent failed run whose input/Shorts artifacts still exist. It restores the real checkpoint and proves recovery without AI inference or publication. Self-contained synthetic boundary/internal-gap regressions remain in the normal test suite after those temporary artifacts expire.


Cleanup verification requires the saved video/channel identity, matching title and
description, public visibility, completed HD processing and exact private Drive
file IDs/hashes. Changed YouTube tags are reported as a notice and do not prevent
cleanup. Scheduled/private media remains available for recovery until publication;
the hourly sweep revisits it. Cleanup permanently deletes only the verified
automation media and never empties the account's unrelated Trash.
