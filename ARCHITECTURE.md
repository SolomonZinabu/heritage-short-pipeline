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
| Keyframes | `python -m pipeline keyframes` | the `stills` each shot names; for a shot with none, its `image_prompt` with the references | `outputs/keyframes/` | none for a given picture; FLUX.2 [klein] 4B on Cloudflare Workers AI for a generated one |
| Shots | `python -m pipeline shots`, then `python -m pipeline shots import clips.zip` | the stills that have a `clip_prompt` | `outputs/shots/` | Wan 2.2 TI2V-5B on Kaggle, in float16 |
| Music | `python -m pipeline music`, then `python -m pipeline music import score.zip` | `music` | `outputs/music/` | ACE-Step 1.5 on Kaggle |
| Assembly | `python -m pipeline film`, `python -m pipeline radio` | everything above | `outputs/film/`, `outputs/radio/` | none: FFmpeg only |
| Sound check | `python -m pipeline check` | sound files | nothing | none: plain arithmetic |

`python -m pipeline film` runs narration, keyframes, music and assembly in that order. A shot that has no video yet is shown as its keyframe with a slow move, which the challenge allows as a fallback. A film whose score is not made yet uses a placeholder score.

## Pictures given, and several in one shot

A shot may name its pictures in `stills`, one or more. Each is a file in the repository, with an optional `crop` and its planned `seconds`. Nothing is generated for a given picture. The keyframe stage copies it into `outputs/keyframes/`, cut to its crop if it has one, under a name taken from the hash of the original and of the crop. So what the film shows is on record, and a changed picture is a new file rather than a silent replacement.

When a shot has several pictures, its time is shared among them in proportion to their planned seconds, counted in frames so that the shares add up exactly. A shot held longer for its line keeps its shape. The narration, the subtitle and the music cue belong to the whole shot.

This is how this film fits the speech service's limit of 10 requests a day: twelve of the film-maker's shots became eight lines, and the pictures of a merged pair are shown one after another under the one line.

## Who is in a shot

`references` in the storyboard holds the people and the place. A reference is either a brief that is generated (a prompt and a seed), or a photograph of a real person: `file` with the photo's `sha256`. A photograph is not generated. It is only shrunk to the size of the generated references and copied into `outputs/references/`, under a name taken from its fingerprint.

Each shot has a `cast`, a list of reference ids. Only those references are sent with the shot's prompt, and only they are described in it. A shot of milk on the ground names the place alone; a shot of the boy running names him and the place. The reason is not to offer the model two faces to choose from in a shot that shows one person. This was not tested one way against the other: experiment 4 in `EXPERIMENTS.md` is the test, and it has not been run.

The photographs themselves are not in the repository. Because the copy is named after the photo's fingerprint, which the storyboard carries, a clean clone that holds the copy still runs. A changed photograph stops the run and names its new fingerprint.

This was tried on 25 Nov 2026, on a copy of exactly what a fresh clone would hold: the copies of the photographs, and not the photographs. With dummy keys, so that a call would have failed, the keyframe stage found all twelve keyframes and their references and called nothing. The dry run (`film --mock`) wrote both films. What it does not show is a real call from a clean clone: that is to be done at the end, with real keys.

## Timing comes from the narration

`duration_seconds` in the storyboard is a floor. After narration, each line's real length is measured, and a shot stays on screen for its planned time or for the length of its line plus a short lead-in and tail, whichever is longer. So no line is ever cut off, and the spoken word sets the pace. The arithmetic is in `pipeline/timeline.py`, in one place, and both the narration report and the assembly use it.

Because the planned times are only a floor, the storyboard's own check cannot know the film's real length. So the assembly checks it again once the lines have been spoken, and refuses to make a film outside 60 to 90 seconds. On this film the first spoken lines ran past their shots and would have given 92.8 seconds.

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
| A server asks for a long wait | A wait of up to two minutes is obeyed. A longer one is not: the run stops, names the time to return, and remembers the wait in `outputs/_build/wait-<service>.json`. Until that time no call is sent to that service, so that none is sent only to be refused. What was already made is kept. |
| A model answers with anything else, or with no audio or image | The stage stops with the service's message. The failed call is logged. |
| A private value is missing | The stage stops and names the variable, never its value. |
| A call is interrupted, or FFmpeg fails | Every media file is written under a temporary name and moved into place only when it is complete, so a half-made file is never mistaken for a finished one. |
| The joined picture or a film has the wrong number of frames | FFmpeg can stop at a damaged shot and still report success, so the frames are counted. A wrong count is an error, not a film. |
| A piece comes out at another size | Pieces of different sizes can be joined without an error and spoil the film, so every piece is measured before it is joined. |
| The mixed sound holds no narrator | A mix that holds only the score sounds finished and is not. The first line is looked for in the mix where it is spoken; if it is not found, the mix is refused. The voice is split before it goes to the two filters that need it. |
| The sound mix | The score is repeated only as often as the film needs. A stream that never ends would keep the ducking filter waiting for ever. The mix also has a hard stop at the film's length. |
| A shot's clip is shorter than the shot | Its last frame is held. |
| A shot has no clip | Its keyframe is moved slowly instead. A shot with no keyframe is black. |
| The speech service is refusing a line for now | The radio cut goes on without that line and says which shot is silent. The film refuses to be made: a finished film has every line. |
| The film's real length is outside 60 to 90 seconds | The assembly stops before rendering, and says how long the film would be. |
| A photograph named in the storyboard has changed | The run stops and names the photo's new fingerprint, which belongs in the storyboard in place of the old one. |
| A font is missing | A clear error says which setting names the font file. |
| A job on Kaggle stops | `score/progress.log` in its output holds the reason. The candidates already made are kept, and running it again continues from them. |
| The bundle from Kaggle is incomplete | It is taken in only with a manifest that lists what was made, and each call in it is logged once. |

