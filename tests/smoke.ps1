<#
.SYNOPSIS
    Smoke tests for install.ps1. Runs every target against a throwaway home and project.
    Works on Windows PowerShell 5.1 and PowerShell 7+ (any OS). Exits non-zero on the first failure.
#>
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).ProviderPath
$Installer = Join-Path $Root "install.ps1"
$Shell = (Get-Process -Id $PID).Path
$Manifest = @(Import-Csv -LiteralPath (Join-Path (Join-Path $Root "dist") "manifest.tsv") -Delimiter "`t")
$Targets = @("antigravity", "gemini", "claude", "codex", "opencode", "cursor", "windsurf", "copilot")
$BeginMarker = "<!-- BEGIN senior-developer-arsenal -->"
$Work = Join-Path ([System.IO.Path]::GetTempPath()) ("arsenal-smoke-" + [System.Guid]::NewGuid().ToString("N"))
$HomeDir = Join-Path $Work "home"
$ProjectDir = Join-Path $Work "proj"
$script:Passed = 0
$script:Output = ""

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        Write-Host $script:Output
        Write-Host "FAIL: $Message" -ForegroundColor Red
        Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
        exit 1
    }
}

function Complete-Test([string]$Name) { $script:Passed++; Write-Host "ok - $Name" }

function Reset-Sandbox {
    if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force }
    New-Item -ItemType Directory -Path $HomeDir, $ProjectDir -Force | Out-Null
    # install.ps1 prefers USERPROFILE; HOME stays untouched so PowerShell's own cache lands elsewhere.
    $env:USERPROFILE = $HomeDir
}

# Runs install.ps1 in a child process; returns its exit code and stores its output.
function Invoke-Installer {
    $script:Output = (& $Shell -NoProfile -ExecutionPolicy Bypass -File $Installer @args 2>&1 | Out-String)
    return $LASTEXITCODE
}

function Get-Entries([string]$Path) {
    return @(Get-ChildItem -LiteralPath $Path -Recurse -Force)
}

function Assert-Installed([string]$TargetName, [string]$Scope, [string]$Base) {
    $rows = $Manifest | Where-Object { $_.target -eq $TargetName -and $_.scope -eq $Scope -and @("dir", "file", "block") -contains $_.kind }
    foreach ($row in $rows) {
        $path = Join-Path $Base $row.destination
        if ($row.kind -eq "block") {
            Assert-True ((Test-Path -LiteralPath $path) -and ([System.IO.File]::ReadAllText($path).Contains($BeginMarker))) "$TargetName/${Scope}: no arsenal block in $($row.destination)"
        } else {
            Assert-True (Test-Path -LiteralPath $path) "$TargetName/${Scope}: missing $($row.destination)"
        }
    }
}

$SkillCount = @(Get-ChildItem -LiteralPath (Join-Path (Join-Path $Root ".agents") "skills") -Directory).Count

foreach ($name in $Targets) {
    Reset-Sandbox
    $code = Invoke-Installer -Global -Project $ProjectDir -Target $name
    Assert-True ($code -eq 0) "${name}: install exited $code"
    Assert-Installed $name "global" $HomeDir
    Assert-Installed $name "project" $ProjectDir
    Assert-True ($script:Output -match "skipped 0") "${name}: unexpected skips"
    Invoke-Installer -Global -Project $ProjectDir -Target $name | Out-Null
    Assert-True ($script:Output -match "Installed 0,") "${name}: second run is not idempotent"
    Invoke-Installer -Global -Project $ProjectDir -Target $name -Uninstall | Out-Null
    Assert-True (((Get-Entries $HomeDir).Count + (Get-Entries $ProjectDir).Count) -eq 0) "${name}: uninstall left files behind"
    Complete-Test "${name}: install, idempotent re-run, uninstall"
}

Reset-Sandbox
Invoke-Installer -Global | Out-Null
$antigravitySkills = Join-Path (Join-Path (Join-Path $HomeDir ".gemini") "config") "skills"
Assert-True (@(Get-ChildItem -LiteralPath $antigravitySkills -Directory).Count -eq $SkillCount) "default target did not install all $SkillCount skills"
Assert-True (-not (Test-Path -LiteralPath (Join-Path $HomeDir ".agents"))) "default target must only touch Antigravity paths"
Complete-Test "default target is antigravity and installs all $SkillCount skills"

