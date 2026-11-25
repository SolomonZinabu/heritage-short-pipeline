# Pipeline stage contracts

Planned stages, all driven by storyboard.json:

1. `keyframes`: reference sheet and per-shot stills; cache by prompt, seed, model, parameters, and reference hashes.
2. `shots`: image-to-video clips or documented still-animation fallback.
3. `music`: generate/audition score candidates and record the selected candidate.
4. `narration`: render narration per shot and align English subtitles.
5. `assemble`: produce 9:16 and 16:9 MP4s, mix/duck audio, and add the AI end card.

These providers and stage scripts are not wired yet. Do not describe the starter as an end-to-end pipeline until the stages are implemented and the outputs are regenerated from a clean clone.
