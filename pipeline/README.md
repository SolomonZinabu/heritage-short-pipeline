# Pipeline stage contracts

Every stage is one module, run as `python -m pipeline <stage>`. Each one checks
`storyboard.json` first, looks for the outputs it already made, and only then
calls a model. Each model call is one line in `runs.jsonl`.

| Stage | Module | Reads from the storyboard | Writes | Reuses when unchanged |
|---|---|---|---|---|
| Narration | `narration.py` | `shots[].narration`, `narration.voice`, `narration.style` | `outputs/narration/<shot>-<key>.wav` | the text, the voice, the style, the model |
| Keyframes | `keyframes.py` | `references[]`, `visual_style`, `character_reference_prompt`, `shots[].image_prompt`, `shots[].seed` | `outputs/references/`, `outputs/keyframes/` | the prompt, the seed, the size, the steps, the model, the reference images |
| Shots | not built | `shots[].motion_prompt` | `outputs/shots/` | the keyframe, the motion prompt, the seed |
| Music | `music.py` | `music` | `outputs/music/`, and a job for Kaggle in `outputs/_jobs/music/` | the caption, the tempo, the key, the length, the seed |
| Assembly | `assemble.py` | shot lengths, `end_card`, `settings.assembly` | `outputs/radio/`, `outputs/film/` | every input file, by hash |

The shared code:

- `validate_storyboard.py` checks the storyboard. `load_storyboard` is what the stages call.
- `cache.py` makes the keys and keeps `outputs/manifest.json`.
- `runlog.py` writes `runs.jsonl`, including failed calls.
- `retry.py` retries the failures that may go away.
- `timeline.py` works out when each shot starts and how long it stays.
- `subtitles.py` draws the subtitles and the end card.
- `providers/` holds the two model clients, one file each.
- `smoke.py` holds `doctor` and `smoke`.
