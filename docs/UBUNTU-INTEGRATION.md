# 🐧 Ubuntu & Linux Integration Guide

This guide walks you through integrating the **Senior Developer Arsenal** on **Ubuntu OS** (native desktop, server, virtual machine, or WSL2). The same commands work on macOS.

---

## ⚡ 1-Minute Quick Start

1. **Clone the arsenal repository**:
   ```bash
   git clone https://github.com/abdulazeem-m0uneer/senior-developer-arsenal.git ~/senior-developer-arsenal
   cd ~/senior-developer-arsenal
   ```

2. **Install globally for the agents you use and register the CLI**:
   ```bash
   ./install.sh --global --cli --target all
   ```
   Omit `--target` to install for Antigravity only, or list agents: `--target claude,codex,cursor`.

3. **Reload your shell profile** (only needed if `~/.local/bin` was just added to PATH):
   ```bash
   source ~/.bashrc   # or source ~/.zshrc
   ```

4. **Verify**:
   ```bash
   arsenal status --target all
   ```

### WSL2 on Windows

A repository cloned on the Windows side is reachable under `/mnt/c/`. Run the same installer from there; it installs into your WSL user's home, so agents running inside WSL2 pick it up:

```bash
cd /mnt/c/path/to/senior-developer-arsenal
./install.sh --global --cli --target all
```

---

## 🛠️ The `arsenal` CLI Commands

The installer links `~/.local/bin/arsenal` to `scripts/arsenal`, a thin wrapper over `install.sh`. Any `install.sh` option may follow a command.

| Command | Purpose |
| :--- | :--- |
| `arsenal sync` *(or `arsenal global`)* | Installs skills, subagents, and rules globally. |
| `arsenal link [path]` | Symlinks each arsenal item into the target project, so arsenal updates apply without re-copying. |
| `arsenal copy [path]` | Copies the arsenal into the target project (ideal for air-gapped or isolated repositories). |
| `arsenal remove [path]` | Removes what the installer created in the project (`--global` for the global install). |
| `arsenal status` | Shows how many items are present per agent. |
| `arsenal update` | Pulls the latest commits and re-installs globally. |

Examples:

```bash
arsenal sync --target all
arsenal link . --target claude,cursor
arsenal remove . --target cursor
```

---

## 📂 Applying the Arsenal to a Project

```bash
cd ~/projects/my-fastapi-app
arsenal link . --target codex
```

This creates per-item links and a managed block, never replacing your own files:

```text
my-fastapi-app/
├── .agents/
│   ├── skills/<name>   -> /path/to/senior-developer-arsenal/.agents/skills/<name>
│   ├── rules/<rule>.md -> /path/to/senior-developer-arsenal/.agents/rules/<rule>.md
│   └── .arsenal-manifest          # what the installer owns (used by uninstall)
├── .codex/agents/<name>.toml -> /path/to/senior-developer-arsenal/dist/codex/agents/<name>.toml
└── AGENTS.md                      # your content, plus a marked arsenal block
```

Existing files that the installer did not create are skipped and reported; pass `--force` to replace them.

---

## ⚙️ Shell Configuration (`.bashrc` / `.zshrc`)

If your shell does not already have `~/.local/bin` in PATH, add:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Optional convenience alias:

```bash
alias alink="arsenal link ."
```

---

## 🔄 Keeping Synchronized

```bash
arsenal update --target all
```
