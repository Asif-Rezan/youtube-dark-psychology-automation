# Verified Drive media cleanup

The workflow `drive-cleanup.yml` checks all tagged episode checkpoints every
hour, on manual dispatch, and when cleanup code changes. The generation workflow
also sweeps completed episodes after its long video succeeds, independently of
Shorts success. Reports include pending runs, failures and account quota before
and after the sweep; they are retained as GitHub artifacts for 14 days.

A scheduled/private video is deferred. Once YouTube reports the same video on
the expected channel as public, processed, successfully encoded and HD, its saved
upload title/description/tags and thumbnail receipt must also match. The upload
body takes precedence over the original generated story metadata. Scheduled
checkpoints are refreshed to published only after verified cleanup.

Only the allowlisted temporary long-video media are removed: storyboard archive,
audio, finished video and image/thumbnail files. The private automation folder,
exact file ID, workflow-key hash, name and permissions are checked before each
permanent deletion. A journal is persisted first and every deletion is recorded,
so interrupted attempts resume safely. State/history/lyrics, Shorts checkpoints,
Facebook checkpoints and unrelated Drive files are retained. Small cleanup
journals may use the normal 100 MiB upload reserve, while ordinary media uploads
still require that reserve; no storage upgrade is purchased.

Unfinished, unavailable, mismatched, private or unverified uploads are never
purged merely because they are old. Such runs are preserved or reported for
review. A failed check does not prevent other eligible runs from being examined,
but expected eligibility exclusions do not fail generation. Missing videos, metadata/identity mismatches, incomplete publication receipts and non-public/non-HD videos are preserved with structured reasons and field names in `review`. They emit warnings without exposing metadata or API response bodies. Authentication, API, storage/journal and unsafe deletion-target failures remain visible failures. YouTube verification requests use three SDK retries for transient failures. Near-full quota is surfaced
in the summary rather than bypassing publication verification.

In reusable Shorts workflows, generation of already-prepared music/portraits is
intentionally skipped. Facebook Reel publication explicitly requires successful
Short completion and tolerates those intentional ancestor skips. Recovery of
run 41336716292 reuses its existing Short artifact without generating or
re-uploading a new YouTube Short.

Manual cleanup dispatch accepts `dry_run=true` to audit eligibility without writing journals or deleting media. This distinguishes legacy publication mismatches from operational failures before a cleanup fix is rolled out. The original failed generation remains in GitHub history; a new cleanup verification uses the corrected code without regenerating or re-uploading the video.

Tag comparison uses `upload_settings.normalized_tags`, matching upload verification: tag order, case and repeated whitespace do not create false mismatches. Real differences still preserve recovery media for review.
