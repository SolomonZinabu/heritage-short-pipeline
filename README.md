# The Heritage Short

A 60 to 90 second short film that one file describes. `storyboard.json` lists every shot: its picture, its movement, the line spoken over it and the English subtitle. The pipeline in `pipeline/` turns that file into narration, keyframes and a finished film in two aspect ratios.

## Run it

You need Python 3.10 or newer and nothing else. FFmpeg comes with the Python packages.

```
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the three values: a Gemini API key, and a Cloudflare account ID and API token. The pipeline never prints them and Git ignores the file.

```
python -m pipeline doctor    # what is ready and what is missing
python -m pipeline smoke     # one small call to each service, logged
python -m pipeline film      # everything, in outputs/film/
```

A dry run that calls no model and spends nothing: `python -m pipeline film --mock`.

## Commands

| Command | What it does |
|---|---|
| `python -m pipeline validate` | Checks the storyboard against its schema and the 60 to 90 second rule. `--allow-draft` allows TODOs. |
| `python -m pipeline doctor` | Checks the packages, FFmpeg, which private values are set, and the storyboard. |
| `python -m pipeline smoke` | Speaks one line and makes one image, and logs both. |
| `python -m pipeline narration` | Speaks the line of every shot. |
| `python -m pipeline keyframes` | Makes the reference sheet and the still of every shot. |
| `python -m pipeline music` | Reuses the score, or writes the job that makes it on Kaggle. `music import score.zip` brings the result back. |
| `python -m pipeline radio` | The radio cut: the narration over a placeholder score, on a black screen. |
| `python -m pipeline film` | Narration, keyframes and the edit, in 9:16 and 16:9, with subtitles and the end card. |

Every stage takes `--force` to make things again and `--mock` for a dry run. Narration and keyframes also take `--only shot_03,shot_07` to work on some shots.

## Change one thing, and only that is made again

Edit one narration line in `storyboard.json` and run the film again. That line is spoken again. The other lines, the keyframes and everything else are reused, because every generated file is named after a hash of its inputs. `runs.jsonl` gains exactly one line.

## Where things are

| Path | What it holds |
|---|---|
| `storyboard.json` | The contract: shots, durations, prompts, references, narration, music cues. |
| `schema/storyboard.schema.json` | What a valid storyboard looks like. Checked before every run. |
| `pipeline/` | One module per stage, the two model clients, and the shared cache, log and retry code. |
| `kaggle/` | The job that makes the score on Kaggle, and how to run it. |
| `runs.jsonl` | One line per model call: model, parameters, seed, latency, cost, and what came back. |
| `outputs/` | Everything generated, kept so a run can be inspected. `outputs/manifest.json` says which file belongs to which shot. |
| `ARCHITECTURE.md` | How the stages fit together, and how caching and failures are handled. |

## What it costs

The pipeline runs on free tiers. Cloudflare allows 10,000 Neurons a day free. A square 1280 pixel keyframe with two reference images uses about 330 of them, so a whole film's keyframes use about 3,800. On Cloudflare's paid plan that keyframe would cost about $0.004. `COSTS.md` holds the measured latency and the list-price equivalent of each stage.

## Status

Working, and tried end to end as a dry run: validation, narration, keyframes, the radio cut, the music stage, and the film in both aspect ratios with subtitles and the end card. The two hosted models, Gemini TTS and FLUX, have each answered a real call.

Not yet run on Kaggle: the score job for ACE-Step 1.5. It is written, and the part that brings its results back is tested, but the job itself has not run there.

Not built: moving shots from Wan 2.2. Until then a shot is shown as its keyframe with a slow move, and a film with no score yet uses a placeholder score.
