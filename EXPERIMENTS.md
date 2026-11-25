# Experiments

Record at least ten experiments for full marks in the assignment 1 experimentation criterion. Change one major variable at a time where practical.

How this file is kept:

- The hypothesis is written down **before** the result is looked at. Where that did not happen, the row says so.
- The result is whatever came out. An experiment that did not support its guess stays here.
- Every call an experiment made is in `runs.jsonl`, under the stage named in the row.
- A row marked **planned** has not been run. Nothing is claimed for it.

| # | Hypothesis | Change (keep other variables controlled) | Evidence / result | Decision |
|---|---|---|---|---|
| 1 | None written beforehand for the 15 s test. A score test was measured because nobody could listen to it at the time. For the real score the guess was written first: a 90 s piece ends with a short fade of under 2 s, because the model has room to finish a musical phrase. | Each score on Kaggle, measured with `python -m pipeline check`. The real score is three candidates of 90 s, seeds 7, 8 and 9. | **The guess was not supported.** The 15 s test ends with 3.77 s of silence. The three 90 s candidates end with 9.38 s, 3.98 s and 7.59 s of silence, so their music lasts 80.6 s, 86.0 s and 82.4 s. | The second candidate (`chosen_index: 1`) is used, because its music is the only one that reaches the end card of an 88 s film. The film-maker may choose another by ear. |
| 2 | A crop of the face alone gives a closer likeness than the usual head-and-shoulders photo, because the face is only about 125 pixels wide in the photo and the usual reference spends most of its area on clothes and background. | Shot_08, the close-up of the shocked mother. Same prompt, seed 208, model, size and steps. Only the mother's reference image changes: the head-and-shoulders photograph (not published) against `outputs/experiments/mother-face-*.png`. The boy's reference is the same in both. | **Not supported.** By the coding agent's eye, the face-only crop gave a narrower face and no closer a resemblance. Neither picture is a strong likeness of the real person. The film-maker's own judgement is to be added. | Keep the head-and-shoulders reference. Say plainly, in the film's notes, that the likeness is an approximation. |
| 3 | None written beforehand. The overrun was found by the pipeline's own report. | Planned shot lengths against the spoken length of each line, with the narration setting the pace. | Two lines were longer than their shots (8.29 s and 8.01 s of speech). With the end card the film would have run 92.8 s against a 90 s limit. | The pipeline now refuses to assemble a film outside 60 to 90 s. Planned lengths re-balanced to 85.5 s; the film now runs 89.4 s (last line not yet spoken). |
| 5 | The same prompt and the same seed give the same picture twice. | Shot_08 made again with every input the same as its keyframe: prompt, seed 208, the same two reference files, 8 steps, the same size. The new file is compared with the old one by its hash and pixel by pixel. | **Not supported.** Different bytes. A mean difference of 29.9 levels out of 255, and 52 per cent of pixels differing by 16 levels or more. The staging was the same in both: the mother in the middle with her hands on her cheeks, the boy behind her, the wall of the yard. | The seed stays in the storyboard and the log as a record of what was asked. It is not relied on. A picture that matters is kept as a file. |
| 6 | More steps give a cleaner face and take longer in proportion: 4 steps look rough and 12 look best. | Shot_08 at 4 steps and at 12 steps, everything else as its keyframe at 8 steps. Time is read from the log. The face is judged by eye on a crop of each. | **Not supported, as far as one picture each can show.** By the coding agent's eye, the face at 4 steps is as clean as at 8 and at 12. Time did not rise with steps: 12.7 s, 11.8 s and 13.6 s. The price was the same each time, 245.19 Neurons. | Stay at 8 steps. Nothing is gained in price, and nothing was seen to be gained in quality. |
| 8 | Ducking makes the score quieter by 6 dB or more while the narrator speaks, and lets it back up within about 1.5 s after a line. | The first cut's score track rendered alone twice: through the film's ducking, and with the ducking left out. Its level is measured in the seconds where a line is spoken and in the gaps between lines. | **Supported.** While a line is spoken the score fell from minus 38.2 dB to minus 51.0 dB: 12.8 dB. In the gaps it was 2.0 dB lower with ducking than without. After a line ends, the score is back within 2 dB of its gap level after a median of 0.5 s (from 0.0 s to 1.8 s). | Keep ducking. Measured on the placeholder score with eleven lines, and to be measured again on the finished film. |
| 9 | `cover` keeps 56 per cent of a square still in a wide frame. `blur` keeps all of it, with blurred borders taking 44 per cent of the width between them. | Shot_08 brought to 1920 by 1080 both ways. A frame is taken from each and looked at. The share kept follows from the shapes: 1080 of 1920 pixels of height, and borders of 420 pixels on each side. | **Supported.** `cover` keeps the middle 56.2 per cent of the height. `blur` keeps the whole still, with borders of 420 pixels on each side, 43.8 per cent of the width. In `blur` the face is about half the size it is in `cover`. | `cover` for this film, because its stills keep their subjects in the middle. `blur` stays available as `fit: "blur"`, for a still whose subject is at the edge. |
| 10 | None written beforehand. It began with looking at the frames of a dry run. | Ten upright pictures and three wide ones, in a film made in 9:16 and in 16:9. First over a blurred backdrop, then through a window of the film's shape that moves across the picture. | Over a blurred backdrop, an upright picture in the wide film took a strip in the middle, and blur took two thirds of the frame. With the moving window the frame is always filled with the picture, and the whole picture is shown in turn: in the wide film the window starts on the faces and ends on the spilt milk. | The moving window, as `fit: "auto"`. Its cost: a wide picture in the upright film is enlarged about three times, and is a little soft. |

