"""Stage: music. The score is made with ACE-Step 1.5 on Kaggle, on a free GPU.

The model does not run on this machine, so the stage works in three steps:

1. ``python -m pipeline music`` finds which candidates already exist and, for
   the missing ones, writes a job for Kaggle: a notebook that carries the job
   inside it.
2. On Kaggle, the notebook installs the model, makes the candidates, and packs
   the audio, a log of every call and a manifest into ``score.zip``.
3. ``python -m pipeline music import score.zip`` brings them back, and adds
   Kaggle's calls to ``runs.jsonl``.
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

from . import cache, ffmpeg, media
from .config import OUTPUTS, ROOT, RUNS
from .runlog import log_model_call
from .util import say

STAGE = "music"
SCRIPT = ROOT / "kaggle" / "make_score.py"
JOBS = OUTPUTS / "_jobs" / "music"
SCORES = OUTPUTS / "music"
# A short job with a plain caption, to learn whether the Kaggle side works before the real score is needed.
SMOKE_CAPTION = "soft solo piano, slow and warm, a little hopeful"


def caption_for(storyboard: dict[str, Any]) -> str:
    """The description the model is given: the score's prompt and its mood."""
    music = storyboard["music"]
    return ". ".join(part.strip().rstrip(".") for part in (music["prompt"], music["mood"]) if part and part.strip())


def tasks_for(storyboard: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """One task per candidate. Each has its own seed, so each is made and logged on its own."""
    music, config = storyboard["music"], settings["music"]
    tasks = []
    for index in range(int(music.get("candidates", 1))):
        task = {
            "id": f"score-{index}",
            "model": config["model"],
            "caption": caption_for(storyboard),
            "bpm": int(music.get("bpm", 72)),
            "music_key": music.get("key") or "C major",
            "duration_seconds": float(music.get("duration_seconds", 60)),
            "steps": int(config["steps"]),
            "shift": float(config["shift"]),
            "seed": int(music.get("seed", 0)) + index,
        }
        task["cache"] = cache.cache_key(STAGE, task)
        task["file"] = f"{task['id']}-{task['cache'][:10]}.wav"
        tasks.append(task)
    return tasks


def chosen_index(storyboard: dict[str, Any]) -> int:
    return int(storyboard["music"].get("chosen_index", 0))


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
    intro = (
        "# Make the score with ACE-Step 1.5\n\n"
        "This notebook makes the score candidates of the film. It was written by `python -m pipeline music`, "
        "and it carries everything it needs.\n\n"
        "**Before running:** on the right, in *Settings*, under *Accelerator*, choose **GPU T4 x2**. "
        "Then choose *Run all*.\n\n"
        "The first run downloads the model and its parts, several GB, which takes a while. Later runs are quicker.\n\n"
        "**When it has finished:** download `score.zip` from the output panel. Then, on your own machine, run "
        "`python -m pipeline music import score.zip`.\n\n"
        "If it stops, open `score/progress.log` in the output panel. The reason is at its end.\n\n"
        f"**This job:** {len(tasks)} candidate(s), {tasks[0]['duration_seconds']:g} seconds each, "
        f"seeds {', '.join(str(task['seed']) for task in tasks)}."
    )
    unpack = (
        "import base64, json, pathlib\n"
        f'job = json.loads(base64.b64decode("{encoded_job}").decode("utf-8"))\n'
        'pathlib.Path("job.json").write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")\n'
        f'pathlib.Path("make_score.py").write_bytes(base64.b64decode("{encoded_script}"))\n'
        'print(f"Job for {len(job["tasks"])} candidate(s) is written. Run the next cell.")\n'
    )
    show = (
        "import json, pathlib\n"
        "from IPython.display import FileLink, display\n"
        'manifest = pathlib.Path("score/manifest.json")\n'
        "print(manifest.read_text(encoding=\"utf-8\") if manifest.exists() "
        "else \"No manifest, so the job did not finish. Read the output above, or score/progress.log.\")\n"
        'if pathlib.Path("score.zip").exists():\n'
        '    display(FileLink("score.zip"))\n'
    )
    return {
        "cells": [
            _cell("markdown", intro),
            _cell("code", unpack),
            _cell("code", "!python make_score.py job.json"),
            _cell("code", show),
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def export(storyboard: dict[str, Any], settings: dict[str, Any], *, smoke: bool = False) -> Path:
    """Write the job for Kaggle, and return the notebook that carries it."""
    if smoke:
        task = {
            "id": "smoke",
            "model": settings["music"]["model"],
            "caption": SMOKE_CAPTION,
            "bpm": 72,
            "music_key": "C major",
            "duration_seconds": 15,
            "steps": int(settings["music"]["steps"]),
            "shift": float(settings["music"]["shift"]),
            "seed": 1,
        }
        task["cache"] = cache.cache_key("smoke-music", task)
        task["file"] = f"smoke-score-{task['cache'][:10]}.wav"
        tasks = [task]
    else:
        tasks = tasks_for(storyboard, settings)
    job = {"lyrics": "[Instrumental]", "tasks": tasks}
    JOBS.mkdir(parents=True, exist_ok=True)
    (JOBS / "job.json").write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notebook = JOBS / ("score-smoke.ipynb" if smoke else "score-job.ipynb")
    notebook.write_text(json.dumps(_notebook(job), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return notebook


def run(storyboard: dict[str, Any], settings: dict[str, Any], *, mock: bool = False) -> Path | None:
    """The file of the chosen candidate, or None when it has not been made yet.

    When a candidate is missing, the job that makes it is written, so that the
    next step is ready.
    """
    tasks = tasks_for(storyboard, settings)
    directory = OUTPUTS / "_mock" / STAGE if mock else SCORES
    files = {task["id"]: directory / task["file"] for task in tasks}
    chosen = tasks[min(chosen_index(storyboard), len(tasks) - 1)]
    missing = [task for task in tasks if not files[task["id"]].exists()]

    if mock:
        for task in missing:
            media.placeholder_music(files[task["id"]], task["duration_seconds"])
            say(f"{task['id']}  score  mock        {task['file']}")
    elif missing:
        notebook = export(storyboard, settings)
        say(f"{len(missing)} of {len(tasks)} score candidates are not made yet.")
        say(f"The job for Kaggle is written: {cache.relative(notebook)}")
        say("On Kaggle: New Notebook, then File > Import Notebook, and choose that file.")
        say("In Settings, Accelerator: GPU T4 x2. Then Run all.")
        say("When it has finished, download score.zip and run: python -m pipeline music import score.zip")
    for task in tasks:
        if task not in missing:
            say(f"{task['id']}  score  reused      {task['file']}")

    if files[chosen["id"]].exists():
        return files[chosen["id"]]
    return None


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
    """Bring Kaggle's results back: the audio into outputs/music, and its calls into runs.jsonl."""
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
        SCORES.mkdir(parents=True, exist_ok=True)
        made: list[Path] = []
        for result in manifest["results"]:
            origin = base / result["file"]
            if not origin.is_file():
                continue
            target = SCORES / result["file"]
            if not target.exists():
                shutil.copyfile(origin, target)
            say(f"{result['id']}  score  imported    {target.name}  {ffmpeg.duration_seconds(target):.2f}s")
            made.append(target)
        _merge_log(base)
    return made
