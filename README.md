# Grow with Rezan: historical documentary automation

This repository makes one original English historical documentary video per day for the **Grow with Rezan** channel (`UCYjz7d66SsshimfpxZahlhQ`). Videos are uploaded **privately** at 06:00 Asia/Dhaka. The 20 CPU image workers, seven-second visual timeline, Kokoro narration, captions, music, thumbnail, private upload verification and recovery checkpoints remain in place.

Topics rotate through Ancient Egypt and pyramids; archaeology and underground structures; ancient civilizations; Islamic history; and people in Islamic intellectual and travel history. The curated [topic and source list](history_topics.json) supplies factual anchors for each episode. The planner avoids topics from the last ten videos and rejects highly similar recent titles and outlines. Scripts must distinguish evidence from interpretation, avoid invented dialogue and unsupported claims, and include source links in descriptions. Generated scenes are labeled as artistic historical reconstructions.

## YouTube title, description and thumbnail

After the historical script is written, a separate packaging step drafts three accurate title and thumbnail pairs. It requires the topic's search phrase near the start of a concise title, rejects sensational wording, and selects a complementary 2–5 word question that creates a specific curiosity gap. The question must connect to a documented visual feature and be addressed in the episode. The unique description states the subject in its first sentence, explains the evidence, links the episode's sources and labels reconstructions. Tags are limited to a small set of relevant search variants; they are a secondary discovery signal. Uploads use YouTube's Education category.

Each topic now supplies a source-backed visual scene: a scale contrast, a passage into shadow, a path, or a physical trace. The thumbnail prompt puts that scene before style words so the image model draws the visual question. The renderer adds focused light to the artwork on the right and reserves the left side for a large question. A high-contrast 1280×720 layout is added in code, with no text bar covering the bottom of the scene. These rules improve clarity but cannot predict CTR; review private uploads and compare titles and thumbnails against actual YouTube Analytics before publication.

## Historical illustrations

Images use `segmind/SSD-1B` on CPU at **1024×576**, 16 inference steps and guidance scale 9. A new image appears every **seven seconds**. Each image prompt follows the spoken historical scene, showing relevant sites, objects, architecture or people with period-appropriate details. No wizard reference image is loaded in the video or thumbnail path. The CPU image check produces a historical test image for visual review. AI reconstructions may still contain inaccuracies; inspect the private video before public release.

## Required isolated setup

Use a **dedicated, previously unused Google Cloud project and Desktop OAuth client** for this repository. The selected project is `project-2d338b69-9ff5-49c5-87f` (My First Project). Enable YouTube Data API v3 and Google Drive API. Complete Google consent for the Grow with Rezan brand channel and a separate, owner-only Drive folder. Set these GitHub Actions secrets in **this repository only**:

- `GROQ_API_KEY`: the new project's key. Never commit it.
- `YOUTUBE_TOKEN_JSON`: OAuth authorized-user JSON for the Grow with Rezan channel. Required scopes: `youtube.upload` and `youtube.force-ssl`.
- `DRIVE_TOKEN_JSON`: OAuth authorized-user JSON with Drive file access for the new app.
- `DRIVE_FOLDER_ID`: ID of the dedicated Grow with Rezan folder created by `setup_drive_folder.py` with the new Drive OAuth token. This is mandatory. The folder carries a channel-specific marker; the code rejects the source project's folder.

The expected channel ID is fixed in the workflows and upload checks. If the token belongs to a different channel, readiness and upload stop. Keep all credentials out of the repository and Actions logs.

The daily workflow is `.github/workflows/daily-upload.yml`. Run **Google OAuth check** first, then manually dispatch one daily workflow to verify a private HD upload before relying on the schedule. `cleanup_run` retries verification and cleanup of an already completed run without uploading again. A failed or ambiguous upload retains its Drive assets for reconciliation.

The source repository and its secrets, Drive folder, OAuth project, YouTube token, and schedule are independent of this repository. This repository's setup must be completed before its daily workflow can run successfully.

