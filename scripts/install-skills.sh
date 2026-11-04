#!/usr/bin/env bash
# One source, many clients: symlink every skill in skills/ into each client's
# project skills directory.
#   .claude/skills/<name>  -> Claude Code
#   .agents/skills/<name>  -> Codex (and other clients that read .agents/skills)
#
# Safe to run any number of times: correct links are left alone, stale links that
# point into skills/ are repaired or removed, and real directories are never touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TARGETS=(.claude/skills .agents/skills)

created=0; unchanged=0; repaired=0; pruned=0; skipped=0

for target in "${TARGETS[@]}"; do
  mkdir -p "$target"

  # Remove links into ../../skills/ whose skill no longer exists.
  for link in "$target"/*; do
    [ -L "$link" ] || continue
    dest="$(readlink "$link")"
    case "$dest" in
      ../../skills/*)
        if [ ! -e "$link" ]; then rm "$link"; pruned=$((pruned + 1)); echo "  pruned   $link"; fi ;;
    esac
  done

  for skill_dir in skills/*/; do
    name="$(basename "$skill_dir")"
    [ -f "skills/$name/SKILL.md" ] || continue
    link="$target/$name"
    want="../../skills/$name"
    if [ -L "$link" ]; then
      if [ "$(readlink "$link")" = "$want" ]; then
        unchanged=$((unchanged + 1))
      else
        ln -sfn "$want" "$link"; repaired=$((repaired + 1)); echo "  repaired $link -> $want"
      fi
    elif [ -e "$link" ]; then
      skipped=$((skipped + 1)); echo "  SKIPPED  $link exists and is not a symlink (left untouched)" >&2
    else
      ln -s "$want" "$link"; created=$((created + 1)); echo "  linked   $link -> $want"
    fi
  done
done

echo "skills: $created created, $unchanged unchanged, $repaired repaired, $pruned pruned, $skipped skipped"
