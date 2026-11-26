#!/usr/bin/env python3
"""Make moving shots with Wan 2.2 TI2V-5B, which turns a picture into a short clip.

This runs on Kaggle, on a free GPU, and not on the film-maker's machine.
``python -m pipeline shots`` writes the job, and ``python -m pipeline shots
import`` brings the results back.

    python make_shots.py job.json            sets everything up, then runs the job
    python make_shots.py job.json --inner    the job itself, inside that setup

The model's own code is written for a GPU with 24 GB and for bfloat16 numbers.
Kaggle's free T4 has 16 GB and no bfloat16. So, in the private copy that this
job makes on Kaggle, and nowhere else:

- the picture model runs in float16;
- its weight files are converted to float16 first, and it is loaded straight
  into float16, so that the machine's memory is enough to hold them;
- the part that decodes pictures waits in the machine's memory while the
  picture model works;
- only the image-to-video pipeline is loaded. The package's own start-up
  imports four other pipelines, each with libraries of its own.

Every call is written to ``runs.jsonl`` in the same form as the pipeline's own
log, so the two can be merged. The clips, the logs and a manifest are packed
into ``clips.zip`` next to the job file.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

REPO = "https://github.com/Wan-Video/Wan2.2.git"
WEIGHTS = "Wan-AI/Wan2.2-TI2V-5B"
# Large scratch space. Only the results go into the folder Kaggle keeps.
SCRATCH = Path(os.environ.get("HERITAGE_SCRATCH", "/kaggle/tmp/heritage-shots"))
# Each is: a file of the model's code, the line as written, and the line as this job needs it.
# The first two change the picture model's number format from bfloat16 to float16.
FORMAT_PATCHES = (
    ("wan/configs/shared_config.py", "wan_shared_cfg.param_dtype = torch.bfloat16", "wan_shared_cfg.param_dtype = torch.float16"),
    ("wan/modules/attention.py", "dtype=torch.bfloat16,", "dtype=torch.float16,"),
)
# The third loads the picture model straight into its number format, whichever runs.
LOAD_PATCH = ("wan/textimage2video.py", "WanModel.from_pretrained(checkpoint_dir)", "WanModel.from_pretrained(checkpoint_dir, torch_dtype=self.param_dtype)")


def say(message: str) -> None:
    print(message, flush=True)


class Progress:
    """A log beside the results, so that a failure can still be read after the page is closed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(f"{stamp} {message}\n")
        say(f"[{stamp}] {message}")


def machine_memory() -> str:
    """What the machine has, as a line for the log."""
    parts = []
    try:
        rows = subprocess.run(["free", "-g"], capture_output=True, text=True, timeout=20).stdout.splitlines()[1:]
        for row in rows:
            fields = row.split()
            if fields and fields[0] == "Mem:" and len(fields) > 1:
                parts.append(f"{fields[1]} GB of memory in all")
        gpus = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        if gpus:
            parts.append("GPU " + gpus.replace("\n", "; "))
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass
    return ", ".join(parts) or "the machine's memory is not known"


