#!/usr/bin/env python3
"""
Senior Developer Arsenal - UI/UX Anti-Slop Verification Gate
Scans UI files, templates, components, and stylesheets against objective quality gates.
Usage:
  python scripts/verify_ui_ux.py [path]
"""

import sys
import os
import re
import argparse

# Common Unicode emoji ranges
EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F]|"  # emoticons
    r"[\U0001F300-\U0001F5FF]|"  # symbols & pictographs
    r"[\U0001F680-\U0001F6FF]|"  # transport & map
    r"[\U0001F1E0-\U0001F1FF]|"  # flags
    r"[\U00002702-\U000027B0]|"  # dingbats
    r"[\U0001F900-\U0001F9FF]|"  # supplemental symbols
    r"[\U0001FA70-\U0001FAFF]"   # symbols extended
)

# AI Copywriting Tells
BANNED_WORDS = [
    r"\belevate\b",
    r"\bseamless(?:ly)?\b",
    r"\bsupercharge\b",
    r"\bunlock(?:ing)?\s+your\b",
    r"\beffortless(?:ly)?\b",
    r"\bin today's fast-paced\b",
    r"\bempower(?:ing)?\b"
]
BANNED_WORDS_PATTERN = re.compile("|".join(BANNED_WORDS), re.IGNORECASE)

# Em-dash check
EM_DASH_PATTERN = re.compile(r"[\u2014\u2013]")

# Hardcoded hex colors (flags hex outside token definitions or CSS variables)
HEX_COLOR_PATTERN = re.compile(r"(?<!var\()#[0-9a-fA-F]{3,8}\b")

# Dangerous actions using primary/blue styling
BLUE_DELETE_PATTERN = re.compile(
    r"(?:delete|remove|revoke|destroy|cancel-account).*?(?:btn-primary|bg-blue|bg-indigo|color:\s*blue)",
    re.IGNORECASE
)

TARGET_EXTENSIONS = {
    ".html", ".htm", ".tsx", ".jsx", ".vue", ".svelte",
    ".razor", ".xaml", ".css", ".scss", ".less"
}

IGNORE_DIRS = {
    ".git", "node_modules", "bin", "obj", "dist", "build",
    ".system_generated", "coverage", ".next", ".nuget"
}

def scan_file(file_path):
    violations = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Unable to read file: {e}"]

    for idx, line in enumerate(lines, start=1):
        # 1. Emoji Gate
        emojis = EMOJI_PATTERN.findall(line)
        if emojis:
            violations.append(
                f"{file_path}:{idx} [Gate 1: Zero-Emoji] Found Unicode emoji: {', '.join(emojis)}"
            )

        # 2. Em-Dash Gate
        if EM_DASH_PATTERN.search(line):
            violations.append(
                f"{file_path}:{idx} [Gate 8: Anti-AI Copy] Found em-dash / en-dash in UI copy"
            )

        # 3. Marketing Buzzwords Gate
        buzz = BANNED_WORDS_PATTERN.findall(line)
        if buzz:
            violations.append(
                f"{file_path}:{idx} [Gate 8: Anti-AI Copy] Found banned marketing buzzword: {', '.join(buzz)}"
            )

        # 4. Intent Check
        if BLUE_DELETE_PATTERN.search(line):
            violations.append(
                f"{file_path}:{idx} [Gate 2: Intent Tokens] Destructive action styled with primary/blue instead of danger"
            )

    return violations

def main():
    parser = argparse.ArgumentParser(description="Verify UI against Senior Developer Arsenal Anti-Slop Gates")
    parser.add_argument("target", nargs="?", default=".", help="Directory or file to scan (default: current directory)")
    args = parser.parse_args()

    target_path = os.path.abspath(args.target)
    if not os.path.exists(target_path):
        print(f"Error: Target path '{target_path}' does not exist.")
        sys.exit(1)

    all_violations = []
    files_scanned = 0

    if os.path.isfile(target_path):
        files_to_scan = [target_path]
    else:
        files_to_scan = []
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in TARGET_EXTENSIONS:
                    files_to_scan.append(os.path.join(root, file))

    for fpath in files_to_scan:
        files_scanned += 1
        violations = scan_file(fpath)
        all_violations.extend(violations)

    print("==================================================")
    print("   UI/UX Anti-Slop Verification Gate Report")
    print("==================================================")
    print(f"Target:        {target_path}")
    print(f"Files Scanned: {files_scanned}")
    print(f"Violations:    {len(all_violations)}")
    print("--------------------------------------------------")

    if all_violations:
        for v in all_violations:
            print(f"[-] {v}")
        print("--------------------------------------------------")
        print("[FAIL] UI/UX anti-slop verification failed. Resolve violations above.")
        sys.exit(1)
    else:
        print("[PASS] All files passed zero-emoji, intent, and anti-AI copywriting gates!")
        sys.exit(0)

if __name__ == "__main__":
    main()
