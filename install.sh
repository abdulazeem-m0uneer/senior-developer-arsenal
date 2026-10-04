#!/usr/bin/env bash
# ==============================================================================
# Senior Developer Arsenal Installer (Linux / macOS / WSL / Git Bash)
# Installs skills, subagents, rules and MCP servers for any supported AI agent.
# ==============================================================================
set -euo pipefail

ARSENAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
MANIFEST="$ARSENAL_ROOT/dist/manifest.tsv"
CLI_BIN="$ARSENAL_ROOT/scripts/arsenal"
MCP_MERGE="$ARSENAL_ROOT/scripts/mcp_merge.py"
ALL_TARGETS="antigravity gemini claude codex opencode cursor windsurf copilot"
BLOCK_BEGIN='<!-- BEGIN senior-developer-arsenal -->'
BLOCK_END='<!-- END senior-developer-arsenal -->'

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${YELLOW}[+] $*${NC}"; }
ok() { echo -e "  -> ${GREEN}$1${NC} $2"; }
warn() { echo -e "${YELLOW}[WARN] $*${NC}" >&2; }
die() { echo -e "${RED}Error: $*${NC}" >&2; exit 1; }

show_help() {
  cat <<EOF
Usage: ./install.sh [scope] [options]

Scope (one or both):
  -g, --global              Install into your home directory
  -p, --project <path>      Install into a project repository

Options:
  -t, --target <list>       Comma-separated agents (default: antigravity)
                            antigravity, gemini, claude, codex, opencode, cursor, windsurf, copilot, all
  -l, --link                Symlink instead of copy (stays live with this repository)
  -f, --force               Replace existing files that this installer did not create
  -u, --uninstall           Remove what this installer created for the chosen targets
  -n, --dry-run             Print actions without changing anything
  -s, --status              Show what is installed for the chosen targets
  -m, --hindsight           Register the Hindsight memory MCP server
  -c, --codegraph           Register the CodeGraph MCP server
      --bank <id>           Hindsight bank id (default: project folder name)
      --cli                 Install the 'arsenal' command into ~/.local/bin
  -h, --help                Show this help

Examples:
  ./install.sh --global --target all
  ./install.sh --project ~/code/api --target claude,cursor --link
  ./install.sh --global --target codex --codegraph
EOF
}

GLOBAL_MODE=false
PROJECT_PATH=""
TARGET_LIST="antigravity"
LINK_MODE=false
FORCE=false
UNINSTALL=false
DRY_RUN=false
STATUS_MODE=false
CLI_MODE=false
HINDSIGHT_MODE=false
CODEGRAPH_MODE=false
BANK_ID=""

need_value() { if [ $# -lt 2 ] || [ -z "$2" ]; then die "$1 requires a value."; fi; }

[ $# -gt 0 ] || { show_help; exit 0; }
while [ $# -gt 0 ]; do
  case "$1" in
    --global|-g) GLOBAL_MODE=true; shift ;;
    --project|-p) need_value "$@"; PROJECT_PATH="$2"; shift 2 ;;
    --target|-t) need_value "$@"; TARGET_LIST="$2"; shift 2 ;;
    --bank) need_value "$@"; BANK_ID="$2"; shift 2 ;;
    --link|-l) LINK_MODE=true; shift ;;
    --force|-f) FORCE=true; shift ;;
    --uninstall|-u) UNINSTALL=true; shift ;;
    --dry-run|-n) DRY_RUN=true; shift ;;
    --status|-s) STATUS_MODE=true; shift ;;
    --cli) CLI_MODE=true; shift ;;
    --hindsight|-m) HINDSIGHT_MODE=true; shift ;;
    --codegraph|-c) CODEGRAPH_MODE=true; shift ;;
    --help|-h) show_help; exit 0 ;;
    *) echo -e "${RED}Unknown option: $1${NC}" >&2; show_help; exit 1 ;;
  esac
done