Reset-Sandbox
$skills = Join-Path (Join-Path $ProjectDir ".agents") "skills"
New-Item -ItemType Directory -Path (Join-Path $skills "code-review"), (Join-Path $skills "my-skill") -Force | Out-Null
[System.IO.File]::WriteAllText((Join-Path (Join-Path $skills "code-review") "SKILL.md"), "user version")
[System.IO.File]::WriteAllText((Join-Path (Join-Path $skills "my-skill") "SKILL.md"), "user skill")
$agentsMd = Join-Path $ProjectDir "AGENTS.md"
[System.IO.File]::WriteAllText($agentsMd, "# My project`r`n`r`nKeep me.`r`n")
Invoke-Installer -Project $ProjectDir -Target codex | Out-Null
Assert-True ([System.IO.File]::ReadAllText((Join-Path (Join-Path $skills "code-review") "SKILL.md")) -eq "user version") "overwrote a user skill without -Force"
Assert-True (Test-Path -LiteralPath (Join-Path (Join-Path $skills "my-skill") "SKILL.md")) "deleted an unrelated user skill"
$merged = [System.IO.File]::ReadAllText($agentsMd)
Assert-True ($merged.Contains("Keep me.") -and $merged.Contains($BeginMarker)) "AGENTS.md lost user content or has no arsenal block"
Assert-True (-not ($merged -replace "`r`n", "").Contains("`n")) "AGENTS.md line endings were not preserved"
Assert-True ($script:Output -match "skipped 1") "did not report the skipped skill"
Invoke-Installer -Project $ProjectDir -Target codex -Force | Out-Null
Assert-True ([System.IO.File]::ReadAllText((Join-Path (Join-Path $skills "code-review") "SKILL.md")) -match "name: code-review") "-Force did not replace the skill"
Invoke-Installer -Project $ProjectDir -Target codex -Uninstall | Out-Null
Assert-True ([System.IO.File]::ReadAllText($agentsMd) -eq "# My project`r`n`r`nKeep me.`r`n") "uninstall did not restore AGENTS.md"
Assert-True (Test-Path -LiteralPath (Join-Path (Join-Path $skills "my-skill") "SKILL.md")) "uninstall deleted an unrelated user skill"
Complete-Test "user files survive install, -Force replaces, uninstall restores"

Reset-Sandbox
Invoke-Installer -Project $ProjectDir -Target "codex,cursor" | Out-Null
Invoke-Installer -Project $ProjectDir -Target codex -Uninstall | Out-Null
Assert-True (Test-Path -LiteralPath (Join-Path (Join-Path (Join-Path $ProjectDir ".agents") "skills") "code-review")) "uninstalling one target removed a path another target shares"
Assert-True (-not (Test-Path -LiteralPath (Join-Path $ProjectDir ".codex"))) "uninstall left codex-only files"
Complete-Test "shared paths survive uninstalling one of two targets"

Reset-Sandbox
$sourceSkill = Join-Path (Join-Path (Join-Path $Root ".agents") "skills") "code-review"
$before = @(Get-ChildItem -LiteralPath $sourceSkill -Recurse -File).Count
Invoke-Installer -Project $ProjectDir -Target antigravity -Symlink | Out-Null
$linked = Get-Item -LiteralPath (Join-Path (Join-Path (Join-Path $ProjectDir ".agents") "skills") "code-review") -Force
Assert-True ([bool]$linked.LinkType) "-Symlink did not create a link for the skill folder"
Invoke-Installer -Project $ProjectDir -Target antigravity -Uninstall | Out-Null
Assert-True (@(Get-ChildItem -LiteralPath $sourceSkill -Recurse -File).Count -eq $before) "removing a link deleted files in the arsenal repository"
Assert-True ((Get-Entries $ProjectDir).Count -eq 0) "uninstall left linked files behind"
Complete-Test "-Symlink links per item and uninstall never follows links"

Reset-Sandbox
Invoke-Installer -Global -DryRun -Target all | Out-Null
Assert-True ((Get-Entries $HomeDir).Count -eq 0) "-DryRun changed the filesystem"
Complete-Test "-DryRun changes nothing"

