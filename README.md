# Grow with Rezan: dark psychology video automation

This repository is an isolated copy of the `youtube-motivation-automation` pipeline for the **Grow with Rezan** channel (`UCYjz7d66SsshimfpxZahlhQ`). It creates original fictional English dark psychology stories and uploads a daily 10–15 minute illustrated video **privately** at 01:00 Asia/Dhaka. The 16 CPU image workers, seven-second visual timeline, Kokoro narration, captions, original music, thumbnail, private upload verification, run checkpoints, and run-scoped Drive cleanup follow the source pipeline.

Stories explore manipulation, coercive control, gaslighting, deception, social pressure, and boundaries. Prompts require fictional labeling, believable consequences, and a protagonist who regains agency. They avoid glamorizing abuse, instructions for exploitation, and unsupported diagnoses.

## Story illustrations

Story images use pinned public `segmind/SSD-1B` weights on CPU at 1024×576. The previous DreamShaper model constants remain commented in `image_cpu.py` for restoration. The supplied [wizard reference](assets/wizard-reference.jpg) defines the recurring protagonist: long silver beard, weathered face, dark pointed hood, embroidered brown robe, wooden staff and glowing amber orb. This text-to-image model uses a detailed description derived from that reference for each wizard shot; it does not condition on the reference image pixels, so visual identity is approximate and should be reviewed before public release.

Fresh stories place the wizard in a fictional fantasy setting. Narration-aligned prompts change his action, expression, setting and camera framing with each seven-second window. Object-only scenes omit him. All images use cinematic fantasy lighting, mist, deep blue-gray shadows and amber orb light where the wizard is present. The `Free CPU image generation check` workflow creates a local test illustration and checks its size, content and scene match without producing or uploading a video.

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

Fresh daily stories keep the twenty-chapter Dark Psychology outline and target 84
spoken words per chapter, plus the closing CTA. Set `STORY_CHAPTER_WORD_TARGET`
between 75 and 88 to tune the initial request. Actual Kokoro audio duration,
not word count, controls acceptance: 600–900 seconds is required, with 720–840
seconds preferred.

Preparation measures every chapter before making images. A slight overrun uses
at most a 4% FFmpeg tempo correction. Larger overruns use Groq to shorten
selected chapters; underruns use Groq to add meaningful story events and dialogue.
At most three correction attempts run. Changed chapters alone are resynthesized,
then word timestamps, captions, and every seven-second visual window are rebuilt.
Audio and transcript caches are tied to content hashes so changed text cannot
reuse stale timing. The corrected story, narration, captions, storyboard source
hash, and validated duration are checkpointed together before the sixteen image
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
