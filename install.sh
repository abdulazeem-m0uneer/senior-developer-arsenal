#!/usr/bin/env bash
# Senior Developer Arsenal Installer for Unix / WSL
set -euo pipefail

ARSENAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_AGENTS="$ARSENAL_ROOT/.agents"
SOURCE_AGENTS_MD="$ARSENAL_ROOT/AGENTS.md"

echo "=================================================="
echo "   Senior Developer Arsenal Installer (sh)"
echo "=================================================="

show_help() {
  echo "Usage:"
  echo "  ./install.sh --global                  # Install globally into ~/.gemini/config"
  echo "  ./install.sh --project <path>          # Copy into target project repository"
  echo "  ./install.sh --project <path> --link   # Symlink into target project repository"
}

if [ $# -eq 0 ]; then
  show_help
  exit 0
fi

GLOBAL_MODE=false
PROJECT_PATH=""
SYMLINK_MODE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global)
      GLOBAL_MODE=true
      shift
      ;;
    --project)
      PROJECT_PATH="$2"
      shift 2
      ;;
    --link)
      SYMLINK_MODE=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

if [ "$GLOBAL_MODE" = true ]; then
  GLOBAL_CONFIG="$HOME/.gemini/config"
  GLOBAL_SKILLS="$GLOBAL_CONFIG/skills"
  GLOBAL_RULES="$GLOBAL_CONFIG/rules"

  echo "[+] Installing globally into: $GLOBAL_CONFIG"
  mkdir -p "$GLOBAL_SKILLS" "$GLOBAL_RULES"

  cp -r "$SOURCE_AGENTS/skills/"* "$GLOBAL_SKILLS/"
  cp -r "$SOURCE_AGENTS/rules/"*.md "$GLOBAL_RULES/"
  echo "[SUCCESS] Global installation completed!"
fi

if [ -n "$PROJECT_PATH" ]; then
  if [ ! -d "$PROJECT_PATH" ]; then
    echo "Error: Target project directory '$PROJECT_PATH' not found."
    exit 1
  fi

  TARGET_AGENTS="$PROJECT_PATH/.agents"
  TARGET_AGENTS_MD="$PROJECT_PATH/AGENTS.md"

  echo "[+] Installing into Project: $PROJECT_PATH"

  if [ "$SYMLINK_MODE" = true ]; then
    rm -rf "$TARGET_AGENTS" "$TARGET_AGENTS_MD"
    ln -s "$SOURCE_AGENTS" "$TARGET_AGENTS"
    ln -s "$SOURCE_AGENTS_MD" "$TARGET_AGENTS_MD"
    echo "[SUCCESS] Symlinked .agents and AGENTS.md into $PROJECT_PATH"
  else
    rm -rf "$TARGET_AGENTS"
    cp -r "$SOURCE_AGENTS" "$TARGET_AGENTS"
    cp "$SOURCE_AGENTS_MD" "$TARGET_AGENTS_MD"
    echo "[SUCCESS] Copied .agents and AGENTS.md into $PROJECT_PATH"
  fi
fi
