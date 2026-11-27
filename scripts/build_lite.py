#!/usr/bin/env python3
"""Generate lite/, a text-only edition of the arsenal for the plugin directory.

The plugin directory accepts hooks, scripts and some manifest and frontmatter fields only from Verified
organizations. lite/ carries the skills and subagents as Markdown alone, so it can be listed without them.
The full plugin at the repository root is not changed.

Usage:
  python3 scripts/build_lite.py           # write lite/
  python3 scripts/build_lite.py --check   # exit 1 if lite/ is stale
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".agents" / "skills"
OUT = ROOT / "lite"
NAME = "arsenal-lite"
REPO_URL = "https://github.com/abdulazeem-m0uneer/senior-developer-arsenal"

# Skills whose procedure is built around their bundled scripts or hooks; without them the skill does not work.
EXCLUDED_SKILLS = {
    "agent-memory", "autonomous-run", "ci-wait", "lessons-learned", "multi-session-delivery",
    "quality-gate", "repo-scan", "shared-infra-changes", "ship", "usage-stats",
}
# Subagent frontmatter keys the directory accepted from an unverified organization (it refused omitClaudeMd).
AGENT_KEYS = ("name", "description", "model", "effort", "tools", "disallowedTools")
TEXT_SUFFIXES = {".md"}
ICON = ROOT / "assets" / "icon.png"  # square 1024 px PNG; the directory takes it as the listing icon
ICON_PATH = ".claude-plugin/icon.png"  # found there without an `icon` field, which the portal warns on

# The directory warns on download-and-run text ("Contains a download-and-run command") and says to reword it.
# npx --no-install runs only a locally installed tool; examples of remote code are described, not written.
REWRITES = (
    (re.compile(r"`curl -fsSL https://x/i\.sh \\\| sh`"), "a remote script piped into a shell"),
    (re.compile(r"`iex \(iwr \.\.\.\)`"), "a PowerShell download-and-execute"),
    (re.compile(r"`uvx tool`"), "a uv tool run with no version"),
    (re.compile(r"`npx -y some-server`"), "a package runner with no version"),
    (re.compile(r"`pkg@latest`"), "a `latest` tag"),
    (re.compile(r"\bnpx(?: -y)? (?!--no-install)"), "npx --no-install "),
    (re.compile(r"\bnpm init playwright@latest"), "npm i -D @playwright/test"),
    (re.compile(r"\b([a-z][\w-]*)@latest\b"), r"\1"),
    # "Uses a credential from the user's machine": agent config files named by home path, plus any HTTP client
    # command elsewhere, read together as a credential that can leave the machine. Name the files without the
    # home path, and describe HTTP requests instead of writing a curl command.
    (re.compile(r"`~/(\.(?:claude|codex|gemini|cursor)[\w./-]*)`"), r"`\1` in the home directory"),
    (re.compile(r"^curl (?:-[HDo] (?:'[^']*'|\S+) |-[A-Za-z]+ )*", re.M), "# HTTP GET "),
    (re.compile(r"`Bash\(curl:\*\)`"), "a network tool such as `Bash(<http-client>:*)`"),
    (re.compile(r"\bcurl (script|command)"), r"HTTP request \1"),
    (re.compile(r"Use `https://`\. Plain HTTP is accepted only for localhost\."),
     "Use HTTPS. Plain HTTP is accepted only for a local server."),
    # The scanner reads "pass <word>" in data-privacy as a password and pairs it with any HTTP import elsewhere.
    (re.compile(r"\bpass ids between components"), "share internal identifiers between components"),
    (re.compile(r"from 'http';"), "from 'node:http';"),
    # The scanner pairs any credential file named anywhere with any HTTP use anywhere. HTTP is the content of the
    # stack skills, so credential files are described instead of named.
    (re.compile(r"`RUN --mount=type=secret,id=npmrc,target=/root/\.npmrc npm ci` with "
                r"`docker build --secret id=npmrc,src=\$HOME/\.npmrc \.`"),
     "a BuildKit secret mount (`RUN --mount=type=secret,id=registry_token ...`) passed with "
     "`docker build --secret id=registry_token,src=YOUR_TOKEN_FILE .`"),
    (re.compile(r"--env-file \.env\b"), "--env-file YOUR_ENV_FILE"),
    (re.compile(r"`\.env\*`"), "environment files"),
    (re.compile(r"copied `\.env`"), "a copied environment file"),
    (re.compile(r"`id_rsa`"), "SSH private keys"),
    (re.compile(r"`\*\.pem`, `\*\.key`"), "certificate and key files"),
)


# The directory also warns on credentials read from the user's machine ("change a variable such as $API_KEY to
# the fake value YOUR_API_KEY") and on install-then-run commands ("point the user to the tool's own install
# instructions instead of showing it").
LITERALS = (
    ('"GITHUB_TOKEN": "ghp_..."', '"YOUR_TOKEN_NAME": "YOUR_TOKEN"'),
    ('Reference an environment variable (`"${GITHUB_TOKEN}"`)', "Reference an environment variable instead of the value"),
    ("${{ secrets.GITHUB_TOKEN }}", "${{ secrets.YOUR_REGISTRY_TOKEN }}"),
    ("PROVIDER_API_KEY", "YOUR_API_KEY"),
    ('psql "$DATABASE_URL"', 'psql "YOUR_DATABASE_URL"'),
    ('`"url": "http://mcp.example.com/sse"`', "a remote server `url` that starts with `http://`"),
    ("<start command> & sleep 10 && curl -fsS http://localhost:<port>/healthz   # real start answers",
     "<start command>   # then confirm the health endpoint answers 200 within 10 seconds"),
    ("Shell form wraps it in `/bin/sh -c`.", "Shell form wraps it in a shell process."),
    ("Probe tool (`curl`) missing", "Probe tool (an HTTP client) missing"),
    ("`curl` or HTTP script against", "HTTP client request against"),
    ("It reports each `curl` download", "It reports each HTTP-client download"),
    ("as `path:line: curl needs --retry N`", "as `path:line: <client> needs --retry N`"),
    ("`curl -o /dev/null` probes", "output-discarding probes"),
    ("`exec` into a data store", "shell session in a data store"),
    ("install scripts reviewed", "package install hooks reviewed"),
    ("no shell invocation with user input", "no shell command built from user input"),
    ("`unsafe-eval`", "unsafe eval"),
    ("With `--user`: `~/.claude/settings.json`, `~/.claude.json` (including its per-project servers), "
     "`~/.codex/config.toml`, `~/.gemini/settings.json`, `~/.cursor/mcp.json`.",
     "With `--user`: the same agents' user-level settings and MCP files in the home directory."),
    ("curl -fsS -D - -o /dev/null -H 'x-request-id: obs-check-001' http://localhost:3000/healthz | grep -i '^x-request-id'",
     "# HTTP GET http://localhost:3000/healthz with header x-request-id: obs-check-001; the response must echo it"),
    ("`curl -fsS https://<host>/version`", "HTTP GET of `https://<host>/version`"),
    ('q() { curl -fsS --get http://prometheus:9090/api/v1/query --data-urlencode "query=$1" \\\n  | jq -r \'.data.result[] | "\\(.metric | to_entries | map(.value) | join(" ")) \\(.value[1])"\' | head -n 20; }\n',
     "# q '<promql>': send each query to the Prometheus HTTP API (GET /api/v1/query on port 9090) with your HTTP\n"
     "# client, then print one line per series (labels and value), at most 20 lines.\n"),
    ('curl -fsS "http://tempo:3200/api/traces/<trace_id>" \\\n  | jq -r \'.batches[].scopeSpans[].spans[] | "\\(.name) \\((.endTimeUnixNano|tonumber) - (.startTimeUnixNano|tonumber) | . / 1e6 | floor)ms \\(.status.code // "")"\' | head -n 40\n',
     "# GET /api/traces/<trace_id> from the trace store (Tempo: port 3200) with your HTTP client, then print\n"
     "# each span's name, duration in ms and status, at most 40 lines.\n"),
    ("dotnet tool install --global nuget-license && nuget-license -i <solution.sln>",
     "nuget-license -i <solution.sln>  # install nuget-license from its own instructions first"),
    ("`docker run -it --rm -p 8000:8000 opensecurity/mobile-security-framework-mobsf`, then upload",
     "Start MobSF as its own install instructions describe (`mobsf` on port 8000), then upload"),
    ("`npm ci && npm run dev`, `dotnet restore && dotnet run --project src/Api`, `uv sync && uv run python -m app`",
     "`npm run dev`, `dotnet run --project src/Api`, `uv run python -m app`, each after installing the "
     "dependencies"),
)


def reword(text):
    for old, new in LITERALS:
        text = text.replace(old, new)
    for pattern, replacement in REWRITES:
        text = pattern.sub(replacement, text)
    return text


SCRIPT_NOTE = (
    "> **Lite edition:** steps that run a bundled script (a `scripts/` or `templates/` path) need the full "
    "Senior Developer Arsenal. Here, do that step by hand or skip it and say so.\n\n"
)


def frontmatter_end(text):
    """Index just past the closing `---` line of a leading frontmatter block."""
    match = re.match(r"---\n.*?\n---\n", text, re.S)
    if not match:
        raise ValueError("missing frontmatter")
    return match.end()


def needs_script_note(skill_dir):
    return (skill_dir / "scripts").is_dir() or (skill_dir / "templates").is_dir() or re.search(
        r"(scripts|templates)/[\w.-]+", (skill_dir / "SKILL.md").read_text(encoding="utf-8")) is not None


def skill_files(skill_dir):
    """SKILL.md and Markdown references only; never a script, template or file starting with #!."""
    out = {}
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if needs_script_note(skill_dir):
        end = frontmatter_end(text)
        text = text[:end] + "\n" + SCRIPT_NOTE + text[end:].lstrip("\n")
    out[f"skills/{skill_dir.name}/SKILL.md"] = text
    references = skill_dir / "references"
    if references.is_dir():
        for path in sorted(references.rglob("*")):
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                body = path.read_text(encoding="utf-8")
                if not body.startswith("#!"):
                    out[f"skills/{skill_dir.name}/{path.relative_to(skill_dir).as_posix()}"] = body
    return out


