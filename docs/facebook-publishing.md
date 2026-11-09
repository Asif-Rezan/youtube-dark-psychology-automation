# Facebook Page publishing

Destination: [Rezan Relaxation](https://www.facebook.com/rezan.relaxation/), Page ID `297892583408910` (confirmed in the Page's management links). Meta app: `Rezan Video Automation`, App ID `1768108484480464`, connected to business portfolio `747381864278018`. Existing YouTube and Drive credentials remain unchanged.

## One-time authorization

1. Register for Meta for Developers using the Page administrator's personal account. The user must explicitly approve Meta terms acceptance and complete authentication/account verification themselves when required.
2. Create `Rezan Video Automation` with the **Manage everything on your Page** use case and the matching `rezan_relaxation` business portfolio.
3. Authorize only the required Page with `pages_show_list`, `pages_read_engagement`, and `pages_manage_posts`. The authorizing person must be able to perform CREATE_CONTENT. Confirm current standard/advanced access and review requirements in the dashboard for the actual app/account; app creation alone is not publication authorization.
4. Obtain a Page access token, not a personal profile token. Validate `/me?fields=id,name` returns `297892583408910`. Store it only as repository Actions secret `FACEBOOK_PAGE_ACCESS_TOKEN`. Never commit it, put it in a variable, paste it into chat, or print it in logs. Record any token expiry/data-access expiry and renew authorization before expiry. Do not assume a token is permanent.
5. Run a controlled publication using existing episode artifacts and inspect Page identity, processing and the scheduled release. Set repository variable `FACEBOOK_PUBLISH_ENABLED=true` only after authorization is ready.

## Account setup verified October 30, 2026

The Meta app is **Published**. Its public [privacy and data deletion policy](https://asif-rezan.github.io/youtube-motivation-automation/privacy.html) is hosted from `docs/privacy.html` by the repository's existing GitHub Pages deployment.

Only Rezan Relaxation was authorized. The derived Page token was verified in Meta's debugger as Type Page, Valid True, **Expires Never**, with `pages_show_list`, `pages_read_engagement`, and `pages_manage_posts` limited to Page `297892583408910`. It is stored in `FACEBOOK_PAGE_ACCESS_TOKEN`; `FACEBOOK_PUBLISH_ENABLED=true` is enabled. Publishing the app does not itself remove token expiry: the non-expiring Page token was derived after extending authorization. Meta still displayed a separate **Data Access Expires** timestamp `1801076531` (January 27, 2027 UTC). Recheck authorization before that date and if publishing reports an authorization error. Password/security changes, permission revocation or losing Page access can invalidate the token; never promise uninterrupted permanent access.

The first live Reel test [run 41004538486](https://github.com/Asif-Rezan/youtube-motivation-automation/actions/runs/41004538486) uploaded existing episode `kids-rhyme-20261029-2134`, verified processing ready, exact Page/video identity and scheduled timestamp `1793617200` (November 2, 2026, 17:00 Asia/Dhaka). Facebook video ID: `1443974681239622`. A successful schedule is not proof of eventual public release; Meta processing, policy and account restrictions can still affect publication.

The landscape upload [run 41004686341](https://github.com/Asif-Rezan/youtube-motivation-automation/actions/runs/41004686341) also succeeded, verifying Facebook video ID `2584572045350123` and the same scheduled timestamp. Both items were confirmed as Public and scheduled for November 2 at 17:00 in Meta Business Suite. Meta currently labels both items as Reels in its content table, although the landscape file uses the Page `/videos` upload endpoint. Existing media was reused; these recovery runs made no YouTube writes.

The existing private storage account is `asifrezan.office@gmail.com`. Both Facebook checkpoint files were verified in its `Kids Rhymes - YouTube Automation` folder. Use this account when manually inspecting Drive, rather than the browser's default Google account. Keep the existing `DRIVE_TOKEN_JSON` and `DRIVE_FOLDER_ID` secrets.

## Behavior

The original landscape MP4 is a Page video; the 40-second portrait Short is a Facebook Reel. No new models or media generation. Facebook uses the same frozen publication target saved in the YouTube checkpoint. Scheduled Page content becomes public at release; this is not personal-profile posting. The Reel is explicitly disclosed as AI-generated; Page video descriptions disclose AI-generated music and illustrations.

The Facebook jobs use the existing private Drive store for `facebook/SONG_RUN_ID/video/state.json` and `facebook/SONG_RUN_ID/short/state.json`. Keys are separate from YouTube checkpoints. A file hash, Page ID, media type, metadata, schedule and returned video/session IDs are frozen before publication. Retrying reads the same ID; an initialization with a lost response stops for reconciliation rather than creating a duplicate. API error messages show only HTTP/error codes, not response bodies, URLs or tokens.

A publishing failure can be resumed through **Publish existing episode to Facebook** without restarting models or writing to YouTube. Select `kind=video` and the original generation `source_run`, or `kind=short` and the run containing its `rhyme-short` artifact. The original song `run_id` must match. This recovery currently supports the default 0–40 second Short. Artifacts expire after seven days. Preserve or restore artifacts before retrying older episodes.

Facebook scheduling is constrained to over ten minutes and under 29 days in this integration (the stricter Reel window). Expired schedules require deliberate reconciliation; retries never silently publish early or postpone an existing scheduled item. Scheduled media is retained by the existing cleanup rules. Facebook is disabled independently of YouTube until `FACEBOOK_PUBLISH_ENABLED=true`.

## Facebook failures do not block YouTube

Automatic landscape and Reel uploads run in separate, optional jobs **after** their respective YouTube jobs succeed. The YouTube Short depends on the landscape YouTube job, never on its Facebook job. Missing Facebook tokens produce a preflight warning instead of stopping generation. Expired/revoked tokens, Facebook API errors, upload failures and Facebook job timeouts cannot fail the YouTube publication jobs. Automatic Facebook jobs tolerate failure, show a warning/job summary where possible and preserve checkpoint artifacts (`facebook-publication-GITHUB_RUN_ID-video` or `-short`) and private Drive state for recovery. Shared Drive or YouTube credential errors still fail the affected YouTube jobs normally.

The Facebook-only manual recovery workflow intentionally reports failures normally. Retry that workflow after renewing Facebook authorization; it does not regenerate media or write to YouTube. Automatic and manual Facebook jobs share a lock per media kind, separate from YouTube locks, so a slow Facebook request does not hold up the next YouTube publication. Facebook reads its own copy of the original workflow artifact, so Drive media cleanup does not remove its upload source.

## Verification and limits

Run `python -m unittest -v` and `actionlint -shellcheck= -pyflakes=`. Mocked tests cover Page identity, schedule windows, AI disclosure, per-chunk transfer, retry ID reuse, response-loss duplicate prevention, invalid upload hosts and credential-safe diagnostics. These do not prove actual Meta account eligibility, token permissions, upload acceptance or schedule readback; those require the authorized live test.

Official API references used:

- [Page video upload and schedule parameters](https://developers.facebook.com/docs/graph-api/reference/page/videos/)
- [Video API publishing requirements](https://developers.facebook.com/documentation/video-api/guides/publishing)
- [Reel publishing and schedule parameters](https://developers.facebook.com/documentation/video-api/guides/reels-publishing)

The implementation uses Graph API `v26.0`, as shown in Meta's current reference when this integration was prepared. Review Meta's API-version lifecycle before upgrading.


## Facebook feed format

New landscape episode uploads are exported as **1080×1350 (4:5)** using a direct center crop before Facebook upload. There is no blurred background or padding. The center remains visible and the sides are cropped; source audio and duration are retained. YouTube video and 9:16 Reel media are unchanged.

The exact cropped MP4 is saved under the episode's private Facebook storage key before upload, so a retry resumes the same media bytes and Facebook video ID. Existing landscape upload checkpoints keep their original media rather than switching format mid-upload. The export is enabled for new Facebook publications launched from this version of the workflow.
