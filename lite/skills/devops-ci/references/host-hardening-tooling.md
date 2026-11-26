# Optional Host and TLS Checks

Run a tool only when it is already installed; otherwise say which check was not run. Target only hosts and images the user owns.

| Tool | Use when | Command |
| :--- | :--- | :--- |
| Lynis | Hardening audit of a VM or bare-metal host that runs the service | `sudo lynis audit system --quick`, then read the warnings in `/var/log/lynis-report.dat` |
| sslscan | After a TLS, ingress or certificate change | `sslscan <host>:443` (fail on TLS 1.0/1.1 or weak ciphers) |
| trivy | Scan the built image for known vulnerable packages before push | `trivy image --exit-code 1 --severity HIGH,CRITICAL <image>` |

Fix every warning that touches the deployed service, or list it with a reason.