## Local checks

`python -m unittest -v` runs component and safety checks. Full video generation and upload require the cloud credentials and a live private test.

## Story duration recovery

Fresh daily stories keep the twenty-chapter historical documentary outline and target 84
spoken words per chapter, plus the closing CTA. Set `STORY_CHAPTER_WORD_TARGET`
between 75 and 88 to tune the initial request. Actual Kokoro audio duration,
not word count, controls acceptance: 600–900 seconds is required, with 720–840
seconds preferred.

Preparation measures every chapter before making images. A slight overrun uses
at most a 4% FFmpeg tempo correction. Larger overruns use Groq to shorten
selected chapters; underruns use Groq to add relevant documented historical details.
At most three correction attempts run. Changed chapters alone are resynthesized,
then word timestamps, captions, and every seven-second visual window are rebuilt.
Audio and transcript caches are tied to content hashes so changed text cannot
reuse stale timing. The corrected story, narration, captions, storyboard source
hash, and validated duration are checkpointed together before the twenty image
workers start. Recovery failure stops before rendering or upload. The prepare job
has a 90-minute limit to accommodate bounded Groq and CPU narration retries.

## Recovering a Drive cleanup timeout

Open **Resume verified private video cleanup** in GitHub Actions and enter the original
`daily-<run ID>`, such as `daily-38644830219`. This workflow runs only
`daily_publish.py`: it rechecks the existing video's channel, exact metadata,
private visibility, successful HD processing, and confirmed thumbnail before
deleting any run media. It never generates or uploads a video.

Small JSON checkpoints use bounded backoff for timeouts, connection errors, rate
limits, and temporary server errors. Retries keep one Drive file ID. A new file
uses a preallocated ID, so a timed-out create cannot create duplicate checkpoints;
an ambiguous result is accepted only if its saved JSON matches. Cleanup saves an
ID manifest before deletion and checkpoints each ten deletions and at completion.
If interrupted, it resumes from the manifest and treats previously deleted IDs
as complete after Drive returns 404. Essential state and story files are preserved.

### Drive timeouts and upload-only shard recovery

Drive reads and uploads retry temporary failures with bounded exponential backoff
(5 failures per operation; 2, 4, 8, 16 second delays). Media uses 8 MiB resumable
chunks, a preallocated file ID, size/MD5 verification and an on-disk ID journal.
An ambiguous response is reconciled against that same ID. Matching files are
skipped; duplicates, privacy failures and identity conflicts stop the operation.
Small JSON checkpoints use the same verified, idempotent write path. YouTube
insertion is deliberately outside these retries and keeps its existing guards.

Daily image jobs retry upload-only once on the same runner if saving fails. If
that fails, completed/partial work and reserved IDs are encrypted with AES-GCM
before a GitHub artifact is saved for 14 days. The encryption key is derived from
the existing Drive refresh token; keep that token available until recovery is
finished. Replacing it makes old backups unreadable. No plain media, credentials,
or resumable session URLs are placed in the artifact. A hard runner termination
or backup service failure can still prevent preservation.

Use **Recover original shard uploads only** with the original numeric GitHub run
ID and shard number. If available, supply the original artifact name
`private-shard-<shard>-<attempt>`. It checks the original prepared state and exact
story/plan/duration, then reports missing assets before writing anything. With a
complete local/Drive bundle it uploads only missing/different assets and writes
a verified per-shard manifest. It never generates images, narration or videos,
never calls YouTube, and never deletes media. A request can also be triggered by
committing `.github/recovery-request.json` on main, e.g.
`{"run_id":"38730964321","shard":9,"backup_artifact":""}`.

If the original runner is gone and Drive or encrypted backups do not contain all
required assets, recovery stops. Do not use **Re-run failed jobs** to retry only
an upload: the old workflow reruns generation on a fresh runner and uses its old
code revision. Successful upload-only shard recovery does not automatically
assemble or upload a video; inspect all shard results and existing YouTube state
before continuing those stages.
