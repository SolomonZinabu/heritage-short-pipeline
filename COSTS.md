# Costs and measurements

Record measured values, not estimates presented as measurements.

Nothing was paid. Every call ran on a free tier. The figures below are read from `runs.jsonl` with `python -m pipeline costs` on 25 Nov 2026 at 23:45 East Africa Time. The column "list price" is what the same calls would have cost on the provider's paid plan, worked out from the published prices. It is not a payment.

## Calls

43 calls in all.

| Stage | Model / tool | Calls | Latency (median, longest) | GPU minutes | Measured cost | List-price equivalent | Notes |
|---|---|---:|---|---:|---:|---:|---|
| Narration | Gemini 3.8 Flash TTS | 17: 11 made, 6 refused | 5.7 s, 7.5 s | none | 0 | $0.0142 for 63.07 s of speech | Free tier. The service states a limit of 10 requests a day. The six refusals were HTTP 429 (five) and HTTP 503 (one). |
| Keyframes | FLUX.2 klein 4B, Cloudflare Workers AI | 15, all made | 17.6 s, 22.5 s | none | 0 | $0.0470 | 4,273.92 Neurons. Fifteen pictures for twelve shots: three were made again to correct a continuity slip. |
| Reference sheet | FLUX.2 klein 4B | 1, made | 13.2 s | none | 0 | $0.0026 | 234.45 Neurons. One place reference. The two photographs were not generated. |
| Experiments 2, 5 and 6 | FLUX.2 klein 4B | 4, made | 13.1 s, 16.1 s | none | 0 | $0.0108 | 980.76 Neurons. All on shot_08. |
| Smoke test | FLUX.2 klein 4B; Gemini TTS | 1 each, made | 6.5 s; 4.5 s | none | 0 | $0.0004; not known | One small call to each service. |
| Hand-sent probes | Gemini TTS | 3: 1 made, 2 refused | 0.9 s | none | 0 | 0 | Sent by hand to read the service's limit message. One of the three was not timed. See `FAILURES.md`. |
| Score, test | ACE-Step 1.5, on Kaggle | 1, made | 10.7 s | 0.2 | 0 | not known | 15 s of music. Installation took 72 s and is not counted. |
| Score, real | ACE-Step 1.5, on Kaggle | 3, made | 14.0 s, 17.2 s | 0.7 | 0 | not known | Three candidates of 90 s each, made by Solomon on 26 Nov 2026. They took 17.2 s, 14.0 s and 14.0 s on a Tesla T4. Installation took 4 min 10 s and is not counted. Their music lasts 80.6 s, 86.0 s and 82.4 s. |
| Moving shots, three attempts | Wan 2.2 TI2V-5B, on Kaggle | 3, all failed | 264 s, and longer | 0.8 | 0 | not known | No clip was made. The first attempt stopped at an import, the second on an assertion in the model, the third for want of GPU memory in both number formats. `FAILURES.md`. |
| Experiments 8 and 9 | FFmpeg only | no model called | | | 0 | 0 | Ducking measured, and two ways of fitting a still. Local files only. |

## Allowances

| Service | Free allowance | Used so far | What a whole film needs |
|---|---|---|---|
| Cloudflare Workers AI | 10,000 Neurons a day | 5,489.13 counted for 25 Nov, which is 54.9 per cent of a day, and about 30 more for the smoke image, which was logged before Neurons were recorded. More was spent on 26 Nov on test pictures that were all rejected. | Nothing. The film-maker supplies the pictures; the first version's 3,638.55 Neurons were spent on pictures that are not in the film. |
| Gemini TTS | 10 requests a day, as the service states | 11 lines, one smoke line and one probe were served | 8, one per line, which leaves 2 spare |
| Kaggle | GPU hours a week | About 47 minutes so far: under one for the score, and 46 for three failed attempts at moving shots | About five minutes for three 90-second candidates, by the test's rate |

## What a full run amounts to

Worked out from the list prices above, not paid: the twelve keyframes with their reference, $0.0400; the twelve lines of narration, about $0.016. Together about six cents.

## Other measurements

| What was measured | Value | How |
|---|---|---|
| Length of the first cut | 89.42 s | `python -m pipeline radio` |
| Loudness of the first cut | Minus 13.9 LUFS, integrated; true peak minus 1.6 dBTP | FFmpeg's `loudnorm`, second pass. The target is minus 14 LUFS. |
| Speech in the eleven lines spoken | 63.07 s in 11 files; 4.38 s to 8.29 s each | `runs.jsonl`, `output_seconds` |
| Silence before and after each line | 0.00 to 0.19 s before, 0.09 to 0.82 s after | `python -m pipeline check` |
| Loudest sample in each line | 0.6 to 2.1 dB below full scale; no clipped samples | `python -m pipeline check` |
| Narrator's pitch | Calm lines about 98 to 143 Hz; excited lines about 168 to 216 Hz. The check is not reliable enough to say more. | `python -m pipeline check`. See `FAILURES.md`. |
| Silence at the end of the 15 s score test | 3.77 s | `python -m pipeline check` |
| A keyframe | 1280 by 1280, 1.2 to 1.6 MB as JPEG | The files in `outputs/keyframes/` |
| A narration line | 24 kHz, mono, 213 to 396 KB as WAV | The files in `outputs/narration/` |
| Score test on Kaggle | 10.7 s for 15 s of music, 5.6 GB of GPU memory at its peak, on a T4 | `kaggle/logs/score-smoke-run-2/progress.log` |

Measured on 26 Nov 2026, on a dry run of the whole film at full size (1080 by 1920 and 1920 by 1080) with the film-maker's pictures, the chosen score and stand-in narration:

| What was measured | Value | How |
|---|---|---|
| The edit at full size, both aspect ratios | 267 s | The pipeline's own clock, from the start of assembly to the second film. |
| Length of that film | 89.08 s, 2,138 frames at 24 frames a second | Counted by decoding. |
| Loudness of that film | Minus 14.0 LUFS, integrated; true peak minus 1.9 dBTP | FFmpeg's `loudnorm`, second pass. |

The finished film, measured on 26 Nov 2026 after the narration was spoken: 89.50 s, 2,148 frames at 24 frames a second; loudness minus 13.9 LUFS, integrated; true peak minus 1.0 dBTP. The upright film is 27.2 MB and the wide film 87.9 MB. The narrator is heard during every line: the likeness between the film's sound and the voice alone is 0.95 to 1.00.

The narration took 9 requests on 26 Nov 2026: the line with the shout was spoken twice, the second time with a `<shout>` mark before the exclamation, and the service refused one call for 38 s before it was made. The eight lines as spoken last 84.5 s. They are brought 5 per cent closer together in time for the film, which costs nothing.
