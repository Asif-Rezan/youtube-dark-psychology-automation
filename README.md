# Grow with Rezan: dark psychology video automation

This repository is an isolated copy of the `youtube-motivation-automation` pipeline for the **Grow with Rezan** channel (`UCYjz7d66SsshimfpxZahlhQ`). It creates original fictional English dark psychology stories and uploads a daily 10–15 minute illustrated video **privately** at 01:00 Asia/Dhaka. The 16 CPU image workers, seven-second visual timeline, Kokoro narration, captions, original music, thumbnail, private upload verification, run checkpoints, and run-scoped Drive cleanup follow the source pipeline.

Stories explore manipulation, coercive control, gaslighting, deception, social pressure, and boundaries. Prompts require fictional labeling, believable consequences, and a protagonist who regains agency. They avoid glamorizing abuse, instructions for exploitation, and unsupported diagnoses.

## Required isolated setup

Use a **new Google Cloud project and Desktop OAuth client** for this repository. Enable YouTube Data API v3 and Google Drive API. Complete Google consent for the Grow with Rezan brand channel and a separate, owner-only Drive folder. Set these GitHub Actions secrets in **this repository only**:

- `GROQ_API_KEY`: the new project's key. Never commit it.
- `YOUTUBE_TOKEN_JSON`: OAuth authorized-user JSON for the Grow with Rezan channel. Required scopes: `youtube.upload` and `youtube.force-ssl`.
- `DRIVE_TOKEN_JSON`: OAuth authorized-user JSON with Drive file access for the new app.
- `DRIVE_FOLDER_ID`: ID of the dedicated Grow with Rezan folder created by `setup_drive_folder.py` with the new Drive OAuth token. This is mandatory. The folder carries a channel-specific marker; the code rejects the source project's folder.

The expected channel ID is fixed in the workflows and upload checks. If the token belongs to a different channel, readiness and upload stop. Keep all credentials out of the repository and Actions logs.

The daily workflow is `.github/workflows/daily-upload.yml`. Run **Google OAuth check** first, then manually dispatch one daily workflow to verify a private HD upload before relying on the schedule. `cleanup_run` retries verification and cleanup of an already completed run without uploading again. A failed or ambiguous upload retains its Drive assets for reconciliation.

The source repository and its secrets, Drive folder, OAuth project, YouTube token, and schedule are independent of this repository. This repository's setup must be completed before its daily workflow can run successfully.

## Local checks

`python -m unittest -v` runs component and safety checks. Full video generation and upload require the cloud credentials and a live private test.
