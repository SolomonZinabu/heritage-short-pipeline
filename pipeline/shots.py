"""Stage: shots. A picture that must move is turned into a short clip with Wan 2.2 on Kaggle, on a free GPU.

The model does not run on this machine, so the stage works in three steps, like
the music stage:

1. ``python -m pipeline shots`` finds which clips already exist and, for the
   missing ones, writes a job for Kaggle: a notebook that carries the job and
   the pictures inside it.
2. On Kaggle, the notebook installs the model, makes the clips, and packs them
   with a log of every call and a manifest into ``clips.zip``.
3. ``python -m pipeline shots import clips.zip`` brings them back, and adds
   Kaggle's calls to ``runs.jsonl``.

A still asks for a clip with a ``clip_prompt``. When the clip exists, the film
shows it in place of the still, for the still's time.
"""
from __future__ import annotations

import base64
import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from . import cache, ffmpeg
from .config import OUTPUTS, ROOT, RUNS
from .runlog import log_model_call
from .util import say

STAGE = "shots"
SCRIPT = ROOT / "kaggle" / "make_shots.py"
JOBS = OUTPUTS / "_jobs" / "shots"
CLIPS = OUTPUTS / "shots"
# The two shapes Wan 2.2's image-to-video model makes. Each is width times height.
LANDSCAPE, PORTRAIT = "1280*704", "704*1280"


def task_for(still: dict[str, Any], label: str, seed: int, settings: dict[str, Any]) -> dict[str, Any]:
    """Everything that decides one clip, so that the same clip is found again by the same inputs."""
    from PIL import Image

    source = ROOT / still["file"]
    with Image.open(source) as picture:
        width, height = picture.size
    task = {
        "id": label,
        "model": settings["shots"]["model"],
        "image": still["file"],
        "image_sha256": cache.file_hash(source),
        "prompt": still["clip_prompt"],
        "frames": int(still.get("clip_frames", settings["shots"]["frames"])),
        "steps": int(settings["shots"]["steps"]),
        "seed": int(seed),
        "size": LANDSCAPE if width >= height else PORTRAIT,
    }
    task["cache"] = cache.cache_key(STAGE, task)
    task["file"] = f"{label}-clip-{task['cache'][:10]}.mp4"
    return task


