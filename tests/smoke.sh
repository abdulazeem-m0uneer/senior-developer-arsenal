#!/usr/bin/env bash
# Smoke tests for install.sh. Runs every target against a throwaway HOME and project.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTALL="$ROOT/install.sh"
MANIFEST="$ROOT/dist/manifest.tsv"
TARGETS="antigravity gemini claude codex opencode cursor windsurf copilot"
BEGIN_MARKER='<!-- BEGIN senior-developer-arsenal -->'
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PASSED=0
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { PASSED=$((PASSED + 1)); echo "ok - $*"; }
fresh() { rm -rf "${WORK:?}/home" "${WORK:?}/proj"; mkdir -p "$WORK/home" "$WORK/proj"; export HOME="$WORK/home"; }

# Asserts that every dir/file/block row of the manifest exists under a base directory.
assert_installed() { # target scope base
  local kind destination
  while IFS=$'\t' read -r kind destination; do
    if [ "$kind" = "block" ]; then
      grep -Fxq "$BEGIN_MARKER" "$3/$destination" || fail "$1/$2: no arsenal block in $destination"
    else
      [ -e "$3/$destination" ] || fail "$1/$2: missing $destination"
    fi
  done < <(awk -F'\t' -v t="$1" -v s="$2" '$1 == t && $2 == s && ($3 == "dir" || $3 == "file" || $3 == "block") { print $3 "\t" $6 }' "$MANIFEST")
}

SKILL_COUNT="$(find "$ROOT/.agents/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"

for target in $TARGETS; do
  fresh
  "$INSTALL" --global --project "$WORK/proj" --target "$target" > "$WORK/out.txt" 2>&1 || { cat "$WORK/out.txt"; fail "$target: install exited non-zero"; }
  assert_installed "$target" global "$HOME"
  assert_installed "$target" project "$WORK/proj"
  grep -q "skipped 0" "$WORK/out.txt" || fail "$target: unexpected skips"
  "$INSTALL" --global --project "$WORK/proj" --target "$target" > "$WORK/out.txt" 2>&1
  grep -q "Installed 0," "$WORK/out.txt" || { cat "$WORK/out.txt"; fail "$target: second run is not idempotent"; }
  "$INSTALL" --global --project "$WORK/proj" --target "$target" --uninstall > /dev/null 2>&1
  [ -z "$(find "$HOME" "$WORK/proj" -mindepth 1)" ] || { find "$HOME" "$WORK/proj" -mindepth 1; fail "$target: uninstall left files behind"; }
  pass "$target: install, idempotent re-run, uninstall"
done

