# Working on this repository

## Changelog: always

`tesserae_paperless/CHANGELOG.md` is the one changelog for this repository.
GitHub shows it, and Home Assistant shows it on the app's Changelog tab.

- Every change that a user can notice (a widget, the paperlesspaper plugin,
  the device kind, the app) gets a line under `## [Unreleased]` in the same
  commit or PR, under Added / Changed / Fixed / Removed. Write it for the
  user: what they see or can do now, not which file changed.
- Docs-only or test-only changes need no entry.

## Releasing a new app version

Home Assistant only offers an update when `version` changes, and the image is
built from the commit pinned in `WIDGETS_REF`. In the release commit:

1. Set `WIDGETS_REF` in `tesserae_paperless/build.yaml` and the default in
   `tesserae_paperless/Dockerfile` to the full SHA of the commit with the
   changes (the commit must stay on `master`: merge PRs with a merge commit,
   do not squash).
2. Bump `version` in `tesserae_paperless/config.yaml`.
3. In the changelog, move the Unreleased entries under
   `## [x.y.z] - YYYY-MM-DD`, note the Tesserae version and commit it is
   built from, and update the compare links at the bottom.

## Tests

```sh
python -m pytest paperlesspaper_core/tests -q
```
