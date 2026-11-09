# Image motion extraction recovery

Run 41295472841 generated scene artwork successfully, but image shards 0 and 3
failed in character_motion.py: BiRefNet foreground coverage was 0.013 and 0.020,
below the 0.025 minimum. This was a character segmentation failure, not an image
inference failure. Node 20 deprecation notices were unrelated warnings.

Invalid foreground masks still fail the layer quality checks. At clip rendering,
only InvalidForegroundMask triggers recovery: a gentle centered camera push-in
preserves the complete generated scene. Normal masks retain layered character
animation. Other errors (model loading, inpainting, source data or encoding)
remain errors rather than silently publishing damaged output.

Recovery logs a character_extraction_fallback warning and saves motion_mode and
fallback_reason in the clip JSON. FFprobe dimensions/duration and FFmpeg decoding
must pass before the output is recorded. The new renderer version invalidates
previous clip caches; source, prompt and video hashes still guard cache integrity.

Regression tests cover the two observed coverage failures, landscape and portrait
clips, changing frames, corrupted caches and failed encodes. Component checks run
these tests on every push and pull request.

Existing workflow retries use the original commit. Use a new workflow run on the
fixed main commit to pick up this fix; simply retrying the original run will still
execute its old code.