Experiments 2, 5, 6 and 9 were run on 25 Nov 2026 on the first version of the film, whose pictures were made by the image model. Those pictures are no longer in the film. The entries are kept as they were run.

What each row was run on:

## 1. Does a generated score fill the length asked for?

- **Setup:** the first score test on Kaggle was asked for 15 s. It was measured with `python -m pipeline check`, which finds 3.77 s of silence at the end of the 15.00 s file.
- **Guess for the real score, written before it exists:** a 90 s piece ends with a short fade of under 2 s, because the model has room to finish a musical phrase.
- **What it means for the film:** the score is cut to the picture's length with a fade, so a score that ends early would leave the last shots without music.

## 2. Does a face-only crop of the photo give a closer likeness?

- **Setup:** see the table. Both calls use FLUX.2 klein 4B at 1280 by 1280 with 8 steps on Cloudflare Workers AI. The experiment's call is logged under the stage `experiment`, target `shot_08-face-crop`.
- **How it is judged:** by eye, against the photo. That is a judgement, not a measurement, and it is reported as one.
- **Result (25 Nov 2026):** the hypothesis was not supported. In the face-only picture the face came out narrower and more angular. In the usual one it is rounder. Compared with the photo, the coding agent could not call either one a close likeness: both carry her glasses, her skin tone and her way of dressing, and neither carries her face exactly. The hypothesis was written down before the picture was looked at.
- **What it does not settle:** whether a larger model, or a photograph with more pixels on the face, would do better. Neither was tried, because the larger model costs about five times the day's allowance per picture.

## 3. Do the spoken lines fit the planned shot lengths?

- **What was found:** planned lengths are a floor. In a film cut to narration the length is known only after the narration exists, so the real length is checked at that point.
- **What was kept on purpose:** the long hold on the shocked face (shot_08) and the pause after the spill (shot_07). The slack was taken from the quiet lines instead.

## 5. Does the same seed give the same picture twice?

- **Why it matters:** the storyboard gives every shot a seed. If the service ignores it, a picture that is lost can only be made again as a different picture, and the seed is a label rather than a guarantee.
- **Setup:** see the table. The repeated call is logged under the stage `experiment`, target `shot_08-repeat`. The inputs were taken from `outputs/manifest.json`, so they are the keyframe's own.
- **Result (25 Nov 2026):** not supported. The service gave a different picture for the same seed. The composition was close: the same person in the same pose, the boy behind her. The framing, the boy's place and the details of the face were different.
- **What it means:** a seed on this service is a request and not a promise. The pipeline was already built for that. Every picture is kept as a file under a hash of its inputs, and the film is cut from the files, never made again from the seeds. The same is true of the speech service, which takes no seed at all.

## 6. Do more steps give a better face?

- **Why it matters:** steps are not charged by the image service. If 12 steps give a better face for the same price, the film should use them, and only the waiting time is lost.
- **Setup:** see the table. Both calls are logged under the stage `experiment`, targets `shot_08-steps-4` and `shot_08-steps-12`.
- **Result (25 Nov 2026):** not supported, as far as one picture at each setting can show. Looked at side by side at twice the size, the three faces were equally clean. The times were 12.7 s for 4 steps, 11.8 s for 8 and 13.6 s for 12, which is within the change from one call to the next.
- **What it does not settle:** whether the service acts on the number of steps at all. Because it does not repeat itself (experiment 5), one picture at each setting cannot show a small difference.

## 8. What does ducking do to the score?

- **Why it matters:** the brief asks for the score to be ducked under the narration. "Ducked" should mean something that can be measured.
- **Setup:** see the table. The levels come from the loudness of each half second of the two tracks, in dB below full scale. The voice is the side chain: it decides when the score is pressed down, and it is not heard in the track being measured.
- **Result (25 Nov 2026):** supported. Of 178 half seconds, 127 had a line being spoken.

| | Without ducking | With ducking |
|---|---:|---:|
| Score while a line is spoken | minus 38.2 dB | minus 51.0 dB |
| Score in the gaps between lines | minus 37.8 dB | minus 39.9 dB |

- **What it shows:** the score is pressed down by 12.8 dB under the narration. Between lines it is 2.0 dB quieter than it would be without ducking, which is the price of the release time. It comes back quickly: within 2 dB of its gap level after a median of 0.5 s.
- **Limit:** this was measured on the placeholder score, with eleven of the twelve lines. It is to be measured again on the finished film.

## 9. How much of a square picture survives a wide frame?

- **Why it matters:** the stills are square and the films are not. `cover` fills the frame and throws the rest away. `blur` keeps everything and fills the sides with a blurred copy.
- **Setup:** see the table. The two frames are `experiment-9-cover.png` and `experiment-9-blur.png`.
- **Result (25 Nov 2026):** supported, and seen. In `cover` the face fills the height of the frame. In `blur` the whole picture sits in the middle at 1080 by 1080, and the face is about half the size.
- **Decision:** `cover`. It was checked on all twelve keyframes that nobody is cut out by it.

## Planned, not yet run

Each guess is written here before it is run.

4. **Without the reference photos, the people change from shot to shot.** One shot made with and without its reference images, everything else the same. This one is waiting for the film-maker. The report has to say whether a practice beat his expectation or not, so his expectation is to be written here before the call is made.
7. **The whole script in one speech request sounds more natural than twelve separate lines.** One request against twelve. Costs one speech request, so it waits for the daily allowance.
