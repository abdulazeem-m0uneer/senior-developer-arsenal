#!/usr/bin/env bash
# ==============================================================================
# Senior Developer Arsenal Installer for Ubuntu / Linux / WSL
# ==============================================================================
set -euo pipefail

ARSENAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_AGENTS="$ARSENAL_ROOT/.agents"
SOURCE_AGENTS_MD="$ARSENAL_ROOT/AGENTS.md"
CLI_BIN="$ARSENAL_ROOT/scripts/arsenal"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}==================================================${NC}"
echo -e "${CYAN}   🚀 Senior Developer Arsenal Installer (Ubuntu/Linux)${NC}"
echo -e "${CYAN}==================================================${NC}"

# Ensure CLI script is executable
if [ -f "$CLI_BIN" ]; then
  chmod +x "$CLI_BIN"
fi

show_help() {
  echo "Usage:"
  echo "  ./install.sh --global                  # Install globally into ~/.gemini/config"
  echo "  ./install.sh --cli                     # Install 'arsenal' CLI command to ~/.local/bin"
  echo "  ./install.sh --project <path>          # Copy into target project repository"
  echo "  ./install.sh --project <path> --link   # Symlink into target project repository"
  echo "  ./install.sh --status                  # Verify installed skills & rules"
}

if [ $# -eq 0 ]; then
  show_help
  exit 0
fi

GLOBAL_MODE=false
CLI_MODE=false
PROJECT_PATH=""
SYMLINK_MODE=false
STATUS_MODE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global|-g)
      GLOBAL_MODE=true
      shift
      ;;
    --cli)
      CLI_MODE=true
      shift
      ;;
    --project|-p)
      PROJECT_PATH="${2:-}"
      shift 2
      ;;
    --link|-l)
      SYMLINK_MODE=true
      shift
      ;;
    --status|-s)
      STATUS_MODE=true
      shift
      ;;
    --help|-h)
      show_help
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      show_help
      exit 1
      ;;
  esac
done

# 1. Global Installation Mode
if [ "$GLOBAL_MODE" = true ]; then
  GLOBAL_CONFIG="$HOME/.gemini/config"
  GLOBAL_SKILLS="$GLOBAL_CONFIG/skills"
  GLOBAL_RULES="$GLOBAL_CONFIG/rules"

  echo -e "${YELLOW}[+] Installing globally into: $GLOBAL_CONFIG${NC}"
  mkdir -p "$GLOBAL_SKILLS" "$GLOBAL_RULES"

  skill_count=0
  for skill_dir in "$SOURCE_AGENTS/skills/"*; do
    if [ -d "$skill_dir" ]; then
      skill_name="$(basename "$skill_dir")"
      target="$GLOBAL_SKILLS/$skill_name"
      rm -rf "$target"
      cp -r "$skill_dir" "$target"
      echo -e "  -> ${GREEN}Skill:${NC} $skill_name"
      ((skill_count++))
    fi
  done

  rule_count=0
  for rule_file in "$SOURCE_AGENTS/rules/"*.md; do
    if [ -f "$rule_file" ]; then
      rule_name="$(basename "$rule_file")"
      cp "$rule_file" "$GLOBAL_RULES/$rule_name"
      echo -e "  -> ${GREEN}Rule:${NC} $rule_name"
      ((rule_count++))
    fi
  done

  echo ""
  echo -e "${GREEN}[SUCCESS] Installed $skill_count skills and $rule_count rules globally!${NC}"
fi

# 2. CLI Tool Installation Mode
if [ "$CLI_MODE" = true ]; then
  TARGET_BIN_DIR="$HOME/.local/bin"
  mkdir -p "$TARGET_BIN_DIR"
  TARGET_CLI="$TARGET_BIN_DIR/arsenal"

  echo -e "${YELLOW}[+] Installing 'arsenal' CLI into: $TARGET_CLI${NC}"
  rm -f "$TARGET_CLI"
  ln -s "$CLI_BIN" "$TARGET_CLI"
  chmod +x "$TARGET_CLI"

  echo -e "${GREEN}[SUCCESS] 'arsenal' CLI installed!${NC}"
  if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo -e "${YELLOW}[TIP] Add ~/.local/bin to your PATH by adding this line to ~/.bashrc or ~/.zshrc:${NC}"
    echo '      export PATH="$HOME/.local/bin:$PATH"'
  fi
  echo -e "You can now run: ${CYAN}arsenal sync${NC}, ${CYAN}arsenal link .${NC}, or ${CYAN}arsenal status${NC}"
fi

# 3. Project Installation Mode
if [ -n "$PROJECT_PATH" ]; then
  if [ ! -d "$PROJECT_PATH" ]; then
    echo -e "${RED}Error: Target project directory '$PROJECT_PATH' not found.${NC}"
    exit 1
  fi

  TARGET_PROJECT="$(cd "$PROJECT_PATH" && pwd)"
  TARGET_AGENTS="$TARGET_PROJECT/.agents"
  TARGET_AGENTS_MD="$TARGET_PROJECT/AGENTS.md"

  echo -e "${YELLOW}[+] Installing into Project: $TARGET_PROJECT${NC}"

  if [ "$SYMLINK_MODE" = true ]; then
    rm -rf "$TARGET_AGENTS" "$TARGET_AGENTS_MD"
    ln -s "$SOURCE_AGENTS" "$TARGET_AGENTS"
    ln -s "$SOURCE_AGENTS_MD" "$TARGET_AGENTS_MD"
    echo -e "${GREEN}[SUCCESS] Symlinked .agents and AGENTS.md into $TARGET_PROJECT${NC}"
  else
    rm -rf "$TARGET_AGENTS" "$TARGET_AGENTS_MD"
    cp -r "$SOURCE_AGENTS" "$TARGET_AGENTS"
    cp "$SOURCE_AGENTS_MD" "$TARGET_AGENTS_MD"
    echo -e "${GREEN}[SUCCESS] Copied .agents and AGENTS.md into $TARGET_PROJECT${NC}"
  fi
fi

# 4. Status Check Mode
if [ "$STATUS_MODE" = true ]; then
  GLOBAL_CONFIG="$HOME/.gemini/config"
  echo -e "${CYAN}=== Active Global Arsenal Status ($GLOBAL_CONFIG) ===${NC}"
  if [ -d "$GLOBAL_CONFIG/skills" ]; then
    echo -e "${YELLOW}Skills installed:${NC}"
    for s in "$GLOBAL_CONFIG/skills/"*; do
      [ -d "$s" ] && echo "  - $(basename "$s")"
    done
  fi
  if [ -d "$GLOBAL_CONFIG/rules" ]; then
    echo -e "\n${YELLOW}Rules installed:${NC}"
    for r in "$GLOBAL_CONFIG/rules/"*.md; do
      [ -f "$r" ] && echo "  - $(basename "$r")"
    done
  fi
fi
