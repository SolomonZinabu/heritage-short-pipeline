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

## Not yet tried

The score job is written from the model's documentation and has not been run on
Kaggle yet. The first run is the test.