fresh
"$INSTALL" --global > /dev/null 2>&1
[ "$(find "$HOME/.gemini/config/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" = "$SKILL_COUNT" ] \
  || fail "default target did not install all $SKILL_COUNT skills"
[ ! -e "$HOME/.agents" ] || fail "default target must only touch Antigravity paths"
pass "default target is antigravity and installs all $SKILL_COUNT skills"

fresh
mkdir -p "$WORK/proj/.agents/skills/code-review" "$WORK/proj/.agents/skills/my-skill"
echo "user version" > "$WORK/proj/.agents/skills/code-review/SKILL.md"
echo "user skill" > "$WORK/proj/.agents/skills/my-skill/SKILL.md"
printf '# My project\n\nKeep me.\n' > "$WORK/proj/AGENTS.md"
"$INSTALL" --project "$WORK/proj" --target codex > "$WORK/out.txt" 2>&1
[ "$(cat "$WORK/proj/.agents/skills/code-review/SKILL.md")" = "user version" ] || fail "overwrote a user skill without --force"
[ -f "$WORK/proj/.agents/skills/my-skill/SKILL.md" ] || fail "deleted an unrelated user skill"
grep -q "Keep me." "$WORK/proj/AGENTS.md" || fail "lost user content in AGENTS.md"
grep -Fxq "$BEGIN_MARKER" "$WORK/proj/AGENTS.md" || fail "did not add the arsenal block"
grep -q "skipped 1" "$WORK/out.txt" || fail "did not report the skipped skill"
"$INSTALL" --project "$WORK/proj" --target codex --force > /dev/null 2>&1
grep -q "^name: code-review" "$WORK/proj/.agents/skills/code-review/SKILL.md" || fail "--force did not replace the skill"
"$INSTALL" --project "$WORK/proj" --target codex --uninstall > /dev/null 2>&1
[ "$(cat "$WORK/proj/AGENTS.md")" = "$(printf '# My project\n\nKeep me.')" ] || fail "uninstall did not restore AGENTS.md"
[ -f "$WORK/proj/.agents/skills/my-skill/SKILL.md" ] || fail "uninstall deleted an unrelated user skill"
pass "user files survive install, --force replaces, uninstall restores"

fresh
"$INSTALL" --project "$WORK/proj" --target codex,cursor > /dev/null 2>&1
"$INSTALL" --project "$WORK/proj" --target codex --uninstall > /dev/null 2>&1
[ -d "$WORK/proj/.agents/skills/code-review" ] || fail "uninstalling one target removed a path another target shares"
[ ! -e "$WORK/proj/.codex" ] || fail "uninstall left codex-only files"
pass "shared paths survive uninstalling one of two targets"

fresh
ln -s "$ROOT/.agents" "$WORK/proj/.agents"
ln -s "$ROOT/AGENTS.md" "$WORK/proj/AGENTS.md"
before="$(cd "$ROOT" && find .agents AGENTS.md -type f | sort | xargs cksum)"
"$INSTALL" --project "$WORK/proj" --target antigravity --link > /dev/null 2>&1
if [ -L "$WORK/proj/.agents" ] || [ -L "$WORK/proj/AGENTS.md" ]; then fail "legacy whole-directory symlinks were kept"; fi
[ -L "$WORK/proj/.agents/skills/code-review" ] || fail "--link did not create per-skill symlinks"
[ "$before" = "$(cd "$ROOT" && find .agents AGENTS.md -type f | sort | xargs cksum)" ] || fail "install wrote into the arsenal repository"
pass "legacy symlinks are migrated and --link creates per-item links"

fresh
"$INSTALL" --global --dry-run --target all > /dev/null 2>&1
[ -z "$(find "$HOME" -mindepth 1)" ] || fail "--dry-run changed the filesystem"
pass "--dry-run changes nothing"

fresh
mkdir -p "$HOME/.cursor" "$HOME/.codex"
echo '{"mcpServers": {"mine": {"command": "x"}}, "other": 1}' > "$HOME/.cursor/mcp.json"
printf '[mcp_servers.mine]\ncommand = "x"\n' > "$HOME/.codex/config.toml"
"$INSTALL" --target cursor,codex --codegraph --hindsight --bank my-bank > /dev/null 2>&1
python3 - "$HOME" <<'PY'
import json, sys, tomllib
home = sys.argv[1]
cursor = json.load(open(f"{home}/.cursor/mcp.json"))
assert cursor["other"] == 1 and cursor["mcpServers"]["mine"] == {"command": "x"}, cursor
assert cursor["mcpServers"]["codegraph"] == {"command": "codegraph", "args": ["serve", "--mcp"]}, cursor
assert cursor["mcpServers"]["hindsight"] == {"url": "http://localhost:8888/mcp/my-bank/"}, cursor
codex = tomllib.load(open(f"{home}/.codex/config.toml", "rb"))["mcp_servers"]
assert codex["mine"] == {"command": "x"} and codex["codegraph"]["args"] == ["serve", "--mcp"], codex
assert codex["hindsight"]["url"] == "http://localhost:8888/mcp/my-bank/", codex
PY
ls "$HOME/.cursor"/mcp.json.bak-* > /dev/null 2>&1 || fail "no backup of the existing MCP config"
"$INSTALL" --target cursor,codex --codegraph > "$WORK/out.txt" 2>&1
[ "$(grep -c "unchanged" "$WORK/out.txt")" = "2" ] || fail "MCP registration is not idempotent"
pass "MCP servers merge into existing JSON and TOML configs"

fresh
mkdir -p "$HOME/.cursor"
echo '{ not json' > "$HOME/.cursor/mcp.json"
if "$INSTALL" --target cursor --codegraph > /dev/null 2>&1; then fail "invalid MCP config did not fail the run"; fi
[ "$(cat "$HOME/.cursor/mcp.json")" = '{ not json' ] || fail "invalid MCP config was overwritten"
pass "an unparseable MCP config is left untouched and fails the run"

fresh
if "$INSTALL" --target cursor --hindsight --bank "a'b" > /dev/null 2>&1; then fail "unsafe bank id accepted"; fi
if "$INSTALL" --global --target nope > /dev/null 2>&1; then fail "unknown target accepted"; fi
if "$INSTALL" --project "$WORK/missing" > /dev/null 2>&1; then fail "missing project accepted"; fi
if "$INSTALL" --project "$ROOT" > /dev/null 2>&1; then fail "installing into the arsenal itself accepted"; fi
if "$INSTALL" --project > /dev/null 2>&1; then fail "--project without a value accepted"; fi
pass "invalid input is rejected"

fresh
mkdir -p "$HOME/.gemini/antigravity"
"$INSTALL" --target antigravity --codegraph > /dev/null 2>&1
[ ! -e "$HOME/.gemini/antigravity/mcp.json" ] || fail "created the legacy Antigravity MCP file"
echo '{}' > "$HOME/.gemini/antigravity/mcp.json"
"$INSTALL" --target antigravity --codegraph > /dev/null 2>&1
grep -q codegraph "$HOME/.gemini/antigravity/mcp.json" || fail "did not update the existing legacy Antigravity MCP file"
pass "legacy Antigravity MCP file is updated only when present"

fresh
mkdir -p "$WORK/my proj"
"$INSTALL" --project "$WORK/my proj" --target cursor --hindsight > "$WORK/out.txt" 2>&1 || { cat "$WORK/out.txt"; fail "a project path with spaces was rejected"; }
grep -q '"url": "http://localhost:8888/mcp/my-proj/"' "$WORK/my proj/.cursor/mcp.json" || fail "derived bank id was not sanitised"
[ -d "$WORK/my proj/.agents/skills/code-review" ] || fail "install into a path with spaces failed"
rm -rf "$WORK/my proj"
if "$INSTALL" --project "$HOME" --target codex > /dev/null 2>&1; then fail "the home directory was accepted as a project"; fi
pass "paths with spaces work and the home directory is refused as a project"

fresh
mkdir -p "$WORK/victim" "$WORK/proj/.agents"
echo keep > "$WORK/victim/file"
echo keep > "$WORK/proj/user.txt"
printf 'claude\t../victim\nclaude\t/%s\nclaude\nclaude\tsub/../../victim\n' "$WORK/victim" > "$WORK/proj/.agents/.arsenal-manifest"
"$INSTALL" --project "$WORK/proj" --target claude --uninstall > /dev/null 2>&1
[ -f "$WORK/victim/file" ] || fail "uninstall followed a path outside the project"
[ -f "$WORK/proj/user.txt" ] || fail "an empty record deleted the project"
pass "unsafe install records never delete anything"

fresh
ARSENAL_COPY="$WORK/arsenal"
mkdir -p "$ARSENAL_COPY"
cp -R "$ROOT/.agents" "$ROOT/dist" "$ROOT/scripts" "$ROOT/install.sh" "$ROOT/AGENTS.md" "$ARSENAL_COPY/"
mkdir -p "$WORK/proj/.agents"
ln -s "$ARSENAL_COPY/.agents/skills" "$WORK/proj/.agents/skills"
copy_files() { find "$ARSENAL_COPY/.agents" -type f | wc -l | tr -d ' '; }
before="$(copy_files)"
"$ARSENAL_COPY/install.sh" --project "$WORK/proj" --target codex --force > /dev/null 2>&1
"$ARSENAL_COPY/install.sh" --project "$WORK/proj" --target codex --link --force > /dev/null 2>&1
"$ARSENAL_COPY/install.sh" --project "$WORK/proj" --target codex --uninstall > /dev/null 2>&1
[ "$(copy_files)" = "$before" ] || fail "a symlinked parent let the installer modify the arsenal repository"
[ ! -L "$ARSENAL_COPY/.agents/skills/code-review" ] || fail "a source skill was replaced by a link to itself"
rm -rf "$ARSENAL_COPY"
pass "a parent symlinked into the arsenal is never written to or deleted"

fresh
printf '%s\n%s\nuser text after\n' '<!-- END senior-developer-arsenal -->' '<!-- BEGIN senior-developer-arsenal -->' > "$WORK/proj/AGENTS.md"
cp "$WORK/proj/AGENTS.md" "$WORK/expected.md"
"$INSTALL" --project "$WORK/proj" --target windsurf > "$WORK/out.txt" 2>&1
cmp -s "$WORK/proj/AGENTS.md" "$WORK/expected.md" || fail "reversed block markers led to lost content on install"
"$INSTALL" --project "$WORK/proj" --target windsurf --uninstall > /dev/null 2>&1
cmp -s "$WORK/proj/AGENTS.md" "$WORK/expected.md" || fail "reversed block markers led to lost content on uninstall"
pass "reversed block markers are left untouched"

fresh
echo "# mine" > "$WORK/proj/AGENTS.md"
ln -s AGENTS.md "$WORK/proj/CLAUDE.md"
"$INSTALL" --project "$WORK/proj" --target claude > "$WORK/out.txt" 2>&1
[ -L "$WORK/proj/CLAUDE.md" ] || fail "a symlinked CLAUDE.md was replaced by a regular file"
[ "$(grep -c 'BEGIN senior-developer-arsenal' "$WORK/proj/AGENTS.md")" = "1" ] || fail "writing through a symlink corrupted AGENTS.md"
grep -q "@AGENTS.md" "$WORK/proj/AGENTS.md" && fail "the CLAUDE.md import was written through the symlink"
"$INSTALL" --project "$WORK/proj" --target claude > "$WORK/out.txt" 2>&1
grep -q "Installed 0," "$WORK/out.txt" || fail "a symlinked block file makes re-runs unstable"
pass "a symlinked instruction file is skipped, not replaced or written through"

fresh
printf '# Mine\r\n\r\nKeep me.\r\n' > "$WORK/proj/AGENTS.md"
chmod 600 "$WORK/proj/AGENTS.md"
cp "$WORK/proj/AGENTS.md" "$WORK/expected.md"
"$INSTALL" --project "$WORK/proj" --target windsurf > /dev/null 2>&1
"$INSTALL" --project "$WORK/proj" --target windsurf > "$WORK/out.txt" 2>&1
[ "$(grep -c 'BEGIN senior-developer-arsenal' "$WORK/proj/AGENTS.md")" = "1" ] || fail "a CRLF file received a second block"
if grep -qv $'\r$' "$WORK/proj/AGENTS.md"; then fail "LF lines were written into a CRLF file"; fi
[ -n "$(find "$WORK/proj/AGENTS.md" -perm 600)" ] || fail "file permissions were widened"
"$INSTALL" --project "$WORK/proj" --target windsurf --uninstall > /dev/null 2>&1
cmp -s "$WORK/proj/AGENTS.md" "$WORK/expected.md" || fail "uninstall did not restore the CRLF file byte for byte"
pass "CRLF files keep their line endings and permissions"

fresh
mkdir -p "$HOME/.cursor"
echo '{}' > "$HOME/.cursor/mcp.json"
chmod 600 "$HOME/.cursor/mcp.json"
"$INSTALL" --target cursor --codegraph > /dev/null 2>&1
[ -n "$(find "$HOME/.cursor/mcp.json" -perm 600)" ] || fail "MCP config permissions were widened"
pass "MCP config permissions are preserved"

echo "all $PASSED smoke tests passed"