Reset-Sandbox
$cursorMcp = Join-Path (Join-Path $HomeDir ".cursor") "mcp.json"
$codexToml = Join-Path (Join-Path $HomeDir ".codex") "config.toml"
New-Item -ItemType Directory -Path (Split-Path -Parent $cursorMcp), (Split-Path -Parent $codexToml) -Force | Out-Null
[System.IO.File]::WriteAllText($cursorMcp, '{"mcpServers": {"mine": {"command": "x", "args": ["one"]}}, "other": 1}')
[System.IO.File]::WriteAllText($codexToml, "[mcp_servers.mine]`ncommand = `"x`"`n")
$code = Invoke-Installer -Target "cursor,codex" -CodeGraph -Hindsight -Bank my-bank
Assert-True ($code -eq 0) "MCP registration exited $code"
$cursor = [System.IO.File]::ReadAllText($cursorMcp) | ConvertFrom-Json
Assert-True ($cursor.other -eq 1 -and $cursor.mcpServers.mine.command -eq "x") "existing MCP content was lost"
Assert-True ($cursor.mcpServers.mine.args -is [array] -and $cursor.mcpServers.mine.args.Count -eq 1) "a single-element array was flattened"
Assert-True ($cursor.mcpServers.codegraph.command -eq "codegraph" -and ($cursor.mcpServers.codegraph.args -join " ") -eq "serve --mcp") "codegraph entry is wrong"
Assert-True ($cursor.mcpServers.hindsight.url -eq "http://localhost:8888/mcp/my-bank/") "hindsight entry is wrong"
$toml = [System.IO.File]::ReadAllText($codexToml)
Assert-True ($toml.Contains("[mcp_servers.mine]") -and $toml.Contains("[mcp_servers.codegraph]") -and $toml.Contains('url = "http://localhost:8888/mcp/my-bank/"')) "codex TOML merge is wrong"
Assert-True (@(Get-ChildItem -LiteralPath (Split-Path -Parent $cursorMcp) -Filter "mcp.json.bak-*").Count -eq 1) "no backup of the existing MCP config"
Invoke-Installer -Target "cursor,codex" -CodeGraph | Out-Null
Assert-True (([regex]::Matches($script:Output, "unchanged")).Count -eq 2) "MCP registration is not idempotent"
Complete-Test "MCP servers merge into existing JSON and TOML configs"

Reset-Sandbox
New-Item -ItemType Directory -Path (Split-Path -Parent $cursorMcp) -Force | Out-Null
[System.IO.File]::WriteAllText($cursorMcp, "{ not json")
$code = Invoke-Installer -Target cursor -CodeGraph
Assert-True ($code -ne 0) "invalid MCP config did not fail the run"
Assert-True ([System.IO.File]::ReadAllText($cursorMcp) -eq "{ not json") "invalid MCP config was overwritten"
Complete-Test "an unparseable MCP config is left untouched and fails the run"

Reset-Sandbox
Assert-True ((Invoke-Installer -Target cursor -Hindsight -Bank "a'b") -ne 0) "unsafe bank id accepted"
Assert-True ((Invoke-Installer -Global -Target nope) -ne 0) "unknown target accepted"
Assert-True ((Invoke-Installer -Project (Join-Path $Work "missing")) -ne 0) "missing project accepted"
Assert-True ((Invoke-Installer -Project $Root) -ne 0) "installing into the arsenal itself accepted"
Complete-Test "invalid input is rejected"

Reset-Sandbox
$legacy = Join-Path (Join-Path (Join-Path $HomeDir ".gemini") "antigravity") "mcp.json"
New-Item -ItemType Directory -Path (Split-Path -Parent $legacy) -Force | Out-Null
Invoke-Installer -Target antigravity -CodeGraph | Out-Null
Assert-True (-not (Test-Path -LiteralPath $legacy)) "created the legacy Antigravity MCP file"
[System.IO.File]::WriteAllText($legacy, "{}")
Invoke-Installer -Target antigravity -CodeGraph | Out-Null
Assert-True ([System.IO.File]::ReadAllText($legacy).Contains("codegraph")) "did not update the existing legacy Antigravity MCP file"
Complete-Test "legacy Antigravity MCP file is updated only when present"

Remove-Item -LiteralPath $Work -Recurse -Force
Write-Host "all $($script:Passed) smoke tests passed"
