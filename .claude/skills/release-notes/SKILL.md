---
name: release-notes
description: Write the body of a draft GitHub release for this repo (riptide94/homeassistant-CenteroHome), structured into Highlights/Fixes/Known Issues/Other changes/Upgrade notes/Full Changelog, matching the format of past releases (v0.2.1, v0.2.0, v0.1.1). Use when asked to write/draft/update/fill in release notes, or when a draft release is open on GitHub and needs proper notes instead of the auto-generated PR list.
---

The release workflow (`.github/workflows/release.yml`) creates a draft
release with `gh release create --generate-notes` when a `vX.Y.Z` tag is
pushed. `--generate-notes` only produces a flat "What's Changed" bullet
list of PR titles — it is a starting point, not the final notes. This
skill replaces that body with hand-written notes in the repo's house
format, based on actually reading what changed.

## House format

Every release body is exactly these six sections, in this order, as `##`
headings (title `# vX.Y.Z` is optional/matches the tag):

```markdown
## Highlights

- **Short bold title** - a paragraph explaining the change, written for a
  Home Assistant user, not a developer. Explain *what changed for them*
  and *why it matters*. One bullet per major feature/change.

## Fixes

- Bugs fixed, one bullet each. If none, write a single "- None" (rare —
  most releases have at least something).

## Known Issues

- Known bugs/limitations still present in this release. If none: "- None 🥳"
  (this exact emoji is the house style, see v0.2.1/v0.2.0).

## Other changes

- Everything else noteworthy that isn't a headline feature or a bugfix:
  test coverage, docs, CI/workflow changes, refactors, dependency bumps.

## Upgrade notes

Plain paragraph(s) (not always bullets) telling someone upgrading from
the previous version what to expect: new entities that will appear, any
manual action needed, behavior changes, anything that could surprise
them. If genuinely nothing applies, say so explicitly rather than
omitting the section.

**Full Changelog**: https://github.com/riptide94/homeassistant-CenteroHome/compare/<prev_tag>...<new_tag>
```

Read `gh release view v0.2.1 --json body -q '.body'` and `gh release view
v0.2.0 --json body -q '.body'` for two full worked examples before
writing — match their tone (concise, user-facing, occasional bold lead-in
on Highlights bullets) rather than copying commit messages verbatim.

## Steps

1. **Find the draft release.**
   ```bash
   gh release list --json tagName,isDraft,name,createdAt
   ```
   Filter to `isDraft == true`. If there's more than one draft, or none,
   ask the user which tag to write notes for instead of guessing.

2. **Find the previous tag** to diff against — the release immediately
   before the draft in the same list (releases are ordered by creation,
   newest first; the draft is normally at the top). This is also the
   `<prev_tag>` half of the Full Changelog compare link.

3. **Sanity-check the version.** Confirm
   `custom_components/centero/manifest.json`'s `version` matches the
   draft's tag (minus the `v` prefix) — the release workflow already
   enforces this before the tag can produce a draft, but confirm you're
   looking at the right tag.

4. **Read what actually changed**, don't just skim commit subjects:
   ```bash
   git fetch --tags -q
   git log <prev_tag>..<new_tag> --oneline
   git diff <prev_tag>..<new_tag> --stat
   ```
   For anything non-obvious from the subject line, read the actual diff
   (`git show <sha>` or `git diff <prev_tag>..<new_tag> -- <path>`) or the
   merged PR (`gh pr list --state merged --base main --search
   "<new_tag>"` / `gh pr view <n>`) so the notes describe real
   user-visible behavior, not just restate the commit message. This
   integration's changes are often subtle (entity IDs, new `number`/
   `switch` entities, position-estimation behavior) — get it right rather
   than guessing from the title.

5. **Categorize** each change into Highlights / Fixes / Other changes,
   using judgment — a new user-facing feature is a Highlight even if the
   commit says "fix"; an internal refactor or test addition is "Other
   changes" even if the PR title says "feat". Check open issues (`gh
   issue list`) for anything that should land in Known Issues.

6. **Write the notes to a scratch file**, then apply them without
   publishing:
   ```bash
   gh release edit <new_tag> --notes-file <scratch_file>
   ```
   Do **not** pass `--draft=false` — leave the release as a draft. Publishing
   is a visible, hard-to-reverse action the user should trigger themselves
   (via `gh release edit <tag> --draft=false` or the GitHub UI) after
   reviewing.

7. Show the user the final body (or the `gh release view <tag> --json
   body -q .body` output) and point them at the draft's URL for review —
   don't just say "done".

## Gotchas

- `gh release list` includes drafts by default (no `--exclude-drafts` by
  default) — don't add `--exclude-drafts` or you'll filter out the one
  release this skill exists to edit.
- The Full Changelog link uses three dots (`...`), not two
  (`git diff`/`git log` use two) — `compare/v0.2.0...v0.2.1`.
- `git log`/`git diff` need the tags fetched locally first
  (`git fetch --tags`) — a tag pushed by CI to trigger the release
  workflow may not be in your local clone yet.
- If this is the very first release (no previous tag), there's no compare
  link possible — say so in that line instead of guessing a range.
