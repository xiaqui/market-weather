# TASK.md workflow

`TASK.md` contains the single current assignment for Market Weather. Permanent product specifications belong in the relevant `docs/` file and deferred work belongs in `docs/TODO.md`.

Each task records:

- whether it is new work or a correction to an existing PR;
- the required Git mode (`branch + PR` or an explicitly authorized direct documentation/display correction);
- base branch or existing PR;
- scope, non-goals, tests, and completion conditions;
- whether merge is authorized.

Before implementation, confirm the repository, latest `main`, open PRs, and that the task is still active. Do not replay a completed task. Corrections remain on the existing PR. Verify the latest remote head, required CI/tests, reviews, and unresolved threads before merge. After completion, replace the file with a clear no-active-task state or the next explicitly approved assignment.

