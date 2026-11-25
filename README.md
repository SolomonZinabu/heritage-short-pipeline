# The Heritage Short

This is my project for 10 Academy’s Heritage Short challenge. I’m building a small, repeatable workflow that can turn a story that matters to me and my family into a short film.

I want to bring the parts of the process together in code: planning the shots, creating images and video, generating narration and music, and assembling the final edit. I’ll use audience feedback to improve the story, and I’ll keep notes on what works and what I learn along the way.

## Where I am now

I’ve set up the project structure, drafted the storyboard schema, and added a placeholder storyboard with eight shots. I’ve also written helpers to check the storyboard, create stable cache keys, and record model calls.

The storyboard is still a template: I have not yet filled in the story, audience, language, or prompts. The image, video, music, and narration generation stages, as well as final film assembly, are work I’ll add as I build and test the pipeline.

## Getting started

You’ll need Python 3.10 or newer.

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Check the placeholder storyboard structure:

```bash
python pipeline/validate_storyboard.py --allow-draft
```

Once I’ve filled in the storyboard, run the full validation:

```bash
python pipeline/validate_storyboard.py
```

The second command checks that the storyboard has no TODO placeholders and that the planned shots add up to 60–90 seconds. The Makefile also provides `make validate-draft` and `make validate` shortcuts.

## How I’m organizing the project

- `storyboard.json` is the plan that the pipeline stages will use.
- `schema/storyboard.schema.json` defines the storyboard structure.
- `pipeline/` contains the validation and helper code. I’ll add the generation and assembly stages here.
- `runs.jsonl` will record each model call, including its model, parameters, seed, latency, and cost.
- `outputs/` is where generated images, audio, and video will go.
- `DESIGN.md` is where I’ll record the audience, intent, and feedback from both viewer tests.
- `ARCHITECTURE.md` will describe how the stages, caching, and failure handling work.
- `EXPERIMENTS.md`, `FAILURES.md`, and `COSTS.md` will document my experiments, blockers, and measurements.
- `ETHICS.md` will record consent, model terms, and the film’s AI labelling.

## What I’ll do next

1. Choose the story, audience, language, and the feeling or understanding I want viewers to leave with.
2. Replace the TODO fields in `storyboard.json` with 8–12 planned shots, totaling 60–90 seconds.
3. Make a narration-only radio cut and ask at least three people from my intended audience for feedback.
4. Use that feedback to revise the storyboard, then build and test each generation stage.
5. Show a near-final cut to at least three audience members, record their feedback, and finish both video formats.

The final goal is for someone to clone the repository and use one documented command to regenerate the film. I’ll add that command once the generation and assembly stages are working.

## Ethics and secrets

I won’t put API keys in the repository. For local work, I can copy `.env.example` to `.env`; Git ignores that file. Before using a real person’s face, likeness, or voice, I’ll record their informed consent in `ETHICS.md`. I’ll also check and note the terms for the models I use.

## Putting the project on GitHub

After creating an empty public repository, I can push this project from its folder:

```bash
git init
git add .
git commit -m "initial commit with boiler-plate scaffolding"
git branch -M main
git remote add origin https://github.com/SolomonZinabu/heritage-short-pipeline.git
git push -u origin main
```