## Choices worth knowing

- **A picture of another shape is looked at through a moving window.** With `fit: "auto"`, a picture much taller or wider than the frame is neither cut to a strip nor set over a backdrop of blur, which would fill most of the frame. A window of the film's shape moves slowly across it, from well inside one end to well inside the other, around the shot's `focus` if it names one. A picture of a close shape fills the frame. `fit: "cover"` and `fit: "blur"` remain by name.
- **The film says what it is.** The last three seconds carry an end card in English and Amharic. Each film file also holds its title and a note in its metadata: "Made with AI. The pictures, the narration and the music were generated by models." The image service returns plain pictures with no provenance data, so the note is written here.
- **Text is drawn as images.** Subtitles and the end card are drawn with Pillow and laid over the film, so they look the same however FFmpeg was built. Subtitles in the vertical film sit at three quarters of the height, above where a phone app draws its buttons.
- **Loudness in two passes.** The mix is measured, then normalised to -14 LUFS with a -1 dBTP ceiling, which is what YouTube and most platforms expect.
- **The speech API takes no seed.** A narration line is made repeatable by keeping its file, not by a seed. The log says so on every narration line.

## The score is made on Kaggle

ACE-Step 1.5 needs a GPU that this machine does not have, so the music stage works in three steps.

1. `python -m pipeline music` writes a job: a notebook that carries the job inside it, so nothing else has to be uploaded to Kaggle.
2. On Kaggle, `kaggle/make_score.py` installs the model in a private environment, makes each candidate in a call of its own with its own seed, and packs the audio, a log of every call and a manifest into `score.zip`.
3. `python -m pipeline music import score.zip` brings the audio into `outputs/music/` and adds Kaggle's calls to `runs.jsonl`, each of them once.

The job has run on Kaggle once, as a 15-second test. Its first run stopped on a setting that Kaggle's notebook passes to the programs it starts. Run again in the same session, it made the music: 10.7 seconds on a T4 for 15 seconds of music, with 5.6 GB of GPU memory at its peak. `kaggle/logs/` holds the record of both runs, and `kaggle/README.md` says what to do when a job stops. Both runs are in `FAILURES.md`.

## Sound is measured before it is trusted

`python -m pipeline check` reads a sound file and reports how long it is, how much silence lies before and after the sound, the loudest sample, the number of clipped samples, and the pitch of the voice. It finds the pitch by comparing each short piece of the sound with a shifted copy of itself, in plain arithmetic, so it needs nothing beyond FFmpeg. It was written because a score test ended in silence that nobody could hear at the time. It does not judge acting, and its pitch is an estimate: on this film it read the excited lines higher than the calm ones and could not say why.

## The moving shots are an attempt on a GPU that is too small

The shots stage works like the score stage: a job is written here, run on Kaggle, and brought back. A still with a `clip_prompt` asks for a clip, and a clip that exists takes the place of its still for the still's time; after the clip its last frame is held.

Wan 2.2's code is written for a GPU with 24 GB and for bfloat16 numbers. Kaggle's free T4 has 16 GB and no bfloat16. The job makes a private copy on Kaggle and changes three lines of it: the picture model runs in float16, and is loaded straight into float16 from weight files converted first, so that the machine's memory is enough. The part that decodes pictures waits in the machine's memory while the picture model works. The job tries a clip of nine frames first and stops at the first failure, so that a failure costs minutes and not an hour. No clip has come out. On 26 Nov 2026 three attempts on the free T4 failed; the last two for want of GPU memory, in both number formats. They are in `FAILURES.md`, and the film uses the brief's fallback.
