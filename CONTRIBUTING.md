# Contributing to mediary

Thanks for helping! This guide covers the local setup and the conventions CI enforces.

## Setup

You need [uv](https://docs.astral.sh/uv/). Python versions are installed by uv as needed.

```sh
git clone git@github.com:codeonym-oss/mediary.git && cd mediary
uv sync                                  # .venv with the locked dev tools
uv run pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
```

The hooks run the same checks as CI:

| Stage        | Checks                                                   |
|--------------|----------------------------------------------------------|
| `pre-commit` | ruff lint + format, pyright (strict), file hygiene       |
| `commit-msg` | the message is a [Conventional Commit](#commits)         |
| `pre-push`   | the branch name follows [`<type>/<issue>-<slug>`](#branches) |

Run the full suite with `uv run pytest` (a coverage below 95% fails). To test another Python
version: `uv run --isolated --python 3.14 pytest`.

## Workflow

1. **Start from an issue.** Every change is tracked on the
   [project board](https://github.com/orgs/codeonym-oss/projects/2). Open one first if none exists.
2. **Branch** from `main` using the [branch convention](#branches).
3. **Commit** using [Conventional Commits](#commits).
4. **Open a PR** whose [title](#pull-requests) ends with the issue key and whose body says `Fixes #N`.
5. CI must be green. PRs are **squash-merged**, so the PR title becomes the commit on `main`.

`main` is protected: no direct pushes, no force-pushes, linear history, and these required checks:
`ci-ok`, `branch-name`, `commits`, `pr-title`.

## Conventions

The allowed types are the same everywhere:

| Type       | Use for                                          | In changelog |
|------------|--------------------------------------------------|--------------|
| `feat`     | a new feature                                    | Features     |
| `fix`      | a bug fix                                        | Bug Fixes    |
| `perf`     | a performance improvement                        | Performance  |
| `docs`     | documentation only                               | Documentation|
| `build`    | packaging, dependencies, build tooling           | Build        |
| `refactor` | code change that neither fixes nor adds          | hidden       |
| `test`     | tests only                                       | hidden       |
| `ci`       | CI and release workflows                         | hidden       |
| `chore`    | repo maintenance                                 | hidden       |
| `revert`   | reverting a previous commit                      | shown        |

### Branches

`<type>/<issue>-<slug>`: a type from the table, the GitHub issue number, and a short lowercase
hyphenated slug.

```text
feat/5-package-scan
fix/23-duplicate-handler-message
docs/12-readme-quickstart
```

Branches opened by bots (`release-please--*`, `dependabot/*`) are exempt.

### Commits

Every commit follows [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>(<optional scope>)<optional !>: <summary>

<optional body>

<optional footer(s)>
```

```text
feat(scan): bind handlers through the type hint of handle()
fix: report every duplicate handler at once
feat!: rename Mediator.register to Mediator.add

BREAKING CHANGE: Mediator.register was removed.
```

- Summary in the imperative, lowercase, no trailing period.
- `!` or a `BREAKING CHANGE:` footer marks a breaking change.
- The issue key is **not** required in commit messages; the branch and PR carry it.

### Pull requests

The title is a conventional commit summary **ending with the issue key**, and the body links the
issue:

```text
feat: discover requests and handlers by package scan (#5)
```

```text
Fixes #5
```

Keep a PR to one issue. Fill in the PR template's checklist.

## Releases

Releases are automated with [release-please](https://github.com/googleapis/release-please). Merges
to `main` keep a `chore(main): release X.Y.Z` PR up to date; merging it tags the release, updates
`CHANGELOG.md` and publishes to PyPI through Trusted Publishing. Never edit the version by hand.

Versions follow [SemVer](https://semver.org/). Before 1.0.0, breaking changes bump the minor version.

## Reporting bugs and security issues

- Bugs and feature ideas: [open an issue](https://github.com/codeonym-oss/mediary/issues/new/choose).
- Security vulnerabilities: see [SECURITY.md](SECURITY.md). Please don't open public issues for them.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
