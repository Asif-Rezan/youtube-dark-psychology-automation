# Grow with Rezan Facebook publishing

Destination: https://www.facebook.com/grow.with.rezan/ (Page ID `301624356367343`). Meta app: Rezan Video Automation (`1768108484480464`).

The daily workflow completes YouTube upload, HD verification and scheduled publishing first. Facebook runs in a **separate workflow**, triggered only after successful daily completion. A Facebook failure cannot change the completed YouTube workflow or its publication settings. Facebook uses the same saved 06:00 America/New_York schedule.

The final MP4 stays in private Drive storage until Facebook confirms the correct Page, video, processing and schedule. Other disposable assets can be cleaned normally. Facebook stores its own durable checkpoint in `runs/daily-ID/facebook.json`; it never edits YouTube state or calls YouTube. Resume through **Facebook Page upload**, entering the original `daily-ID`. Resume never regenerates video or reinserts a YouTube video. An initialization with a lost response stops for reconciliation instead of creating a duplicate.

The required repository secret is `FACEBOOK_PAGE_ACCESS_TOKEN`. Use the published production app, extend the administrator's user token, then derive the Page token for this exact Page and verify **Type Page**, **Valid True**, **Expires Never** in Meta's debugger. Do not save an hour-long user token as the publishing secret. App production status and token expiry are separate properties. Meta can revoke authorization after account/security/permission changes, and may show a separate data-access expiry requiring renewed login; record and monitor that date. Never commit tokens or print API response bodies.

The source upload uses the existing private Drive token and folder. For an older run whose MP4 was already cleaned, restore its original MP4 under `runs/daily-ID/video.mp4` before running Facebook recovery. Local recovery can use `facebook_publish.py --run-id daily-ID --source /path/to/original.mp4` with the same private storage credentials.

References: [Page video parameters](https://developers.facebook.com/docs/graph-api/reference/page/videos/), [video reference](https://developers.facebook.com/docs/graph-api/reference/video/), [token lifetime](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/). Graph API version: v26.0.

## Production connection verified October 30, 2026

The app is Published. The Grow with Rezan Page token was verified as Type Page, Page ID `301624356367343`, Valid True, Expires Never, then saved in this repository’s `FACEBOOK_PAGE_ACCESS_TOKEN` secret. Meta separately reports data-access expiry `1801113741` (January 28, 2027 UTC); the Facebook workflow warns within 14 days of that date. Renew the Page authorization if Meta requires it.

For a known upload whose checkpoint was lost, the Facebook workflow accepts an optional existing Facebook video ID. It checks Page identity, exact title/description, duration, processing and the saved YouTube schedule before saving a reconciled checkpoint. It never creates another video during reconciliation.
