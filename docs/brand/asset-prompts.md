# Reference character assets

Created with the built-in ImageGen tool on 2026-11-22. The user supplied the
reference thumbnail in this chat. Character reference role: identity and style;
remove its original typography, banner, background and pointer. No API key or
external paid runtime was added to the repository.

## Transparent character prompt

Use case: background-extraction / identity-preserve. Create a clean reusable transparent PNG character asset from the provided thumbnail. Extract ONLY the exact centered illustrated mascot: indigo blue hooded cloak, white bandage-wrapped round face with a single large blue eye in a black eye opening, white bandaged raised hand with index finger in a shushing gesture. Preserve its exact distinctive design, colors, proportions, flat cel shaded thick black outlines and shushing pose. Show the entire hood, shoulders, torso and hand with a clean straight lower torso edge, matching the visible character from the reference, without cropping hood or hands. Center it large with a small transparent margin. Remove EVERYTHING else: all lettering, red/black backdrop, yellow arrow, banners. Absolutely no text, no arrow, no watermark. True transparent background; no checkerboard drawn into artwork.

Output: `assets/brand/hooded-eye.png`, RGBA with real transparency.

## Example backdrop prompt

Use case: ads-marketing. Asset type: 16:9 YouTube thumbnail background plate for a Dark Psychology channel. Make a dark crimson red and near-black grunge textured background in the flat graphic illustration style of psychological mystery thumbnails. Black vignette edges, red glow in the middle, bold charcoal scratches. On the far RIGHT side, one large symbolic white broken puppet string hanging from a shadowy controlling hand, simple clean readable silhouette. Keep the CENTER empty for a separately composited indigo hooded eye character, the TOP QUARTER clear for headline typography, and BOTTOM 15 percent clear for a black footer. NO text, NO typography, NO letters, NO mascot, NO faces, NO logo. Strong simple graphic shapes, moody high contrast, minimal clutter, landscape 16:9.

Output: `docs/brand/example-backdrop.png`. This is a design example only.
The code adds exact typography, mascot, arrow and footer to the preview.
Production creates a fresh topic-specific background using `complete_thumbnail_prompt`.
