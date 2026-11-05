# Development guidelines

These instructions apply to `xiaqui/market-weather`. `TASK.md` defines the only currently authorized implementation work; long-term product specifications and history live in `docs/`.

## Preflight

- Confirm the working directory, `AGENTS.md`, `TASK.md`, and `git remote get-url origin` all identify this repository. If evidence conflicts or more than one target is plausible, stop and report the conflict instead of guessing.
- Fetch the latest `main`, inspect open PRs and branches, and read the documents referenced by the current task.
- Do not reuse a completed `TASK.md` or select an item from `docs/TODO.md` without a new explicit task.

## Git workflow

- Follow the Git mode written in `TASK.md`. If it is missing, do not choose a mode implicitly; update or clarify the task first.
- Use a branch and PR for logic, data formats, model behavior, external APIs, workflow/build changes, broad UI work, experiments, and changes with uncertain impact.
- Direct `main` changes are limited to explicitly authorized, reversible documentation or non-behavioral display corrections.
- Review corrections belong on the existing PR. Verify the remote head SHA after every update.
- Implementation work normally ends at a ready PR unless the task explicitly includes merge. Before any merge, check the latest head, required tests/CI, and unresolved review threads. P0/P1 blocks merge; resolve P2 or document its disposition.

## Verification

- Run the relevant Python tests, syntax/lint checks, web regressions, and `git diff --check` required by the task.
- If the local environment lacks an Android SDK, run all available local checks and use the existing Android CI when the task requires it.
- Preserve forecast reproducibility, immutable snapshots, no-lookahead guarantees, and existing production values unless the task explicitly changes them.
- Do not commit credentials, tokens, private URLs, personal data, or raw logs.

## Completion report

State the Git mode, branch and PR when used, commit and remote head SHA, tests and CI, review status, and remaining work. Do not describe unavailable builds, reviews, or device checks as completed.