def clean_environment() -> dict[str, str]:
    """The notebook's settings for its own Python, left out of the job's environment.

    Kaggle's notebook runs one Python and tells the programs it starts how it
    likes its plots, through ``MPLBACKEND``. The job runs in another Python,
    where that plotting backend may not exist.
    """
    env = dict(os.environ)
    for name in ("MPLBACKEND", "PYTHONPATH", "PYTHONUSERBASE", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV"):
        env.pop(name, None)
    env["MPLBACKEND"] = "Agg"  # plotting without a screen, for whatever library imports it
    return env


def check(command: list[str], note: Progress, **options) -> int:
    """Run a setup command with its output shown, and note how it ended."""
    note("running: " + " ".join(str(part) for part in command[:8]))
    code = subprocess.run(command, **options).returncode
    note(f"exit code {code}")
    return code


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class MemoryWatch(threading.Thread):
    """The most GPU memory used while the model works, read from the GPU's own meter."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak_gb = 0.0
        self.watching = False
        self.start()

    def run(self) -> None:
        while True:
            if self.watching:
                try:
                    shown = subprocess.run(
                        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=10,
                    ).stdout.strip()
                    used = [float(value) for value in shown.splitlines() if value.strip()]
                    if used:
                        self.peak_gb = max(self.peak_gb, used[0] / 1024)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass
            time.sleep(2)

    def reset(self) -> None:
        self.peak_gb = 0.0
        self.watching = True

    def stop(self) -> None:
        self.watching = False


def patch(repo: Path, note: Progress, number_format: str) -> None:
    """In the private copy on Kaggle only, set the picture model's number format and load it straight into it.

    ``number_format`` is "float16" or "bfloat16". The first two lines are
    changed for float16 and put back for bfloat16, which is how the model is
    written. The third line is kept either way.
    """
    if number_format == "float16":
        changes = [*FORMAT_PATCHES, LOAD_PATCH]
    else:
        # The same lines, the other way round: what float16 changed is put back.
        changes = [(relative, needed, written) for relative, written, needed in FORMAT_PATCHES]
        changes.append(LOAD_PATCH)
    for relative, written, needed in changes:
        path = repo / relative
        text = path.read_text(encoding="utf-8")
        if needed in text:
            note(f"{relative}: already set for {number_format}")
            continue
        if written not in text:
            raise SystemExit(f"STOPPED: {relative} does not hold the line this job patches: {written}")
        path.write_text(text.replace(written, needed), encoding="utf-8")
        note(f"{relative}: set for {number_format}")


def convert_to_float16(weights: Path, note: Progress) -> None:
    """The picture model's weight files, written again in float16, one file at a time.

    They are published in float32, 20 GB. Loaded as they are, they would not
    fit in the machine's memory next to the text encoder.
    """
    from safetensors.torch import load_file, save_file
    import torch

    for shard in sorted(weights.glob("diffusion_pytorch_model-*-of-*.safetensors")):
        if shard.with_suffix(".fp16").exists():
            note(f"{shard.name}: already in float16")
            continue
        note(f"{shard.name}: converting to float16, {shard.stat().st_size / 2**30:.1f} GB")
        state = load_file(str(shard))
        changed = shard.with_name(shard.name + ".tmp")
        save_file({name: value.to(torch.float16).clone() for name, value in state.items()}, str(changed), metadata={"format": "pt"})
        del state
        changed.replace(shard)
        shard.with_suffix(".fp16").touch()
        note(f"{shard.name}: now {shard.stat().st_size / 2**30:.1f} GB")


def run_job(job: dict, out_dir: Path, note: Progress) -> int:
    """Make every clip in the job, one call each, and log every call."""
    import logging
    import types

    repo, weights, images = (Path(os.environ[name]) for name in ("HERITAGE_REPO", "HERITAGE_WEIGHTS", "HERITAGE_IMAGES"))
    number_format = os.environ.get("HERITAGE_NUMBER_FORMAT", "float16")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    patch(repo, note, number_format)

    import torch
    import torchvision
    import diffusers
    import transformers

    note(
        f"Python {platform.python_version()}, torch {torch.__version__}, torchvision {torchvision.__version__}, "
        f"diffusers {diffusers.__version__}, transformers {transformers.__version__}, CUDA {torch.version.cuda}; {machine_memory()}"
    )
    if not torch.cuda.is_available():
        note("STOPPED: no GPU is visible. Switch the notebook's accelerator on.")
        return 2
    gpu = torch.cuda.get_device_name(0)
    note(f"GPU: {gpu}; bfloat16 supported: {torch.cuda.is_bf16_supported()}; compute capability {torch.cuda.get_device_capability(0)}")
    convert_to_float16(weights, note)

    # The package's own start-up imports four other pipelines, each with libraries of its own.
    # A bare package with the same name loads only what this job needs.
    stub = types.ModuleType("wan")
    stub.__path__ = [str(repo / "wan")]
    sys.modules["wan"] = stub
    from PIL import Image
    from wan.configs import MAX_AREA_CONFIGS, SIZE_CONFIGS, WAN_CONFIGS
    from wan.textimage2video import WanTI2V
    from wan.utils.utils import save_video

    # Tesla T4 (compute capability 7.5): FlashAttention-2 needs sm80+, so
    # flash_attn is not installed and model.py's direct flash_attention call
    # asserts at the first denoise step. attention.py ships no named SDPA
    # function - the fallback lives inline in its attention() dispatcher -
    # so re-implement that exact fallback here (scaled_dot_product_attention
    # with the packed varlen tensors flattened to a plain [B, L] batch) and
    # bind model.py's direct call sites to it. No-op when flash is present.
    import wan.modules.attention as _wan_attention
    import wan.modules.model as _wan_model
    if not getattr(_wan_attention, "FLASH_ATTN_2_AVAILABLE", False) and not getattr(_wan_attention, "FLASH_ATTN_3_AVAILABLE", False):
        import torch as _torch

        def _sdpa_attention(q, k, v, q_lens=None, k_lens=None, dropout_p=0.0,
                             softmax_scale=None, q_scale=None, causal=False,
                             window_size=(-1, -1), deterministic=False,
                             dtype=_torch.bfloat16, fa_version=None, **_ignored):
            # flash_attention packs varlen sequences into one flattened row
            # batch; SDPA wants a padded [B, heads, L, dim] layout.
            if q_lens is not None:
                import math as _math
                b = len(q_lens)
                lq = int(max(q_lens))
                q = _torch.stack([
                    _torch.nn.functional.pad(u[:n], (0, 0, 0, lq - n))
                    for u, n in zip(q, q_lens)
                ])
            else:
                b, lq = q.shape[0], q.shape[1]
                q = q.transpose(1, 2)
            if k_lens is not None:
                lk = int(max(k_lens))
                k = _torch.stack([
                    _torch.nn.functional.pad(u[:n], (0, 0, 0, lk - n))
                    for u, n in zip(k, k_lens)
                ])
                v = _torch.stack([
                    _torch.nn.functional.pad(u[:n], (0, 0, 0, lk - n))
                    for u, n in zip(v, k_lens)
                ])
            else:
                lk = k.shape[1]
                k = k.transpose(1, 2)
                v = v.transpose(1, 2)
            q = q.to(dtype); k = k.to(dtype); v = v.to(dtype)
            if q_scale is not None:
                q = q * q_scale
            # Padded rows attend only within their own sequence.
            attn_mask = None
            if q_lens is not None:
                device = q.device
                ar = _torch.arange(lq, device=device)[None, :] < _torch.tensor(list(map(int, q_lens)), device=device)[:, None]
                attn_mask = ar[:, None, None, :].to(q.dtype) * 0.0
                arange_k = _torch.arange(lk, device=device)
                valid_k = arange_k[None, :] < _torch.tensor(list(map(int, k_lens)), device=device)[:, None]
                joint = ar[:, :, None] & valid_k[:, None, :]
                attn_mask = _torch.where(joint, 0.0, float("-inf")).to(q.dtype)[:, None, :, :]
            out = _torch.nn.functional.scaled_dot_product_attention(
                q, k, v, attn_mask=attn_mask, is_causal=causal, dropout_p=dropout_p)
            out = out.transpose(1, 2).contiguous()
            # Unpack back to the flattened varlen layout the caller expects.
            if q_lens is not None:
                out = _torch.cat([u[:n] for u, n in zip(out, q_lens)])
            return out

        _wan_model.flash_attention = _sdpa_attention
        note("attention: flash_attn unavailable (T4) - model.py flash_attention routed to an SDPA fallback")
    else:
        note("attention: flash_attn available - no patch needed")

    config = WAN_CONFIGS["ti2v-5B"]
    note(f"loading the model: the picture model in {config.param_dtype}, the text encoder in {config.t5_dtype} in the machine's memory")
    started = time.perf_counter()
    pipeline = WanTI2V(config=config, checkpoint_dir=str(weights), device_id=0, rank=0, t5_cpu=True, convert_model_dtype=True)
    note(f"the model is loaded in {time.perf_counter() - started:.0f}s. {machine_memory()}")

    # While the picture model works, the part that decodes pictures waits in the machine's memory.
    model, vae, device = pipeline.model, pipeline.vae, pipeline.device
    model_to = model.to

    def to(*args, **kwargs):
        moved = model_to(*args, **kwargs)
        target = args[0] if args else kwargs.get("device")
        vae.model.to("cpu") if isinstance(target, torch.device) and target.type == "cuda" else vae.model.to(device)
        return moved

    model.to = to

    session_file = out_dir / "session.json"
    session = json.loads(session_file.read_text(encoding="utf-8")) if session_file.exists() else {"started_at": time.time()}
    log_file = out_dir / "runs.jsonl"
    made_already = set()
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("status") == "ok":
                made_already.add(json.loads(line).get("target"))

    watch = MemoryWatch()
    results, failures = [], 0
    for task in job["tasks"]:
        target = out_dir / task["file"]
        if task["id"] in made_already and target.exists():
            say(f"{task['id']} was made in an earlier run, skipping it")
            results.append({"id": task["id"], "file": task["file"], "task": task})
            continue
        frames, steps, seed = int(task["frames"]), int(task["steps"]), int(task["seed"])
        parameters = {"prompt": task["prompt"], "frames": frames, "steps": steps, "size": task["size"], "number_format": number_format}
        record = {
            "call_id": str(uuid.uuid4()),
            "stage": "shots",
            "target": task["id"],
            "model": f"{WEIGHTS} ({task['model']})",
            "parameters": parameters,
            "seed": seed,
            "attempt": 1,
            "status": "ok",
            "error": None,
            "cost": 0.0,
            "cost_basis": "free GPU quota on Kaggle",
            "place": "kaggle",
            "gpu": gpu,
        }
        note(f"{task['id']}: {frames} frames at {task['size']} in {steps} steps, seed {seed}")
        watch.reset()
        started = time.perf_counter()
        video = None
        try:
            with Image.open(images / Path(task["image"]).name) as picture:
                image = picture.convert("RGB")
            video = pipeline.generate(
                task["prompt"],
                img=image,
                size=SIZE_CONFIGS[task["size"]],
                max_area=MAX_AREA_CONFIGS[task["size"]],
                frame_num=frames,
                shift=config.sample_shift,
                sample_solver="unipc",
                sampling_steps=steps,
                guide_scale=config.sample_guide_scale,
                seed=seed,
                offload_model=True,
            )
            if video is None or video.numel() == 0:
                raise RuntimeError("the model returned no frames")
            if not bool(torch.isfinite(video).all()):
                raise RuntimeError("the clip holds values that are not numbers, which float16 can cause")
            if float(video.std()) < 0.01:
                raise RuntimeError("the clip is one flat colour, so the model produced nothing usable")
            save_video(tensor=video[None], save_file=str(target), fps=config.sample_fps, nrow=1, normalize=True, value_range=(-1, 1))
            if not target.is_file() or target.stat().st_size == 0:
                raise RuntimeError("the clip was not written")
            seconds = round(int(video.shape[1]) / config.sample_fps, 3)
            record.update(
                output=task["file"],
                output_seconds=seconds,
                output_frames=int(video.shape[1]),
                output_sha256=sha256(target),
            )
            results.append({"id": task["id"], "file": task["file"], "task": task, "seconds": seconds})
            note(f"{task['id']}: done, a clip of {seconds:.2f}s in {time.perf_counter() - started:.0f}s")
        except Exception as exc:  # logged, and the rest is not tried
            failures += 1
            record["status"] = "error"
            out_of_memory = isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in str(exc).lower()
            record["error"] = ("out of GPU memory: " if out_of_memory else "") + f"{type(exc).__name__}: {exc}"[:800]
            note(f"{task['id']} FAILED: {record['error']}")
            # Where it failed, in the model's own words. The first attempt kept only the kind of error,
            # and a bare assertion with no message could not be found.
            record["traceback"] = traceback.format_exc()[-2500:]
            note("the last lines of the error:\n" + record["traceback"][-1200:])
        watch.stop()
        record["latency_seconds"] = round(time.perf_counter() - started, 3)
        record["gpu_peak_memory_gb"] = round(watch.peak_gb, 2)
        with log_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        del video
        if record["status"] != "ok":
            note("stopped at the first failure, so that the reason can be read and the GPU time not spent for nothing")
            break

    session_seconds = round(time.time() - float(session.get("started_at", time.time())))
    manifest = {
        "gpu": gpu,
        "session_seconds": session_seconds,
        "patches_for_the_number_format": [list(item) for item in FORMAT_PATCHES],
        "patch_for_loading": list(LOAD_PATCH),
        "number_format_of_this_attempt": number_format,
        "results": results,
        "tasks": job["tasks"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    note(f"finished: {len(results)} of {len(job['tasks'])} clip(s) made, {failures} failed, about {session_seconds / 60:.0f} minutes on the GPU")
    return 1 if failures else 0


def write_images(job: dict, folder: Path) -> Path:
    """The pictures the job starts from, as files."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, encoded in job.get("images", {}).items():
        path = folder / Path(name).name
        path.write_bytes(base64.b64decode(encoded))
    return folder


def pack(out_dir: Path) -> Path:
    """One file to download, holding the clips, the logs and the manifest."""
    return Path(shutil.make_archive(str(out_dir.with_suffix("")), "zip", root_dir=out_dir.parent, base_dir=out_dir.name))


def setup(job: dict, job_file: Path, out_dir: Path, note: Progress) -> int:
    """Install the model in a private environment, then run the job inside it."""
    say(f"Python {platform.python_version()} on {platform.system()}")
    session_file = out_dir / "session.json"
    if not session_file.exists():
        session_file.write_text(json.dumps({"started_at": time.time(), "gpu": machine_memory()}))
    note(f"the machine: {machine_memory()}")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    repo = SCRATCH / "Wan2.2"
    if not (repo / ".git").exists():
        note("downloading the model's code")
        if check(["git", "clone", "--quiet", "--depth", "1", REPO, str(repo)], note):
            note("STOPPED: could not download the code")
            return 2
    note("the code is at commit " + subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip())

    env = clean_environment()
    env["UV_CACHE_DIR"] = str(SCRATCH / "uv-cache")
    env["HF_HOME"] = str(SCRATCH / "hf-cache")
    python = SCRATCH / "venv" / "bin" / "python"
    if not python.exists():
        if shutil.which("uv") is None:
            note("installing uv")
            if check([sys.executable, "-m", "pip", "install", "-q", "uv"], note):
                note("STOPPED: could not install uv")
                return 2
        note("making a private Python 3.11")
        if check(["uv", "venv", "--python", "3.11", str(SCRATCH / "venv")], note, env=env):
            note("STOPPED: could not make the private Python")
            return 2
        # Everything in one step. Two steps were tried first: the second one,
        # left unpinned, replaced PyTorch with a newer version and left its
        # vision module at the old one, and the two no longer matched.
        note("installing PyTorch, its vision module and what the model's code needs. Several GB; this takes a while")
        if check(
            ["uv", "pip", "install", "--python", str(python), "torch", "torchvision", "diffusers", "transformers==4.51.3", "accelerate", "safetensors",
             "einops", "numpy<2", "imageio", "imageio-ffmpeg", "easydict", "ftfy", "dashscope", "huggingface_hub"],
            note, env=env,
        ):
            note("STOPPED: could not install what the model's code needs")
            return 2

    weights = SCRATCH / WEIGHTS.split("/")[1]
    if not (weights / "Wan2.2_VAE.pth").exists() or not list(weights.glob("diffusion_pytorch_model-*.safetensors")):
        note("downloading the model's weights, 34 GB. This takes a while")
        downloader = SCRATCH / "download_weights.py"
        downloader.write_text(
            "import sys\nfrom huggingface_hub import snapshot_download\n"
            "snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], max_workers=4)\n",
            encoding="utf-8",
        )
        if check([str(python), str(downloader), WEIGHTS, str(weights)], note, env=env):
            note("STOPPED: could not download the weights")
            return 2

    env["HERITAGE_REPO"], env["HERITAGE_WEIGHTS"] = str(repo), str(weights)
    env["HERITAGE_IMAGES"] = str(write_images(job, job_file.parent / "images"))
    log = out_dir / "job-output.log"
    code = 1
    # The first attempt runs the picture model in float16, as changed above. If
    # it stops, the model's own number format, bfloat16, is tried for the clips
    # that are still not made. Newer PyTorch reports bfloat16 as supported on a
    # T4, so the model as written may run there after all.
    for number_format in ("float16", "bfloat16"):
        env["HERITAGE_NUMBER_FORMAT"] = number_format
        note(f"running the job with the picture model in {number_format}. Everything it prints is kept in job-output.log")
        with log.open("a" if log.exists() else "w", encoding="utf-8") as stream:
            process = subprocess.Popen(
                [str(python), str(Path(__file__).resolve()), str(job_file.resolve()), "--inner"],
                cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
            )
            for line in process.stdout:
                stream.write(line)
                if "%|" not in line and "it/s]" not in line and "s/it]" not in line:
                    say(line.rstrip()[:400])
            code = process.wait()
        note(f"the job ended with code {code}")
        if code == 0:
            break
    return code


def main() -> int:
    if len(sys.argv) < 2:
        say(__doc__)
        return 2
    job_file = Path(sys.argv[1]).resolve()
    job = json.loads(job_file.read_text(encoding="utf-8"))
    out_dir = job_file.parent / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    note = Progress(out_dir / "progress.log")
    inner = "--inner" in sys.argv
    code = run_job(job, out_dir, note) if inner else setup(job, job_file, out_dir, note)
    if not inner:
        say(f"Everything is packed in {pack(out_dir)}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