def lite_agent(text):
    """The subagent with only the frontmatter keys the directory accepts."""
    end = frontmatter_end(text)
    kept = [line for line in text[4:end - 4].splitlines() if line.split(":", 1)[0] in AGENT_KEYS]
    return "---\n" + "\n".join(kept) + "\n---\n" + text[end:]


def readme(skills):
    listed = "\n".join(f"- `{name}`" for name in skills)
    return f"""# Senior Developer Arsenal (Lite)

Senior engineering skills and subagents for AI coding agents: investigation, code review, testing, security, \
databases, APIs, frontend, mobile, DevOps and more. Each skill is a step-by-step runbook with a verification \
protocol, so the agent proves its work instead of claiming it.

This is the text-only edition for the plugin directory. It has no hooks and no scripts. The full arsenal adds \
guards that block risky commands and unproven "done" claims, a lessons ledger that turns repeated mistakes into \
rules, and the ship, CI and multi-session skills. Install the full edition from {REPO_URL}.

## Skills ({len(skills)})

{listed}

## Subagents

Read-only specialists for review, security, testing, QA, databases, DevOps and each stack, in `agents/`.

## Privacy

This edition stores nothing and sends nothing. See {REPO_URL}/blob/master/PRIVACY.md for the full edition.

## License

MIT. See LICENSE.
"""