# --- Resolve targets, scopes and inputs ---------------------------------------
TARGETS=()
IFS=',' read -r -a requested_targets <<< "$TARGET_LIST"
for requested in "${requested_targets[@]}"; do
  if [ "$requested" = "all" ]; then
    read -r -a TARGETS <<< "$ALL_TARGETS"
    break
  fi
  case " $ALL_TARGETS " in
    *" $requested "*) TARGETS+=("$requested") ;;
    *) die "Unknown target '$requested'. Valid: ${ALL_TARGETS// /, }, all." ;;
  esac
done
[ ${#TARGETS[@]} -gt 0 ] || die "--target requires at least one agent."

PROJECT_ROOT=""
if [ -n "$PROJECT_PATH" ]; then
  [ -d "$PROJECT_PATH" ] || die "Target project directory '$PROJECT_PATH' not found."
  PROJECT_ROOT="$(cd "$PROJECT_PATH" && pwd -P)"
  [ "$PROJECT_ROOT" != "$ARSENAL_ROOT" ] || die "Refusing to install the arsenal into its own repository."
fi

if [ -z "$BANK_ID" ]; then
  BANK_ID="senior-developer-arsenal"
  [ -z "$PROJECT_ROOT" ] || BANK_ID="$(basename "$PROJECT_ROOT")"
fi
[[ "$BANK_ID" =~ ^[A-Za-z0-9._-]+$ ]] || die "Bank id '$BANK_ID' may only contain letters, digits, '.', '_' and '-' (use --bank)."

MCP_MODE=false
if [ "$HINDSIGHT_MODE" = true ] || [ "$CODEGRAPH_MODE" = true ]; then MCP_MODE=true; fi

SCOPES=()
[ "$GLOBAL_MODE" = false ] || SCOPES+=("global")
[ -z "$PROJECT_ROOT" ] || SCOPES+=("project")
# MCP registration, status and uninstall default to the global scope.
if [ ${#SCOPES[@]} -eq 0 ]; then
  if [ "$MCP_MODE" = true ] || [ "$STATUS_MODE" = true ] || [ "$UNINSTALL" = true ]; then
    SCOPES+=("global")
  fi
fi
INSTALL_FILES=false
if [ "$GLOBAL_MODE" = true ] || [ -n "$PROJECT_ROOT" ]; then INSTALL_FILES=true; fi

[ ${#SCOPES[@]} -eq 0 ] || [ -f "$MANIFEST" ] || die "Missing dist/manifest.tsv. Run: python3 scripts/build.py"

INSTALLED=0
UNCHANGED=0
SKIPPED=0
REMOVED=0
FAILED=0

# --- Helpers -------------------------------------------------------------------
scope_base() { if [ "$1" = "global" ]; then echo "$HOME"; else echo "$PROJECT_ROOT"; fi; }

state_file() {
  if [ "$1" = "global" ]; then
    echo "$HOME/.config/senior-developer-arsenal/manifest"
  else
    echo "$PROJECT_ROOT/.agents/.arsenal-manifest"
  fi
}

# Prints manifest rows for one target and scope: kind name source destination extra
manifest_rows() {
  awk -F'\t' -v t="$1" -v s="$2" 'NR > 1 && $1 == t && $2 == s { print $3 "\t" $4 "\t" $5 "\t" $6 "\t" $7 }' "$MANIFEST"
}

is_recorded() { # state destination [target]
  [ -f "$1" ] && awk -F'\t' -v d="$2" -v t="${3:-}" '$2 == d && (t == "" || $1 == t) { found = 1 } END { exit !found }' "$1"
}

record() { # state target destination
  is_recorded "$1" "$3" "$2" && return 0
  mkdir -p "$(dirname "$1")"
  printf '%s\t%s\n' "$2" "$3" >> "$1"
}

forget() { # state target destination
  [ -f "$1" ] || return 0
  awk -F'\t' -v t="$2" -v d="$3" '!($1 == t && $2 == d)' "$1" > "$1.tmp"
  mv "$1.tmp" "$1"
  [ -s "$1" ] || rm -f "$1"
}

# Removes now-empty directories between a removed path and a base directory.
remove_empty_parents() { # path base
  local directory
  directory="$(dirname "$1")"
  while [ "$directory" != "$2" ] && [ "$directory" != "/" ] && rmdir "$directory" 2> /dev/null; do
    directory="$(dirname "$directory")"
  done
}

links_into_arsenal() {
  [ -L "$1" ] || return 1
  local resolved
  resolved="$(readlink "$1")"
  case "$resolved" in "$ARSENAL_ROOT"|"$ARSENAL_ROOT"/*) return 0 ;; *) return 1 ;; esac
}

# True when the destination already holds exactly what this run would install.
is_current() { # source path
  if [ "$LINK_MODE" = true ]; then
    [ -L "$2" ] && [ "$(readlink "$2")" = "$1" ]
  elif [ -L "$2" ]; then
    return 1
  elif [ -d "$1" ]; then
    diff -rq "$1" "$2" > /dev/null 2>&1
  else
    cmp -s "$1" "$2"
  fi
}

block_marker_counts() { # file -> "begin end"
  awk -v b="$BLOCK_BEGIN" -v e="$BLOCK_END" '$0 == b { nb++ } $0 == e { ne++ } END { print nb + 0, ne + 0 }' "$1"
}

strip_block() { # file -> stdout without the managed block
  awk -v b="$BLOCK_BEGIN" -v e="$BLOCK_END" '$0 == b { skip = 1; next } $0 == e { skip = 0; next } !skip' "$1"
}

# Older releases symlinked the whole .agents directory and AGENTS.md into the project.
migrate_legacy_links() {
  local legacy
  for legacy in "$PROJECT_ROOT/.agents" "$PROJECT_ROOT/AGENTS.md"; do
    if links_into_arsenal "$legacy"; then
      if [ "$DRY_RUN" = true ]; then
        echo "[dry-run] would remove legacy symlink $legacy"
      else
        rm "$legacy"
        ok "Removed legacy symlink:" "$legacy"
      fi
    fi
  done
}

install_item() { # target scope kind name source destination
  local target="$1" scope="$2" kind="$3" name="$4" source="$ARSENAL_ROOT/$5" destination="$6"
  local base state path
  base="$(scope_base "$scope")"; state="$(state_file "$scope")"; path="$base/$destination"
  [ -e "$source" ] || die "Missing source '$5'. Run: python3 scripts/build.py"

  if [ -e "$path" ] || [ -L "$path" ]; then
    if is_current "$source" "$path"; then
      [ "$DRY_RUN" = true ] || record "$state" "$target" "$destination"
      UNCHANGED=$((UNCHANGED + 1))
      return 0
    fi
    if [ "$FORCE" = false ] && ! is_recorded "$state" "$destination" && ! links_into_arsenal "$path"; then
      warn "Skipped $path (exists and was not created by this installer; use --force to replace)."
      SKIPPED=$((SKIPPED + 1))
      return 0
    fi
  fi
  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] would install $path"
    return 0
  fi
  rm -rf "$path"
  mkdir -p "$(dirname "$path")"
  if [ "$LINK_MODE" = true ]; then
    ln -s "$source" "$path"
  elif [ "$kind" = "dir" ]; then
    cp -R "$source" "$path"
  else
    cp "$source" "$path"
  fi
  record "$state" "$target" "$destination"
  INSTALLED=$((INSTALLED + 1))
}

install_block() { # target scope source destination
  local target="$1" scope="$2" source="$ARSENAL_ROOT/$3" destination="$4"
  local base state path counts body
  base="$(scope_base "$scope")"; state="$(state_file "$scope")"; path="$base/$destination"
  [ -f "$source" ] || die "Missing source '$3'. Run: python3 scripts/build.py"

  body=""
  if [ -f "$path" ]; then
    counts="$(block_marker_counts "$path")"
    if [ "$counts" != "0 0" ] && [ "$counts" != "1 1" ]; then
      warn "Skipped $path (unbalanced arsenal block markers; fix the file manually)."
      SKIPPED=$((SKIPPED + 1))
      return 0
    fi
    # A file copied verbatim by an older release is replaced, not duplicated.
    cmp -s "$source" "$path" || body="$(strip_block "$path")"
  elif [ -e "$path" ]; then
    warn "Skipped $path (not a regular file)."
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi
  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] would write the arsenal block in $path"
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  {
    if [ -n "$body" ]; then printf '%s\n\n' "$body"; fi
    printf '%s\n' "$BLOCK_BEGIN"
    cat "$source"
    printf '%s\n' "$BLOCK_END"
  } > "$path.arsenal-tmp"
  record "$state" "$target" "$destination"
  if [ -f "$path" ] && cmp -s "$path.arsenal-tmp" "$path"; then
    rm -f "$path.arsenal-tmp"
    UNCHANGED=$((UNCHANGED + 1))
    return 0
  fi
  mv "$path.arsenal-tmp" "$path"
  INSTALLED=$((INSTALLED + 1))
}

uninstall_item() { # target scope destination
  local target="$1" scope="$2" destination="$3"
  local base state path remaining
  base="$(scope_base "$scope")"; state="$(state_file "$scope")"; path="$base/$destination"
  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] would remove $path"
    return 0
  fi
  forget "$state" "$target" "$destination"
  [ -f "$state" ] || remove_empty_parents "$state" "$base"
  # Another installed target still shares this path.
  if is_recorded "$state" "$destination"; then return 0; fi
  if is_block_destination "$destination"; then
    if [ -f "$path" ] && [ "$(block_marker_counts "$path")" = "1 1" ]; then
      remaining="$(strip_block "$path")"
      if [ -n "${remaining//[[:space:]]/}" ]; then printf '%s\n' "$remaining" > "$path"; else rm -f "$path"; fi
    fi
  else
    rm -rf "$path"
  fi
  remove_empty_parents "$path" "$base"
  REMOVED=$((REMOVED + 1))
}

is_block_destination() {
  awk -F'\t' -v d="$1" '$3 == "block" && $6 == d { found = 1 } END { exit !found }' "$MANIFEST"
}

# Removes everything recorded for a target, including items a newer manifest no longer lists.
uninstall_target() { # target scope
  local state recorded_target destination
  state="$(state_file "$2")"
  [ -f "$state" ] || return 0
  while IFS=$'\t' read -r recorded_target destination; do
    [ "$recorded_target" != "$1" ] || uninstall_item "$1" "$2" "$destination"
  done < <(cat "$state")
}

server_enabled() {
  case "$1" in
    hindsight) [ "$HINDSIGHT_MODE" = true ] ;;
    codegraph) [ "$CODEGRAPH_MODE" = true ] ;;
    *) return 1 ;;
  esac
}

register_mcp() { # scope kind name source destination extra
  local scope="$1" kind="$2" name="$3" source="$ARSENAL_ROOT/$4" destination="$5" extra="$6"
  local path key format header separator=""
  path="$(scope_base "$scope")/$destination"; key="${extra%%:*}"; format="${extra##*:}"
  [ "$kind" != "mcp-if-exists" ] || [ -f "$path" ] || return 0
  [ -f "$source" ] || die "Missing source '$4'. Run: python3 scripts/build.py"

  if [ "$format" = "json" ]; then
    command -v python3 > /dev/null 2>&1 || die "python3 is required to update $path."
    local arguments=(--file "$path" --key "$key" --name "$name" --entry "$source" --set "BANK_ID=$BANK_ID")
    [ "$DRY_RUN" = false ] || arguments+=(--dry-run)
    python3 "$MCP_MERGE" "${arguments[@]}" || FAILED=1
    return 0
  fi

  header="[$key.$name]"
  if [ -f "$path" ] && grep -Fq "$header" "$path"; then
    echo "unchanged: '$name' already registered in $path"
    return 0
  fi
  if [ "$DRY_RUN" = true ]; then
    echo "[dry-run] would register '$name' in $path"
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  [ ! -f "$path" ] || cp -p "$path" "$path.bak-$(date +%Y%m%d%H%M%S)"
  [ ! -s "$path" ] || separator=$'\n'
  {
    printf '%s%s\n' "$separator" "$header"
    sed "s/{{BANK_ID}}/$BANK_ID/g" "$source"
  } >> "$path"
  echo "registered '$name' in $path"
}

show_status() { # target scope
  local base present=0 total=0 kind name source destination extra path
  base="$(scope_base "$2")"
  while IFS=$'\t' read -r kind name source destination extra; do
    case "$kind" in dir|file|block) ;; *) continue ;; esac
    total=$((total + 1)); path="$base/$destination"
    if [ "$kind" = "block" ]; then
      if [ -f "$path" ] && grep -Fxq "$BLOCK_BEGIN" "$path"; then present=$((present + 1)); fi
    elif [ -e "$path" ]; then
      present=$((present + 1))
    fi
  done < <(manifest_rows "$1" "$2")
  printf '  %-12s %-8s %s/%s items present\n' "$1" "$2" "$present" "$total"
}

process() { # target scope
  local target="$1" scope="$2" kind name source destination extra
  while IFS=$'\t' read -r kind name source destination extra; do
    case "$kind" in
      dir|file)
        [ "$INSTALL_FILES" = false ] || install_item "$target" "$scope" "$kind" "$name" "$source" "$destination" ;;
      block)
        [ "$INSTALL_FILES" = false ] || install_block "$target" "$scope" "$source" "$destination" ;;
      mcp|mcp-if-exists)
        ! server_enabled "$name" || register_mcp "$scope" "$kind" "$name" "$source" "$destination" "$extra" ;;
      mcp-note)
        ! server_enabled "$name" || echo -e "  ${CYAN}note:${NC} $extra" ;;
      note)
        [ "$INSTALL_FILES" = false ] || echo -e "  ${CYAN}note:${NC} $extra" ;;
      *) die "Unknown manifest row kind '$kind'. Update install.sh to match scripts/build.py." ;;
    esac
  done < <(manifest_rows "$target" "$scope")
}

# --- Main ----------------------------------------------------------------------
if [ "$STATUS_MODE" = true ]; then
  echo -e "${CYAN}=== Senior Developer Arsenal status ===${NC}"
  for scope in "${SCOPES[@]}"; do
    for target in "${TARGETS[@]}"; do show_status "$target" "$scope"; done
  done
  exit 0
fi

for scope in ${SCOPES[@]+"${SCOPES[@]}"}; do
  if [ "$scope" = "project" ] && [ "$UNINSTALL" = false ] && [ "$INSTALL_FILES" = true ]; then
    migrate_legacy_links
  fi
  for target in "${TARGETS[@]}"; do
    info "$target ($scope): $(scope_base "$scope")"
    if [ "$UNINSTALL" = true ]; then uninstall_target "$target" "$scope"; else process "$target" "$scope"; fi
  done
done

if [ "$CLI_MODE" = true ]; then
  TARGET_CLI="$HOME/.local/bin/arsenal"
  if [ -e "$TARGET_CLI" ] && [ ! -L "$TARGET_CLI" ] && [ "$FORCE" = false ]; then
    warn "Skipped $TARGET_CLI (exists and is not a symlink; use --force to replace)."
    SKIPPED=$((SKIPPED + 1))
  elif [ "$DRY_RUN" = true ]; then
    echo "[dry-run] would link $TARGET_CLI -> $CLI_BIN"
  else
    mkdir -p "$(dirname "$TARGET_CLI")"
    rm -f "$TARGET_CLI"
    ln -s "$CLI_BIN" "$TARGET_CLI"
    ok "CLI installed:" "$TARGET_CLI"
    case ":$PATH:" in
      *":$HOME/.local/bin:"*) ;;
      *) echo "  Add ~/.local/bin to PATH: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
  fi
fi

if [ ${#SCOPES[@]} -eq 0 ] && [ "$CLI_MODE" = false ]; then
  die "Nothing to do. Pass --global and/or --project <path> (see --help)."
fi

echo ""
if [ "$UNINSTALL" = true ]; then
  echo -e "${GREEN}[DONE] Removed $REMOVED item(s). MCP server entries are left in place.${NC}"
else
  echo -e "${GREEN}[DONE] Installed $INSTALLED, already current $UNCHANGED, skipped $SKIPPED.${NC}"
fi
[ "$FAILED" -eq 0 ] || die "One or more MCP configurations could not be updated (see messages above)."
