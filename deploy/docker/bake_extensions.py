"""Pre-compile pylate/ColBERT CUDA extensions at BUILD time.

The extractor job JIT-compiles decompress_residuals_cpp / packbits_cpp on the
FIRST entity-linking call of every cold run (~84s, the single biggest fixed NLP
cost). nvcc compilation is CPU-side, so we do it here at `docker build` time —
no GPU needed, as long as TORCH_CUDA_ARCH_LIST targets the runtime GPU (L4 =
sm_89). The compiled .so lands in TORCH_EXTENSIONS_DIR and is baked into the
image; the runtime then loads it from cache and skips the compile (and no
longer needs nvcc, enabling a slim runtime base).

Fails the build if nothing compiled — better a failed build than a runtime
image that silently re-compiles (and, on the slim base, can't).
"""
import glob
import os
import sys

os.environ.setdefault("TORCH_CUDA_ARCH_LIST", "8.9")  # L4
EXT_DIR = os.environ.get("TORCH_EXTENSIONS_DIR", os.path.expanduser("~/.cache/torch_extensions"))
os.makedirs(EXT_DIR, exist_ok=True)

# Preferred path: pylate's own loader (robust to source-file naming).
try:
    from pylate.indexes.stanford_nlp.indexing.codecs.residual import ResidualCodec

    ResidualCodec.try_load_torch_extensions(use_gpu=True)
    print("BAKE: pylate try_load_torch_extensions ran")
except Exception as e:  # noqa: BLE001
    print(f"BAKE: pylate loader path failed ({e!r}); trying direct compile")

# Fallback / belt-and-braces: force-compile the two known extensions directly.
try:
    import pylate.indexes.stanford_nlp.indexing.codecs.residual as r
    from torch.utils.cpp_extension import load

    base = os.path.dirname(r.__file__)
    for stem in ("decompress_residuals", "packbits"):
        srcs = [p for p in (f"{base}/{stem}.cpp", f"{base}/{stem}.cu") if os.path.exists(p)]
        if not srcs:
            print(f"BAKE: no sources for {stem}, skipping")
            continue
        try:
            load(name=f"{stem}_cpp", sources=srcs, verbose=True)
            print(f"BAKE: compiled {stem}_cpp")
        except Exception as e:  # noqa: BLE001
            # load() compiles before it imports; the .so is written even if the
            # GPU-less import step raises. Tolerate that — we verify .so below.
            print(f"BAKE: {stem}_cpp load raised post-compile (ok if .so exists): {e!r}")
except Exception as e:  # noqa: BLE001
    print(f"BAKE: direct compile path errored: {e!r}")

sos = glob.glob(os.path.join(EXT_DIR, "**", "*.so"), recursive=True)
print(f"BAKE: {len(sos)} compiled extension(s) in {EXT_DIR}:")
for s in sos:
    print("   ", s)
if not sos:
    sys.exit("BAKE FAILED: no .so produced — do NOT ship a slim runtime image")
print("BAKE OK")
