# Handover: what is done, what is not, and how to continue

Written on 26 Nov 2026 at about 17:00 East Africa Time, when the work done with a coding agent stopped. The deadline for both assignments is 26 Nov 2026 at 23:59 East Africa Time.

This file says what is in the repository, what the brief still asks for, and how to do each thing that is left. `README.md` says how to run the pipeline; `DESIGN.md`, `ARCHITECTURE.md`, `ETHICS.md`, `EXPERIMENTS.md`, `FAILURES.md` and `COSTS.md` hold the rest.

## What exists

| What | Where |
|---|---|
| The finished film, upright, 9:16, 1080 by 1920, 89.5 s | `outputs/film/the-milk-mishap-4296e93523-9x16.mp4` |
| The finished film, wide, 16:9, 1920 by 1080, 89.5 s | `outputs/film/the-milk-mishap-4296e93523-16x9.mp4` |
| The film's subtitles as a file | `outputs/film/the-milk-mishap-4296e93523.srt` |
| The sound-only cut, for the first audience test | `outputs/radio/the-milk-mishap-radio-c80645b8db.mp4` |
| The eight spoken lines, and the film-maker's text | `outputs/narration/`, and `narration` in `storyboard.json` |
| The film-maker's thirteen pictures | `keyframes/` |
| Three candidates for the score; the second is used | `outputs/music/` |
| The log of every model call, including the failed ones | `runs.jsonl` |
| The Kaggle records of the score and of three failed attempts at moving shots | `kaggle/logs/` |

The film has the film-maker's pictures, his own narration in Amharic spoken by Gemini TTS, the score made on Kaggle, English subtitles, and an end card that says it was made with AI. The narrator's presence in the film is checked by the pipeline and was measured again by hand.

## What is not done, against the brief

In the order that matters for the marks:

1. **The report.** 30 marks. It must cover: what the film set out to make and for whom; what was learned from the audience; the hardest problem and how it was solved; one suggested practice that beat the film-maker's instinct and one that did not, each with evidence; any work beyond the floor; and what to build next. The material is in the other documents: the audience is at the top of `DESIGN.md`; the hardest problems are in `FAILURES.md`; the practices are tested in `EXPERIMENTS.md` (the JSON contract caught wrong storyboards several times; logging every call is what showed the limit of ten speech requests a day; letting the agent make the pictures did not work, see below); the work beyond the floor is the sound check, the handling of a daily limit, and the record of what the free GPU cannot do.
2. **The walkthrough video.** 30 marks. At most five minutes: the architecture, one hard decision, and one shot regenerated live. For the live part, change one thing in `storyboard.json`, run `.venv\Scripts\python.exe -m pipeline film`, and show that only that shot is made again. **Changing a narration line costs a speech request, and one is left today** (ten a day; the day ends at 08:00 UTC). A change that costs nothing: the `crop` or the `seconds` of a still, or a `focus`. One hard decision to explain: why the length is decided by the narration, or why the voice is split before it goes to two filters.
3. **The public post.** 20 marks. Written by the film-maker: the story, why it matters to him, one thing learned. The platform's AI label switched on. `ETHICS.md` asks for the film-maker's mother's own yes, in her words, before the film is posted publicly.
4. **The audience tests.** Notes of two tests with three people each, and what changed because of them, in `DESIGN.md`. At the time of writing: the film-maker's mother, his partner and a friend watched and liked it. Which file they watched, and what each one said, are not written down.
5. **The film must be reachable without a login.** Put it on a video platform or a static host and keep the link.
6. **Run the pipeline from a clean clone, with real keys, once more.** The dry run was tried from a clean copy on 25 Nov; the real run was not, for the final version.
7. **Merge the branch.** The work is on `build/pipeline`. `master` is behind it.
8. **Submit both assignments** on the TenX portal before the deadline.

## Where the work differs from the brief, on purpose or by failure

- **Moving shots.** The brief asks for Wan 2.2 image-to-video on Kaggle. The stage is built and the job is written (`kaggle/README.md`), and it was run three times on the free T4. The model loads, and runs out of the GPU's memory on even the smallest clip. `FAILURES.md` has the three attempts. The film uses the brief's stated fallback: stills with a slow move.
- **The pictures** were made by the film-maker with ChatGPT, not by the pipeline's own image stage. The pipeline can make a keyframe from a prompt, and did for a first version; the film-maker rejected those pictures. The pipeline copies and crops his.
- **The edit is cut to the narration**, not to the music cues. Each shot's `music_cue` is written down and not acted on.
- **Two stills ask for a clip** in `storyboard.json` (`clip_prompt`). No clip exists, so they are shown as stills.

## Things to know before changing anything

- **Never change the film-maker's Amharic, not even the spelling.** His text is the authority. Copy it from his file and compare, line by line.
- **Speech costs requests.** Ten a day on the free tier; the day ends at 08:00 UTC. `python -m pipeline narration` speaks only lines that are missing. `python -m pipeline smoke` spends one too.
- **A picture of another shape than the film** is looked at through a window that moves across it (`fit: "auto"`). A piece of the wrong size or frame count stops the pipeline.
- **The photographs of the two people are not in the repository**, by rule in `.gitignore`. Keep it so.
- **Commits** are made as the film-maker, on `build/pipeline`. He merges to `master` himself.
- **The branch was last pushed** on 26 Nov 2026; see the latest commit for the exact state.

## If the moving shots are tried again

What is known: the free T4 has 14.56 GB usable; the model's first step needs more than that with the model in 10 GB, the text encoder in the machine's memory and the picture decoder moved aside. Nine frames is the model's minimum. The ways on are a model that fits in 16 GB, sharing this model over the two T4s that Kaggle gives (`--dit_fsdp --t5_fsdp --ulysses_size 2` in the model's own code), or a clip made elsewhere and brought in with `python -m pipeline shots import`. The job's logs name the exact place of each failure from the third attempt on.

One clue is worth checking first. In the third run the GPU held 12.96 GB when the model's first step asked for 1.68 GB more. The model itself is 10 GB, and the part that decodes pictures is 2.8 GB. So that part was still on the GPU when the step ran, although the job is written to move it out. Commit `a834494` (made with another tool at 18:25) wraps the model's `cpu()` call as well as its `to()`, because `cpu()` does not go through `to()`. Whether the `to()` hook itself fires when the model is moved onto the GPU has not been checked; the first thing to do is to print where that part is before and after each move.
