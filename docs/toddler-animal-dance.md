# Toddler and animal dance scenes

Newly composed episodes feature one or two cute baby animal leads and a small child playmate.
The user-provided appearance reference informs round cheeks, large expressive
eyes, short soft hair and playful raised-hand poses. Production keeps the existing
colorful 3D storybook illustration style, SSD-1B revision, guidance, dimensions and
step counts. The reference photo is not uploaded or copied into the repository.

Cast descriptions specify consistent names, outfits and hair/animal colors. Early
image-prompt tokens prioritize the soft animal style, dreamy nature and child companion, so a long scene
or world description cannot push the human cast beyond the text encoder window.
The shared refrain receives its own dancing composition rather than reusing the
preceding verse composition. Verse scenes still follow their literal events.

Dance plans override incidental moon/rain palette words and use the existing
requested beat (120 BPM/.5 seconds for new scenes; 100 BPM/.6 seconds for old scenes): gentle hops, landing squash and side sway.
Each extracted actor has a different phase/delay. This remains layered puppet
animation of illustrated poses, not full 3D skeletal or physically accurate limb
animation. Touching silhouettes can still move together; prompts request a clear
gap between bodies. Other story actions, moving scenery and camera framing remain.

New cast/action versions invalidate stale animation clips. Already running Actions
use their checked-out commit and are not retroactively changed. No production
video is dispatched automatically by this change. The optional five-second
preview workflow generates one new image with production image settings, then
extracts the cast and renders/decode-checks their dance without publication.

Natural dreamy outdoor scenery stays prominent in every scene prompt: flower meadows, blossom gardens, forests, soft natural light and pastel surroundings. Studio stages and empty backdrops are excluded. Animal and child companions remain separate animation layers where segmentation permits; thin hand contacts can be separated conservatively for dance scenes.

Dance clips also apply small continuous local image deformations around the side/arm, waist and lower/leg regions. The top 28 percent of each cutout is preserved to protect heads and ears. These gentle movements preserve the original artwork; they do not infer anatomical joints or guarantee full articulated dance poses. Existing blink and hop motion remains.

Dance scenes choose a repeatable pseudorandom variant from arm wave, waist sway, alternating steps, gentle sway and hops, using the scene text and index. Only the hop variant jumps. Companions in ordinary non-hop stories no longer receive automatic hops. Re-renders use the same selection.
