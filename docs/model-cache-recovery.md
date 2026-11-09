# Model download failures and cache design — 2026-11-09

Run 42574913015 successfully completed lyrics, long music and Shorts music. Seven
image/portrait shards failed during character-layer preparation, preventing the
final render. The inspected failures are HTTP 504 from BiRefNet's rembg release
asset and from LaMa's TorchScript release asset. Image generation had already
completed; repeatedly restarting entire generations does not address these URLs.

## Download and inference changes

The motion downloader uses four bounded attempts, alternating the publisher's
release URL and its official GitHub asset API. Downloads go to temporary files;
only complete, verified weights replace the destination. BiRefNet retains rembg
2.0.67's MD5 and published asset size. LaMa is checked against SHA-256
`7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c`
and its 205803670-byte size. That digest was computed from the publisher's actual
v0.1.0 GitHub asset, not inferred from a similarly named third-party model.
Both real files were downloaded and verified locally during this fix.

`character_motion.py` uses those files directly. rembg's `U2NET_HOME` points to
the verified BiRefNet directory; LaMa loads the same verified TorchScript file.
No model substitution or animation downgrade is used for network failures.

## Persistent caches

The production workflow prepares four model-family caches before launching
inference. Each worker restores only its own families, sharing one image cache
between all landscape and portrait shards and one music cache between long and
Shorts music. The cache is explicitly saved immediately after download, before
subsequent image generation, animation or publication can fail.

Keys contain the model family and the exact pinned repository revision, component
selection or asset checksums. They contain no run IDs or shard numbers and use
no broad restore prefixes. All cache paths are narrow `.models/` subdirectories;
credentials, OAuth tokens, generated songs and user media are not cached.
Lyrics checksum verification still runs. SSD-1B remains float32 at runtime with
the existing model revision; only its required Diffusers components are fetched,
excluding alternate fp16 files and redundant monolithic exports. Model data,
not an entire virtual environment, is cached.

Cache misses still download public weights. The standalone **Verify and warm
pinned model caches** workflow populates caches and performs real BiRefNet and
LaMa CPU inference. Production, manual Shorts and inference preview/check
workflows share the same cache action. The source-build fallback for the pinned
llama-cpp-python wheel also avoids the earlier GitHub release outage. Existing
bounded runner package installation and the pip no-cache teardown fix are
retained to prevent unrelated setup failures.

## Storage limits

The required uncompressed weights total approximately 18 GB: SSD-1B about 8.9 GB,
ACE-Step components about 6.3 GB, Qwen GGUF about 2.5 GB, motion about 0.43 GB.
GitHub compresses cache archives; actual saved usage appears in the warmup logs.
Do not assume all families fit in the default 10 GB repository quota. GitHub can
evict older caches on quota pressure or after seven days without access. The
application correctly repairs cache misses, but permanent no-redownload behavior
requires sufficient repository cache capacity. Increasing the quota above 10 GB
can incur charges; this change does not enable paid storage or change billing.

## Primary sources

- [rembg 2.0.67 BiRefNet source and checksum](https://github.com/danielgatis/rembg/blob/v2.0.67/rembg/sessions/birefnet_general_lite.py)
- [LaMa publisher's v0.1.0 release](https://github.com/enesmsahin/simple-lama-inpainting/releases/tag/v0.1.0)
- [LaMa publisher's loader](https://github.com/enesmsahin/simple-lama-inpainting/blob/main/simple_lama_inpainting/models/model.py)
- [GitHub cache restore/save semantics and quota](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [GitHub explicit cache-save action](https://github.com/actions/cache/blob/main/save/README.md)
- [Hugging Face download/cache behavior](https://huggingface.co/docs/huggingface_hub/main/guides/download)
