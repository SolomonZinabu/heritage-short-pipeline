# Architecture

## One contract

`storyboard.json` is the contract between the stages. Every stage reads it, writes only its own files under `outputs/`, and appends one line to `runs.jsonl` for every model call it makes. Stages never talk to each other. A later stage reads only the files an earlier stage wrote, and knows them by a hash of their bytes.

```
storyboard.json  (checked against schema/storyboard.schema.json before every run)
      |
      +-------------+--------------+---------------+----------------+
      | narration   | keyframes    | shots         | music          |
      | one spoken  | reference    | one video     | score          |
      | line per    | sheet, then  | per shot      | candidates     |
      | shot        | one still    | (not built)   | on a free GPU  |
      | Gemini TTS  | FLUX on      | Wan 2.2 on    | ACE-Step on    |
      |             | Cloudflare   | Kaggle        | Kaggle         |
      +-------------+--------------+---------------+----------------+
      |                     |               |               |
      +---------------------+---------------+---------------+
                            |
                     assembly, with FFmpeg on this machine
          radio cut  |  film 9:16  |  film 16:9  |  subtitles.srt
```

## The stages

| Stage | Command | Reads | Writes | Model |
|---|---|---|---|---|
| Narration | `python -m pipeline narration` | `narration` of each shot, the voice | `outputs/narration/<shot>-<key>.wav` | Gemini 3.8 Flash TTS |
| Keyframes | `python -m pipeline keyframes` | `references`, then `image_prompt` of each shot with the style block | `outputs/references/`, `outputs/keyframes/` | FLUX.2 [klein] 4B on Cloudflare Workers AI |
| Shots | not built | keyframe and `motion_prompt` | `outputs/shots/` | Wan 2.2 TI2V-5B on Kaggle |
| Music | `python -m pipeline music`, then `python -m pipeline music import score.zip` | `music` | `outputs/music/` | ACE-Step 1.5 on Kaggle |
| Assembly | `python -m pipeline film`, `python -m pipeline radio` | everything above | `outputs/film/`, `outputs/radio/` | none: FFmpeg only |

`python -m pipeline film` runs narration, keyframes, music and assembly in that order. A shot that has no video yet is shown as its keyframe with a slow move, which the challenge allows as a fallback. A film whose score is not made yet uses a placeholder score.

## Timing comes from the narration

`duration_seconds` in the storyboard is a floor. After narration, each line's real length is measured, and a shot stays on screen for its planned time or for the length of its line plus a short lead-in and tail, whichever is longer. So no line is ever cut off, and the spoken word sets the pace. The arithmetic is in `pipeline/timeline.py`, in one place, and both the narration report and the assembly use it.

## Caching: a re-run makes only what changed

The name of every generated file ends in the start of a hash: `shot_03-37eeab5a41.png`. The hash is taken from everything that can change that file:

- the text of the prompt, the seed, the model name and the model's settings;
- the hashes of the assets the output is built on. A keyframe's key includes the reference images. A film's key includes every narration file, keyframe and clip.

A stage looks for a file with the right key before it calls a model. If the file is there, the stage says `reused` and makes no call. If an input changes, the key changes, and the result is a new file next to the old one rather than a silent replacement. `outputs/manifest.json` records which file belongs to which shot and from which inputs.

A consequence to know: changing a keyframe prompt changes that keyframe's hash, so a video clip made from the old keyframe no longer matches. Changing only a narration line changes that line, and the film.

Mock runs (`--mock`) write to `outputs/_mock/`, call no model and log nothing, so the edit and the cache can be tried without spending anything.

## What can fail, and what happens

| Failure | Handling |
|---|---|
| The storyboard is invalid or still has TODOs | No stage starts. `python -m pipeline validate` lists what is wrong. |
| A model answers with a rate limit, a server error, or the connection drops | The call is retried up to four times, waiting 2, 4, then 8 seconds, or for the time the server asks for. Every attempt is a line in `runs.jsonl`. |
| A model answers with anything else, or with no audio or image | The stage stops with the service's message. The failed call is logged. |
| A private value is missing | The stage stops and names the variable, never its value. |
| A call is interrupted, or FFmpeg fails | Every media file is written under a temporary name and moved into place only when it is complete, so a half-made file is never mistaken for a finished one. |
| The joined picture or a film has the wrong number of frames | FFmpeg can stop at a damaged shot and still report success, so the frames are counted. A wrong count is an error, not a film. |
| The sound mix | The score is repeated only as often as the film needs. A stream that never ends would keep the ducking filter waiting for ever. The mix also has a hard stop at the film's length. |
| A shot's clip is shorter than the shot | Its last frame is held. |
| A shot has no clip | Its keyframe is moved slowly instead. A shot with no keyframe is black. |
| A font is missing | A clear error says which setting names the font file. |
| A job on Kaggle stops | `score/progress.log` in its output holds the reason. The candidates already made are kept, and running it again continues from them. |
| The bundle from Kaggle is incomplete | It is taken in only with a manifest that lists what was made, and each call in it is logged once. |

## Choices worth knowing

- **One square keyframe, two crops.** The stills are square. The vertical and the horizontal film each take a centre crop, which is why prompts should keep the subject in the middle. The alternative, `fit: "blur"`, keeps the whole picture over a blurred copy of itself.
- **Text is drawn as images.** Subtitles and the end card are drawn with Pillow and laid over the film, so they look the same however FFmpeg was built. Subtitles in the vertical film sit at three quarters of the height, above where a phone app draws its buttons.
- **Loudness in two passes.** The mix is measured, then normalised to -14 LUFS with a -1 dBTP ceiling, which is what YouTube and most platforms expect.
- **The speech API takes no seed.** A narration line is made repeatable by keeping its file, not by a seed. The log says so on every narration line.

## The score is made on Kaggle

ACE-Step 1.5 needs a GPU that this machine does not have, so the music stage works in three steps.

1. `python -m pipeline music` writes a job: a notebook that carries the job inside it, so nothing else has to be uploaded to Kaggle.
2. On Kaggle, `kaggle/make_score.py` installs the model in a private environment, makes each candidate in a call of its own with its own seed, and packs the audio, a log of every call and a manifest into `score.zip`.
3. `python -m pipeline music import score.zip` brings the audio into `outputs/music/` and adds Kaggle's calls to `runs.jsonl`, each of them once.

The import was tested with a bundle made to look like Kaggle's. The job itself is written from the model's documentation and has not run on Kaggle yet. The first run is the test, and `kaggle/README.md` says what to do when it stops.

## Still to build

- The shots stage on Kaggle (Wan 2.2). The official code wants 24 GB of GPU memory and a number format that the free T4 does not have, so a shot is shown as its keyframe with a slow move until that is settled.
