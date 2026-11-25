# The Milk Mishap

A 60 to 90 second short film that one file describes. `storyboard.json` lists every shot: its picture or pictures, the line spoken over it and the English subtitle. The pipeline in `pipeline/` turns that file into narration and a finished film in two aspect ratios.

The film is a family story in Amharic, told by the film-maker, Solomon Zinabu, about himself at six and his mother. It runs 88 seconds.

## Run it

You need Python 3.10 or newer and nothing else. FFmpeg comes with the Python packages.

```
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in a Gemini API key. The two Cloudflare values are needed only for a shot that has a prompt and no picture. The pipeline never prints these values and Git ignores the file.

```
python -m pipeline doctor    # what is ready and what is missing
python -m pipeline film      # everything, in outputs/film/
```

A dry run that calls no model and spends nothing: `python -m pipeline film --mock`.

## Commands

| Command | What it does |
|---|---|
| `python -m pipeline validate` | Checks the storyboard against its schema and the 60 to 90 second rule. |
| `python -m pipeline doctor` | Checks the packages, FFmpeg, which private values are set, and the storyboard. |
| `python -m pipeline narration` | Speaks the line of every shot. `--only shot_06` speaks one. `--voice Name` tries another narrator for that run only. |
| `python -m pipeline keyframes` | Takes the pictures the storyboard gives for each shot. For a shot with a prompt and no picture, it makes the picture with FLUX on Cloudflare Workers AI. |
| `python -m pipeline music` | Reuses the score, or writes the job that makes it on Kaggle. `music import score.zip` brings the result back. |
| `python -m pipeline radio` | The radio cut: the narration over a placeholder score, on a black screen. It goes on without a line the speech service is refusing for now, and says which. |
| `python -m pipeline film` | Narration, the pictures, the score and the edit, in 9:16 and 16:9, with subtitles, the end card and a note inside the file. It refuses to run without every line. |
| `python -m pipeline check` | Measures generated sound: level, clipped samples, silence at each end, and how high or low the voice is. |
| `python -m pipeline costs` | Turns `runs.jsonl` into a table for `COSTS.md`. |

Every stage takes `--force` to make things again and `--mock` for a dry run.

## Change one thing, and only that is made again

Edit one narration line in `storyboard.json` and run the film again. That line is spoken again. The other lines, the pictures and everything else are reused, because every generated file is named after a hash of its inputs. `runs.jsonl` gains exactly one line.

## Pictures

A shot names its pictures in `stills`: one, or several that are shown one after another. Each may name a `crop`, as left, top, right and bottom from 0 to 1, and its planned `seconds`. The pictures of this film are in `keyframes/`. They were made by the film-maker with an image tool of his own choice; the pipeline only copies and crops them.

A picture's shape rarely matches both films. With `fit: "auto"`, a picture that is much taller or much wider than the frame is looked at through a window of the frame's shape that moves slowly across it. A picture of a close shape fills the frame, around the shot's `focus` if it names one.

## Where things are

| Path | What it holds |
|---|---|
| `storyboard.json` | The contract: shots, durations, pictures, narration, subtitles, music. |
| `schema/storyboard.schema.json` | What a valid storyboard looks like. Checked before every run. |
| `keyframes/` | The film-maker's pictures, one or more per shot. |
| `pipeline/` | One module per stage, the model clients, and the shared cache, log and retry code. |
| `kaggle/` | The job that makes the score on Kaggle, and how to run it. |
| `runs.jsonl` | One line per model call: model, parameters, seed, latency, cost, and what came back. |
| `outputs/` | Everything generated, kept so a run can be inspected. `outputs/manifest.json` says which file belongs to which shot. |
| `DESIGN.md`, `ARCHITECTURE.md`, `ETHICS.md` | The audience and the shots; how the stages fit; consent, licences and labelling. |
| `EXPERIMENTS.md`, `FAILURES.md`, `COSTS.md` | What was tried, what went wrong, and what it measured. |

## What it costs

Nothing was paid. The speech service, Gemini TTS, allows 10 requests a day on its free tier, as the service itself states, and the day ends at 08:00 UTC. The film has eight lines, so eight requests, and the pipeline spends one only on a line that is missing. When a service asks for a long wait, the run stops, remembers the wait and sends nothing until it is over.

The score is made on Kaggle's free GPU: three candidates of 90 seconds took 14 to 17 seconds each on a Tesla T4.

The first version of this film had its pictures made by FLUX.2 klein 4B on Cloudflare Workers AI. The film-maker rejected them, for reasons recorded in `FAILURES.md`, and made his own. `COSTS.md` holds everything that was spent on both.

## Status

Working end to end as a dry run in both aspect ratios, at full size, with the film-maker's pictures and the chosen score. The narration is the film-maker's own text and has not been spoken yet: it waits for the speech service's daily allowance. The audience tests, the report, the walkthrough and the public post are not done. `DESIGN.md` says what has and has not been done.