def tasks_for(storyboard: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """One task for each still that asks for a clip."""
    tasks = []
    for shot in storyboard["shots"]:
        stills = shot.get("stills", [])
        for number, still in enumerate(stills, start=1):
            if still.get("clip_prompt"):
                label = shot["id"] if len(stills) == 1 else f"{shot['id']}-{number}"
                tasks.append(task_for(still, label, shot["seed"], settings))
    return tasks


def clip_for(still: dict[str, Any], label: str, seed: int, settings: dict[str, Any]) -> Path | None:
    """The clip made for this still, if it has been made and brought back."""
    if not still.get("clip_prompt"):
        return None
    path = CLIPS / task_for(still, label, seed, settings)["file"]
    return path if path.exists() else None


def _cell(kind: str, source: str) -> dict[str, Any]:
    cell: dict[str, Any] = {"cell_type": kind, "id": uuid.uuid4().hex[:8], "metadata": {}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def _notebook(job: dict[str, Any]) -> dict[str, Any]:
    """A notebook that carries the whole job, so nothing has to be uploaded to Kaggle but it."""
    tasks = job["tasks"]
    encoded_job = base64.b64encode(json.dumps(job, ensure_ascii=False).encode("utf-8")).decode("ascii")
    encoded_script = base64.b64encode(SCRIPT.read_bytes()).decode("ascii")
    smoke = tasks[0]["id"] == "smoke" and len(tasks) == 1
    intro = (
        "# Make moving shots with Wan 2.2\n\n"
        "This notebook turns pictures of the film into short clips. It was written by `python -m pipeline shots`, "
        "and it carries everything it needs.\n\n"
        "**Before running:** on the right, in *Settings*, under *Accelerator*, choose **GPU T4 x2**. "
        "Then choose *Run all*.\n\n"
        "The first run downloads the model's weights, 34 GB, and installs a private copy of PyTorch. "
        "That takes a while. After that, each clip takes minutes.\n\n"
        "**This is an attempt.** The model is written for a GPU with 24 GB and for bfloat16 numbers. "
        "The free T4 has 16 GB. The job first runs the model in float16 and keeps the part that "
        "decodes pictures out of the GPU's way while the model works. If that stops, it tries the "
        "model's own number format, bfloat16, before it gives up. It may still run out of memory, "
        "and a clip made this way may look wrong. Whatever happens is written down in the log, "
        "with the place in the model's code where it stopped.\n\n"
        "**When it has finished:** download `clips.zip` from the output panel. Then, on your own machine, run "
        "`python -m pipeline shots import clips.zip`.\n\n"
        "If it stops, read `clips/progress.log` and `clips/job-output.log` in the output panel. The reason is at their end.\n\n"
        f"**This job:** {len(tasks)} clip(s) to try, in this order. "
        + "; ".join(f"{task['id']}: {task['frames']} frames at {task['size']} in {task['steps']} steps" for task in tasks)
        + ". The job stops at the first clip that fails, tries the model's own number format, and then gives up."
    )
    unpack = (
        "import base64, json, pathlib\n"
        f'job = json.loads(base64.b64decode("{encoded_job}").decode("utf-8"))\n'
        'pathlib.Path("job.json").write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")\n'
        f'pathlib.Path("make_shots.py").write_bytes(base64.b64decode("{encoded_script}"))\n'
        'print(f"Job for {len(job["tasks"])} clip(s) is written. Run the next cell.")\n'
    )
    show = (
        "import json, pathlib\n"
        "from IPython.display import FileLink, display\n"
        'manifest = pathlib.Path("clips/manifest.json")\n'
        "print(manifest.read_text(encoding=\"utf-8\") if manifest.exists() "
        "else \"No manifest, so the job did not finish. Read the output above, or clips/progress.log.\")\n"
        'if pathlib.Path("clips.zip").exists():\n'
        '    display(FileLink("clips.zip"))\n'
    )
    return {
        "cells": [
            _cell("markdown", intro),
            _cell("code", unpack),
            _cell("code", "!python make_shots.py job.json"),
            _cell("code", show),
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _smoke_task(task: dict[str, Any]) -> dict[str, Any]:
    """A tiny clip of the same picture: it shows whether the model loads and runs on this GPU at all."""
    smoke = dict(task)
    smoke.update(id="smoke", frames=9, steps=4)
    del smoke["cache"], smoke["file"]
    smoke["cache"] = cache.cache_key("smoke-shots", smoke)
    smoke["file"] = f"smoke-clip-{smoke['cache'][:10]}.mp4"
    return smoke


def export(storyboard: dict[str, Any], settings: dict[str, Any], *, smoke: bool = False) -> Path:
    """Write the job for Kaggle, and return the notebook that carries it.

    The real job tries a tiny clip first, so that a failure is found in
    minutes and not after an hour. Then the real clips, the smallest first.
    """
    tasks = tasks_for(storyboard, settings)
    if not tasks:
        raise SystemExit("No still asks for a clip. Give a still a clip_prompt in storyboard.json.")
    if smoke:
        tasks = [_smoke_task(tasks[0])]
    else:
        tasks = [_smoke_task(tasks[0]), *sorted(tasks, key=lambda task: task["frames"])]
    job = {"tasks": tasks, "images": {}}
    for name in sorted({task["image"] for task in tasks}):
        job["images"][name] = base64.b64encode((ROOT / name).read_bytes()).decode("ascii")
    JOBS.mkdir(parents=True, exist_ok=True)
    # The real job's description is kept apart from the test's, so that one does not overwrite the other.
    (JOBS / ("job-smoke.json" if smoke else "job.json")).write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notebook = JOBS / ("clip-smoke.ipynb" if smoke else "clip-job.ipynb")
    notebook.write_text(json.dumps(_notebook(job), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return notebook


def run(storyboard: dict[str, Any], settings: dict[str, Any]) -> list[Path]:
    """Say which clips exist. For the missing ones, write the job that makes them."""
    tasks = tasks_for(storyboard, settings)
    CLIPS.mkdir(parents=True, exist_ok=True)
    made, missing = [], []
    for task in tasks:
        path = CLIPS / task["file"]
        (made if path.exists() else missing).append(task)
        say(f"{task['id']:<12}clip       {'reused    ' if path.exists() else 'not made  '} {task['file']}")
    if missing:
        notebook = export(storyboard, settings)
        say("")
        say(f"{len(missing)} of {len(tasks)} clips are not made. The job for Kaggle is written: {cache.relative(notebook)}")
        say("On Kaggle: New Notebook, then File > Import Notebook, and choose that file.")
        say("In Settings, Accelerator: GPU T4 x2. Then Run all.")
        say("When it has finished, download clips.zip and run: python -m pipeline shots import clips.zip")
    return [CLIPS / task["file"] for task in made]


def _merge_log(folder: Path) -> None:
    """Add the calls made on Kaggle to runs.jsonl, each of them once."""
    incoming = [
        line
        for path in sorted(folder.rglob("runs.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not incoming:
        say("The bundle holds no calls, so nothing was added to runs.jsonl.")
        return
    seen: set[Any] = set()
    if RUNS.exists():
        for line in RUNS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seen.add(json.loads(line).get("call_id"))
    added = 0
    for line in incoming:
        record = json.loads(line)
        if record.get("call_id") in seen:
            continue
        try:
            log_model_call(record)
        except ValueError as exc:
            raise SystemExit(f"A call from Kaggle is not complete, so it was not logged: {exc}") from exc
        seen.add(record.get("call_id"))
        added += 1
    say(f"{added} call(s) from Kaggle added to runs.jsonl. {len(incoming) - added} were already there.")


def import_results(source: Path) -> list[Path]:
    """Bring Kaggle's results back: the clips into outputs/shots, its log into runs.jsonl, and its record into the repository."""
    if not source.exists():
        raise SystemExit(f"There is nothing at {source}.")
    with tempfile.TemporaryDirectory(prefix="heritage-import-") as scratch:
        folder = Path(scratch) / "received"
        if source.is_file():
            folder.mkdir()
            with zipfile.ZipFile(source) as archive:
                for name in archive.namelist():
                    if not (folder / name).resolve().is_relative_to(folder.resolve()):
                        raise SystemExit(f"{source} holds a file that would land outside its folder: {name}")
                archive.extractall(folder)
        else:
            folder = source
        manifests = sorted(folder.rglob("manifest.json"))
        if not manifests:
            raise SystemExit(f"{source} holds no manifest.json, so the job on Kaggle did not finish. Its progress.log says why.")
        base = manifests[0].parent
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        CLIPS.mkdir(parents=True, exist_ok=True)
        made: list[Path] = []
        for result in manifest["results"]:
            origin = base / result["file"]
            if not origin.is_file():
                continue
            target = CLIPS / result["file"]
            if not target.exists():
                shutil.copyfile(origin, target)
            say(f"{result['id']:<12}clip       imported    {target.name}  {ffmpeg.duration_seconds(target):.2f}s")
            made.append(target)
        # Kaggle's own record, kept with the film as evidence of what was tried.
        evidence = ROOT / "kaggle" / "logs" / "clips"
        evidence.mkdir(parents=True, exist_ok=True)
        for name in ("progress.log", "job-output.log", "manifest.json", "session.json"):
            origin = base / name
            if origin.is_file():
                shutil.copyfile(origin, evidence / name)
        _merge_log(base)
    return made
