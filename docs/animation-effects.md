# Episode animation effects

The approved animation set includes tummy wiggle, gentle jelly bounce, clap/step, penguin movement, floating balloons, glowing fireflies, ripple hops and bubbles. The existing wave, waist, step, sway and hop variants remain available. Scene lyrics select explicit actions; otherwise each scene receives a repeatable variant.

The original sky/foliage/grass motion, bounded camera zoom/pan, character approach/rest actions and story props remain. Landscape episodes and portrait Shorts use the same animation engine.

Smile/blink deformation, head/ear warping, peekaboo, follow-the-leader and spinning are disabled. The upper 65% of each cropped character is retained during body deformation, and dancers are not stretched or rotated as a whole. Balloons, fireflies and ripple hops retain the original sprite pixels before compositing.

Animation cache versions invalidate old rendered clips while preserving existing segmentation and background layers. These effects apply to new generation runs using the updated code; already uploaded videos and in-progress runs pinned to an older commit are unchanged.
