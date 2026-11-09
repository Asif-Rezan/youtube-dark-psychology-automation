# Scene stories

New episodes feature children and friendly animal companions with consistent
clothing, colors and appearances in the episode outline. Each five-second shot
has ordered beats: blink, incoming object, notice, action and final reaction.
Rabbit/jumping shots contain two hop arcs. Ball, rain and bedtime scenes use
approach, sway and settling actions instead. The camera pushes closer at the end.

`scene_actions.py` selects actions from the literal scene and lyric. Substantial
disjoint silhouettes animate separately, with staggered reactions. Touching
characters remain one group; this is a CPU 2D puppet renderer, not a full 3D rig.
A conservative eye-pair detector enables blinking, a small head warp and cheek
lift only when there is one unambiguous pair. These are approximations of a head
turn and happy expression, not newly generated side-view or smiling poses.
Uncertain faces retain the source art. Clip manifests record the story plan,
actor count and detected face rigs. Invalid foreground extraction retains the
existing camera-only fallback and records the reason.

Changing `.generation/scene-story-request.json` on main explicitly starts a new
10-minute episode using the full pipeline, including independent Shorts music,
portrait images and configured scheduled publication. Publication still follows
`PUBLISH_ENABLED` and optional Facebook settings. Normal scheduled/manual runs
use the same scene renderer. Cache versions invalidate previous motion clips.

Run 41316394479 started before that correction and is generation-only. Its exact
successful completion is watched by `complete-scene-story.yml`, which reuses its
finished video, restores configured scheduled publication and generates the
missing Short. Other runs cannot trigger that one-episode continuation. Failed
source runs never publish. The long video/music/images are not regenerated.

## Camera, environment and independent cast motion

The v2 scene renderer adds a continuous gentle camera push and pan. Camera
framing is limited by the whole cast's bounds in landscape and portrait shots.
The cleaned background has small sky parallax and foliage/grass sway, while
character layers keep their own motion. This is a lightweight 2D background
mesh, not a generated video or semantic simulation of individual plants.

Disjoint characters get independent sway, hop and nod profiles, phases and
reaction delays. Each remains anchored in its own space; cast members no longer
all slide together. Smaller companions are retained and edge pixels have a
single owner to avoid duplicate silhouettes. The image prompt asks for space
between full-body characters. Touching or overlapping silhouettes still remain
a group rather than being cut at guessed body boundaries.

`demos/motion-improvements/render.py` renders a 15-second review reel from saved
real episode layers: two landscape characters, two portrait characters and a
single-character landscape. It checks decoding/duration and records frame/render
timings in `validation.json`. The motion check workflow repeats these checks on
GitHub without generating new music/images or publishing a video. The saved scene layers are retained under
`demos/motion-improvements/assets` with source provenance and SHA-256 hashes, so
the visual checks do not depend on expiring workflow artifacts.
