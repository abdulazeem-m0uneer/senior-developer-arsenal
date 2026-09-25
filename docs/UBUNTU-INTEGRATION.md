# 🐧 Ubuntu & Linux Integration Guide

This guide walks you through integrating the **Senior Developer Arsenal** on **Ubuntu OS** (Native Desktop, Server, Virtual Machine, or WSL2).

---

## ⚡ 1-Minute Quick Start

### Scenario A: Ubuntu running natively (or dual-boot / separate machine)

1. **Clone the Arsenal Repository**:
   ```bash
   git clone https://github.com/your-username/senior-developer-arsenal.git ~/senior-developer-arsenal
   cd ~/senior-developer-arsenal
   ```

2. **Run the Installer with Global & CLI flags**:
   ```bash
   chmod +x install.sh scripts/arsenal
   ./install.sh --global --cli
   ```

3. **Reload your shell profile**:
   ```bash
   source ~/.bashrc   # or source ~/.zshrc
   ```

4. **Verify Active Arsenal**:
   ```bash
   arsenal status
   ```

---

### Scenario B: Ubuntu running via WSL2 on Windows

Because your repository is already located at `C:\Users\Abdulazeem\Desktop\senior-developer-arsenal`, your WSL2 Ubuntu can access it directly through the `/mnt/c/` filesystem:

1. **Open your Ubuntu Terminal in WSL**:
   ```bash
   cd /mnt/c/Users/Abdulazeem/Desktop/senior-developer-arsenal
   ```

2. **Install globally for your Ubuntu user and register the CLI**:
   ```bash
   chmod +x install.sh scripts/arsenal
   ./install.sh --global --cli
   ```

3. **Reload your profile**:
   ```bash
   source ~/.bashrc
   ```

Now, Antigravity running inside WSL2 will automatically load all rules and skills from `~/.gemini/config/`!

---

## 🛠️ The `arsenal` CLI Commands on Ubuntu

The installer registers a native `arsenal` CLI binary in `~/.local/bin/arsenal`. You can run these commands from **any directory** on your Ubuntu machine:

| Command | Purpose |
| :--- | :--- |
| `arsenal sync` *(or `arsenal global`)* | Deploys the latest skills, rules, and prompts into `~/.gemini/config/`. |
| `arsenal link [path]` | Creates live symbolic links (`.agents` and `AGENTS.md`) in the target project. Changes made in the arsenal automatically reflect in the project without re-copying. |
| `arsenal copy [path]` | Hard-copies `.agents` and `AGENTS.md` into the target project (ideal for air-gapped or isolated repositories). |
| `arsenal status` | Inspects and prints all active skills and rules currently registered in `~/.gemini/config/`. |
| `arsenal update` | Pulls the latest git commits from `master` and re-synchronizes `~/.gemini/config/` in one step. |

---

## 📂 Applying the Arsenal to an Ubuntu Project

When starting or working on any repository in Ubuntu (e.g. `~/projects/my-fastapi-app` or `~/projects/my-dotnet-service`):

```bash
# Navigate to your project directory
cd ~/projects/my-fastapi-app

# Symlink the arsenal into it
arsenal link .
```

This creates:
```text
my-fastapi-app/
├── .agents/   -> /path/to/senior-developer-arsenal/.agents
├── AGENTS.md  -> /path/to/senior-developer-arsenal/AGENTS.md
└── ...
```

---

## ⚙️ Shell Configuration (`.bashrc` / `.zshrc`)

The installer ensures `~/.local/bin` is used. If your shell does not already have it in PATH, add this line to your `~/.bashrc` or `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Optional convenience alias for rapid project linking:
```bash
alias alink="arsenal link ."
```

---

## 🔄 Keeping Ubuntu Synchronized

Whenever you update skills, add rules, or tweak prompts:
```bash
arsenal update
```
This ensures your Ubuntu workstation always runs with the latest token-saving guardrails, defensive epistemology, and polyglot runbooks.
