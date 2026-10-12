# Additions-Only Guardrails

Inventory record, ownership classes, marker conventions, the single data file, the frozen-file check, and the planted cases that keep the guard honest.

---

## 1. Inventory Record

One row per item that exists before the change. Commit it as the baseline (tab-separated or JSON, sorted, no secret values).

| Field | Example | Why it is kept |
| :--- | :--- | :--- |
| Kind | `dns_record` / `bucket` / `oidc_client` | Decides which marker field exists |
| Name | `mail.example.com` | The key the guard refuses to reuse |
| Type and value | `MX 10 mx1.example.net` | Lets the post-apply comparison detect an edit |
| Depends on it | Company email | Tells the reviewer what breaks |
| Owner | Platform team lead | Whose written word is needed to touch it |
| Class | `theirs` / `ours` / `unknown` | `unknown` is handled as `theirs` |
| Exported at | `2025-03-02T10:14Z` by a read-only token | A stale baseline is re-exported, not trusted |

Rules:
- Export with a read-only credential. An inventory command that can write is not an inventory command.
- The owner confirms the export once; after that the baseline changes only in a reviewed pull request.
- Account-wide settings, rulesets, and features belong to the account owner. Enabling one is their act, never part of an addition.

---

## 2. Marker Conventions

Every addition says who added it and for which environment, where the next person will look.

| Resource has | Put the marker in | Example |
| :--- | :--- | :--- |
| A comment field (DNS records, firewall rules) | The comment | `added by <person or team> - staging` |
| Tags or labels (cloud resources, cluster objects) | Two tags | `added-by=<team>`, `environment=production` |
| A description (identity-provider clients, policies) | The description | `added by <team> - staging` |
| None of these (bucket names, some queues) | The name | `tfstate-added-by-<team>-staging` |

- One fixed spelling, checked by a regular expression: `^added by .+ - (staging|production)$`. Free text is not a marker.
- The marker is written by the frozen module, not typed per entry, so an entry cannot omit it.
- "Ours" means "carries the marker". The post-apply comparison removes marked items and expects the rest to equal the baseline.

---

## 3. The Single Data File

```json
[
  { "name": "api-staging", "environment": "staging", "target": "203.0.113.10", "addedBy": "platform-team" },
  { "name": "docs-staging", "environment": "staging", "target": "203.0.113.10", "addedBy": "platform-team" }
]
```

The provisioning code loops over this file and nothing else is editable:

```hcl
locals { records = jsondecode(file("${path.module}/records.json")) }

module "record" {
  source      = "./modules/record"            # frozen: writes the marker comment itself
  for_each    = { for r in local.records : r.name => r }
  name        = each.value.name
  target      = each.value.target
  environment = each.value.environment
  added_by    = each.value.addedBy
}
```

Validate the data as data. Do not parse the provisioning language to find violations: every hand-written parser of it gets walked around (a nested brace, a quote inside an interpolation).

| Rule on an entry | Refuses |
| :--- | :--- |
| Name is one lowercase label: letters, digits, inner hyphens (`^[a-z0-9-]+$`, no hyphen at either end) | Apex (`@`, empty), wildcards, dotted names, trailing dots, upper case, spaces |
| Name is not in the baseline | Taking over or sharing a name someone else serves |
| Name is unique in the file | Two entries fighting for one record |
| Environment is in the fixed list | A typo that produces an unmarked item |
| Production-reserved names are refused until cut-over | An early addition that splits live traffic |
| Keys are exactly the known set | A smuggled field the module would pass through |

---

## 4. Freezing Everything Else

```python
import hashlib, json, pathlib, sys

ROOT = pathlib.Path("infra/shared")
DATA = {"records.json", "baseline.tsv"}
frozen = json.loads(pathlib.Path("infra/frozen.json").read_text())

seen = {}
for path in ROOT.rglob("*"):
    rel = path.relative_to(ROOT).as_posix()
    if path.is_file() and ".terraform/" not in rel and rel not in DATA:
        seen[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

problems = [f"changed or new: {p}" for p in seen if frozen.get(p) != seen[p]]
problems += [f"removed: {p}" for p in frozen if p not in seen]
sys.exit("\n".join(problems) if problems else 0)
```

- The list covers the lock file, provider versions, modules, and state backend settings. A new file fails too: an extra file is the easiest way round a check.
- Changing a frozen file on purpose is allowed. The checksum line in the diff is the statement "what may be added to the live system has changed", and the reviewer treats it as such.
- Policy-as-code (OPA/Conftest, Sentinel, provider organisation policies) can replace or back the checksum; the rule it enforces is the same.

---

## 5. Planted Cases

Each bypass ever found becomes a case the gate runs first: mutate a copy of the real configuration and assert the check refuses it.

| Planted case | Must be refused with |
| :--- | :--- |
| Entry named like an existing baseline record | "exists in the baseline" |
| Entry `*`, `@`, `API`, `api.`, ` api`, `a.b` | "one lowercase label" |
| Frozen module edited to drop the marker | "changed or new" |
| New `.tf` file with a second provider or an `import` block | "changed or new" |
| Data file with an unknown extra key | "unknown key" |

- A case that changes nothing must fail loudly. A pattern that silently stops matching turns the case into a pass that proves nothing.
- If the planted cases fail, stop: the real check's green result is worthless until they are refused again.
