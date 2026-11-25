# The jobs that run on Kaggle

Two of the models need a GPU that this machine does not have: the score
(ACE-Step 1.5) and, if it is tried, the moving shots (Wan 2.2). They run on
Kaggle's free GPUs. The pipeline writes the job, Kaggle runs it, and the
pipeline takes the results back.

## The score

1. On this machine, write the job:

   ```
   .venv\Scripts\python -m pipeline music
   ```

   This writes `outputs/_jobs/music/score-job.ipynb`, a notebook that carries
   the whole job: the caption, the tempo, the key, the length and the seeds of
   every candidate.

2. On Kaggle: **New Notebook**, then **File > Import Notebook** and choose that
   file. On the right, in **Settings**, switch the accelerator on and choose
   **GPU T4 x2**. Then **Run all**.

   The first run downloads the model and its parts, several GB, so it takes a
   while. Later runs are quicker.

3. When it has finished, download `score.zip` from the output panel.

4. On this machine, bring the results back:

   ```
   .venv\Scripts\python -m pipeline music import score.zip
   ```

   The audio goes into `outputs/music/`, and every call made on Kaggle is added
   to `runs.jsonl`.

To find out whether the Kaggle side works before the real score is needed,
there is a job of fifteen seconds:

```
.venv\Scripts\python -m pipeline music export --smoke
```

It writes `outputs/_jobs/music/score-smoke.ipynb`, which is used the same way.

## If a job stops

Open `score/progress.log` in Kaggle's output panel. The reason is at its end.
The script also prints the names the library accepts for its settings, so a
mismatch can be seen at once.

## The record of each run

The output of each run on Kaggle is kept in `logs/`, so that a failure can
still be read after the page is closed. `FAILURES.md` refers to these files as
evidence. `score-smoke-run-1.txt` is the first run of the 15-second test.
`score-smoke-run-2/` holds the log, the manifest and the session of the second.

## How it went

The job has run on Kaggle twice, in one session, as the 15-second test. The
first run stopped on a setting the notebook passes to the programs it starts.
The second made the music. On a T4, 15 seconds of music took 10.7 seconds, with
5.6 GB of GPU memory at its peak.

The music lasts about 12 seconds and the last 3 seconds are silent. The
model's documentation calls 30 to 60 seconds the stable length, so the real
score is asked for at that length or longer, and its end is measured.

The real score has not been made yet.
