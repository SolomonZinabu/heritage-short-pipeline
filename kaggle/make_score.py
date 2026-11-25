#!/usr/bin/env python3
"""Make the score candidates of a film with ACE-Step 1.5.

This runs on Kaggle, on a free GPU, and not on the film-maker's machine.
``python -m pipeline music`` writes the job, and ``python -m pipeline music
import`` brings the results back.

    python make_score.py job.json            sets everything up, then runs the job
    python make_score.py job.json --inner    the job itself, inside that setup

Every call is written to ``runs.jsonl`` in the same form as the pipeline's own
log, so the two can be merged. The audio, the log and a manifest are packed
into ``score.zip`` next to the job file.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
import wave
from pathlib import Path

REPO = "https://github.com/ACE-STEP/ACE-Step-1.5.git"
# Large scratch space. Only the results go into the folder Kaggle keeps.
SCRATCH = Path(os.environ.get("HERITAGE_SCRATCH", "/kaggle/tmp/heritage-score"))


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


def gpu_name() -> str:
    try:
        shown = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        return shown.splitlines()[0] if shown else ""
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return ""


def check(command: list[str], note: Progress, **options) -> int:
    """Run a setup command with its output shown, and note how it ended."""
    note("running: " + " ".join(str(part) for part in command[:6]))
    code = subprocess.run(command, **options).returncode
    note(f"exit code {code}")
    return code


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def accepted(callable_thing, **options) -> dict:
    """Keep only the options this version of the library accepts.

    Some names have moved between versions. For those, both spellings are
    offered here and only the accepted one is kept.
    """
    names = inspect.signature(callable_thing).parameters
    kept = {name: value for name, value in options.items() if name in names}
    if "keyscale" in kept and "key_scale" in kept:
        del kept["key_scale"]
    if "duration" in kept and "audio_duration" in kept:
        del kept["audio_duration"]
    return kept


def write_wav(path: Path, tensor, sample_rate: int) -> tuple[float, int]:
    """Write the model's audio, shaped [channels, samples], as a 16-bit WAV.

    Only the standard library and torch are used, so nothing else has to be
    installed. Returns the length in seconds and the number of channels.
    """
    import torch

    if tensor.dim() == 1:
        tensor = tensor[None]
    channels = int(tensor.shape[0])
    frames = tensor.T.clamp(-1, 1).mul(32767).to(torch.int16).cpu().numpy().tobytes()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(frames)
    return tensor.shape[1] / sample_rate, channels


def run_job(job: dict, out_dir: Path, note: Progress) -> int:
    """Make every candidate in the job, one call each, and log every call."""
    import torch
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    session_file = out_dir / "session.json"
    session = json.loads(session_file.read_text(encoding="utf-8")) if session_file.exists() else {"started_at": time.time()}
    log_file = out_dir / "runs.jsonl"
    made_already = set()
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("status") == "ok":
                made_already.add(json.loads(line).get("target"))

    say(f"Python {platform.python_version()}, torch {torch.__version__}, CUDA {torch.version.cuda}")
    if not torch.cuda.is_available():
        note("STOPPED: no GPU is visible. Switch the notebook's accelerator on.")
        return 2
    gpu = torch.cuda.get_device_name(0)
    say(f"GPU: {gpu}")
    # The names the library accepts, printed so that a mismatch can be seen at once.
    for thing in (AceStepHandler.initialize_service, GenerationParams, GenerationConfig, generate_music):
        say(f"{getattr(thing, '__name__', thing)}{inspect.signature(thing)}")

    handler = AceStepHandler()
    handler.initialize_service(
        **accepted(AceStepHandler.initialize_service, project_root=os.getcwd(), config_path=job["tasks"][0]["model"], device="cuda")
    )
    # Not started: the score is made by the music model alone, from an exact caption.
    llm = LLMHandler()

    results, failures = [], 0
    for task in job["tasks"]:
        target = out_dir / task["file"]
        if task["id"] in made_already and target.exists():
            say(f"{task['id']} was made in an earlier run, skipping it")
            results.append({"id": task["id"], "file": task["file"], "task": task})
            continue
        parameters = accepted(
            GenerationParams,
            caption=task["caption"],
            lyrics=job.get("lyrics", "[Instrumental]"),
            bpm=task["bpm"],
            keyscale=task["music_key"],
            key_scale=task["music_key"],
            duration=int(task["duration_seconds"]),
            audio_duration=int(task["duration_seconds"]),
            thinking=False,
            inference_steps=int(task["steps"]),
            shift=float(task["shift"]),
        )
        params = GenerationParams(**parameters)
        config = GenerationConfig(
            **accepted(GenerationConfig, batch_size=1, seeds=[task["seed"]], use_random_seed=False, audio_format="wav")
        )

        record = {
            "call_id": str(uuid.uuid4()),
            "stage": "music",
            "target": task["id"],
            "model": task["model"],
            "parameters": parameters,
            "seed": task["seed"],
            "attempt": 1,
            "status": "ok",
            "error": None,
            "cost": 0.0,
            "cost_basis": "free GPU quota on Kaggle",
            "place": "kaggle",
            "gpu": gpu,
        }
        say(f"{task['id']}: making {task['duration_seconds']:g}s of music with seed {task['seed']}")
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        try:
            result = generate_music(handler, llm, params, config)
            audio = result.audios[0]
            seconds, channels = write_wav(target, audio["tensor"], int(audio["sample_rate"]))
            record.update(
                output=task["file"],
                output_seconds=round(seconds, 3),
                output_sha256=sha256(target),
                sample_rate=int(audio["sample_rate"]),
                channels=channels,
            )
            results.append({"id": task["id"], "file": task["file"], "task": task, "seconds": round(seconds, 3)})
            say(f"{task['id']}: done, {seconds:.1f}s of music in {time.perf_counter() - started:.0f}s")
        except Exception as exc:  # logged, then the next candidate is tried
            failures += 1
            record["status"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"[:800]
            note(f"{task['id']} FAILED: {record['error']}")
        record["latency_seconds"] = round(time.perf_counter() - started, 3)
        record["gpu_peak_memory_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
        with log_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    session_seconds = round(time.time() - float(session.get("started_at", time.time())))
    manifest = {"gpu": gpu, "session_seconds": session_seconds, "results": results, "tasks": job["tasks"]}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    note(
        f"finished: {len(results)} of {len(job['tasks'])} candidate(s), {failures} failed, "
        f"about {session_seconds / 60:.0f} minutes on the GPU"
    )
    return 1 if failures else 0


def pack(out_dir: Path) -> Path:
    """One file to download, holding the audio, the log and the manifest."""
    return Path(shutil.make_archive(str(out_dir.with_suffix("")), "zip", root_dir=out_dir.parent, base_dir=out_dir.name))


def setup(job: dict, job_file: Path, out_dir: Path, note: Progress) -> int:
    """Install the model in a private environment, then run the job inside it."""
    say(f"Python {platform.python_version()} on {platform.system()}")
    session_file = out_dir / "session.json"
    if not session_file.exists():
        session_file.write_text(json.dumps({"started_at": time.time(), "gpu": gpu_name()}))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    repo = SCRATCH / "ACE-Step-1.5"
    if not (repo / ".git").exists():
        note("downloading the ACE-Step code")
        if check(["git", "clone", "--depth", "1", REPO, str(repo)], note):
            note("STOPPED: could not download the code")
            return 2
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(repo / ".venv")
    env["UV_CACHE_DIR"] = str(SCRATCH / "uv-cache")
    # ACE-Step ships ready-made parts for Python 3.11 only.
    env["UV_PYTHON"] = "3.11"
    env["ACESTEP_CHECKPOINTS_DIR"] = str(SCRATCH / "checkpoints")
    env["HF_HOME"] = str(SCRATCH / "hf-cache")
    python = repo / ".venv" / "bin" / "python"
    if not python.exists():
        if shutil.which("uv") is None:
            note("installing uv")
            if check([sys.executable, "-m", "pip", "install", "-q", "uv"], note):
                note("STOPPED: could not install uv")
                return 2
        note("installing ACE-Step and its own PyTorch build. Several GB; this takes a while")
        if check(["uv", "sync"], note, cwd=repo, env=env):
            note("STOPPED: the installation failed")
            return 2
    note("running the job")
    code = subprocess.run(
        [str(python), str(Path(__file__).resolve()), str(job_file.resolve()), "--inner"],
        cwd=repo, env=env,
    ).returncode
    note(f"the job ended with code {code}")
    return code


def main() -> int:
    if len(sys.argv) < 2:
        say(__doc__)
        return 2
    job_file = Path(sys.argv[1]).resolve()
    job = json.loads(job_file.read_text(encoding="utf-8"))
    out_dir = job_file.parent / "score"
    out_dir.mkdir(parents=True, exist_ok=True)
    note = Progress(out_dir / "progress.log")
    inner = "--inner" in sys.argv
    code = run_job(job, out_dir, note) if inner else setup(job, job_file, out_dir, note)
    if not inner:
        say(f"Everything is packed in {pack(out_dir)}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