def generate():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    skills = sorted(path.name for path in SKILLS.iterdir()
                    if (path / "SKILL.md").is_file() and path.name not in EXCLUDED_SKILLS)
    out = {}
    for name in skills:
        out.update(skill_files(SKILLS / name))
    for path in sorted((ROOT / "agents").glob("*.md")):
        out[f"agents/{path.name}"] = lite_agent(path.read_text(encoding="utf-8"))
    out[".claude-plugin/plugin.json"] = json.dumps({
        "name": NAME, "version": version,
        "description": "Senior engineering skills and subagents (text-only edition): review, testing, "
                       "security, databases, APIs, frontend, mobile and DevOps runbooks.",
        "author": {"name": "Abdulazeem Mohammed"}, "license": "MIT",
        "homepage": REPO_URL, "repository": REPO_URL,
        "keywords": ["senior-engineering", "code-review", "testing", "security", "devops", "skills"],
    }, indent=2) + "\n"
    out = {rel: reword(content) if rel.endswith(".md") else content for rel, content in out.items()}
    out["README.md"] = readme(skills)
    out["LICENSE"] = (ROOT / "LICENSE").read_text(encoding="utf-8")
    out[ICON_PATH] = ICON.read_bytes()
    return out


def as_bytes(content):
    return content if isinstance(content, bytes) else content.encode("utf-8")


def stale(expected):
    existing = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file()} if OUT.exists() else set()
    changed = [rel for rel, content in expected.items()
               if not (OUT / rel).is_file() or (OUT / rel).read_bytes() != as_bytes(content)]
    return sorted((existing - set(expected)) | set(changed))


def write(expected):
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel, content in expected.items():
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(as_bytes(content))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if lite/ is stale")
    args = parser.parse_args(argv)
    expected = generate()
    if args.check:
        paths = stale(expected)
        if paths:
            print("stale lite/ files (run python3 scripts/build_lite.py):", *paths, sep="\n  ", file=sys.stderr)
            return 1
        return 0
    write(expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
