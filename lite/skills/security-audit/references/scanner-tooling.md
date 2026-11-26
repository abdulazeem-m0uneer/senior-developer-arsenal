# Optional Scanners

Run a scanner only when it is already installed (`command -v <tool>`). If it is missing, continue the manual audit and state in the report which scanner was not run. A scanner hit is a lead, not a finding: trace it to an attacker-controlled source as in Step 2 before reporting it.

Dynamic tools (anything that sends requests) run only against a local or dev environment the user owns or has written permission to test. Never point them at production or a third-party host.

| Tool | Use when | Command |
| :--- | :--- | :--- |
| graudit | Quick grep-based sink sweep across many languages, before the Step 2 search | `graudit -d <db> -c 1 <path>` (db: `sql`, `exec`, `xss`, `js`, `python`, `dotnet`) |
| semgrep | Rule-based static scan with data flow, when the repo has no SAST in CI | `semgrep scan --config p/owasp-top-ten --error <path>` |
| sqlmap | Confirm a suspected SQL injection on one dev endpoint | `sqlmap -u '<dev-url>?id=1' -p id --batch --level 2 --risk 1` |
| sslscan | Check TLS versions and ciphers of a host the user owns | `sslscan <host>:443` |
| vulnhuntr | Python repo with LLM or agent code: trace remote input to dangerous calls | `vulnhuntr -r <repo> -a <entry-file>` |

Done when each scanner that ran has every hit traced to a finding or dismissed with a reason, and each one that was not run is named in the report.
