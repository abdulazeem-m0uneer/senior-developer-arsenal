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

# Deletes the sandbox without following links (Remove-Item -Recurse can empty a junction's target on 5.1).
function Remove-Sandbox {
    if (-not (Test-Path -LiteralPath $Work)) { return }
    foreach ($link in @(Get-ChildItem -LiteralPath $Work -Recurse -Force -Attributes ReparsePoint)) {
        if (-not (Get-Item -LiteralPath $link.FullName -Force -ErrorAction SilentlyContinue)) { continue }
        if ($link.PSIsContainer) { [System.IO.Directory]::Delete($link.FullName, $false) } else { [System.IO.File]::Delete($link.FullName) }
    }
    Remove-Item -LiteralPath $Work -Recurse -Force
}

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        Write-Host $script:Output
        Write-Host "FAIL: $Message" -ForegroundColor Red
        Remove-Sandbox
        exit 1
    }
}

function Complete-Test([string]$Name) { $script:Passed++; Write-Host "ok - $Name" }

function Reset-Sandbox {
    Remove-Sandbox
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

Reset-Sandbox
$spaced = Join-Path $Work "my proj"
New-Item -ItemType Directory -Path $spaced -Force | Out-Null
$code = Invoke-Installer -Project $spaced -Target cursor -Hindsight
Assert-True ($code -eq 0) "a project path with spaces was rejected"
$spacedMcp = [System.IO.File]::ReadAllText((Join-Path (Join-Path $spaced ".cursor") "mcp.json")) | ConvertFrom-Json
Assert-True ($spacedMcp.mcpServers.hindsight.url -eq "http://localhost:8888/mcp/my-proj/") "derived bank id was not sanitised"
Assert-True ((Invoke-Installer -Project $HomeDir -Target codex) -ne 0) "the home directory was accepted as a project"
Assert-True ((Invoke-Installer -Force) -ne 0) "options without a scope did not fail"
Complete-Test "paths with spaces work and the home directory is refused as a project"

Reset-Sandbox
$victim = Join-Path $Work "victim"
New-Item -ItemType Directory -Path $victim, (Join-Path $ProjectDir ".agents") -Force | Out-Null
[System.IO.File]::WriteAllText((Join-Path $victim "file"), "keep")
[System.IO.File]::WriteAllText((Join-Path $ProjectDir "user.txt"), "keep")
$records = "claude`t../victim`nclaude`t$victim`nclaude`nclaude`tsub/../../victim`n"
[System.IO.File]::WriteAllText((Join-Path (Join-Path $ProjectDir ".agents") ".arsenal-manifest"), $records)
Invoke-Installer -Project $ProjectDir -Target claude -Uninstall | Out-Null
Assert-True (Test-Path -LiteralPath (Join-Path $victim "file")) "uninstall followed a path outside the project"
Assert-True (Test-Path -LiteralPath (Join-Path $ProjectDir "user.txt")) "an empty record deleted the project"
Complete-Test "unsafe install records never delete anything"

Reset-Sandbox
$copy = Join-Path $Work "arsenal"
New-Item -ItemType Directory -Path $copy, (Join-Path $ProjectDir ".agents") -Force | Out-Null
foreach ($entry in @(".agents", "dist", "scripts", "install.ps1", "AGENTS.md")) {
    Copy-Item -LiteralPath (Join-Path $Root $entry) -Destination (Join-Path $copy $entry) -Recurse -Force
}
$copySkills = Join-Path (Join-Path $copy ".agents") "skills"
$linkType = if ($env:OS -eq "Windows_NT") { "Junction" } else { "SymbolicLink" }
New-Item -ItemType $linkType -Path (Join-Path (Join-Path $ProjectDir ".agents") "skills") -Target $copySkills | Out-Null
$copyInstaller = Join-Path $copy "install.ps1"
$before = @(Get-ChildItem -LiteralPath (Join-Path $copy ".agents") -Recurse -File -Force).Count
foreach ($arguments in @(@("-Force"), @("-Symlink", "-Force"), @("-Uninstall"))) {
    & $Shell -NoProfile -ExecutionPolicy Bypass -File $copyInstaller -Project $ProjectDir -Target codex @arguments 2>&1 | Out-Null
}
Assert-True (@(Get-ChildItem -LiteralPath (Join-Path $copy ".agents") -Recurse -File -Force).Count -eq $before) "a linked parent let the installer modify the arsenal repository"
Assert-True (-not (Get-Item -LiteralPath (Join-Path $copySkills "code-review") -Force).LinkType) "a source skill was replaced by a link to itself"
Complete-Test "a parent linked into the arsenal is never written to or deleted"

Reset-Sandbox
$reversed = "<!-- END senior-developer-arsenal -->`n<!-- BEGIN senior-developer-arsenal -->`nuser text after`n"
[System.IO.File]::WriteAllText($agentsMd, $reversed)
Invoke-Installer -Project $ProjectDir -Target windsurf | Out-Null
Assert-True ([System.IO.File]::ReadAllText($agentsMd) -ceq $reversed) "reversed block markers led to lost content on install"
Invoke-Installer -Project $ProjectDir -Target windsurf -Uninstall | Out-Null
Assert-True ([System.IO.File]::ReadAllText($agentsMd) -ceq $reversed) "reversed block markers led to lost content on uninstall"
Complete-Test "reversed block markers are left untouched"

Reset-Sandbox
$latin1 = [byte[]](0x43, 0x61, 0x66, 0xE9, 0x0A)
[System.IO.File]::WriteAllBytes($agentsMd, $latin1)
Invoke-Installer -Project $ProjectDir -Target windsurf | Out-Null
Assert-True (([System.IO.File]::ReadAllBytes($agentsMd) -join ",") -eq ($latin1 -join ",")) "a non-UTF-8 file was rewritten"
$withBom = [byte[]](0xEF, 0xBB, 0xBF) + [System.Text.Encoding]::UTF8.GetBytes("# Mine`n")
[System.IO.File]::WriteAllBytes($agentsMd, $withBom)
Invoke-Installer -Project $ProjectDir -Target windsurf | Out-Null
$written = [System.IO.File]::ReadAllBytes($agentsMd)
Assert-True ($written[0] -eq 0xEF -and $written[1] -eq 0xBB -and $written[2] -eq 0xBF -and $written.Length -gt $withBom.Length) "a UTF-8 BOM was not preserved"
Invoke-Installer -Project $ProjectDir -Target windsurf -Uninstall | Out-Null
Assert-True (([System.IO.File]::ReadAllBytes($agentsMd) -join ",") -eq ($withBom -join ",")) "uninstall did not restore the BOM file byte for byte"
Complete-Test "non-UTF-8 files are skipped and a UTF-8 BOM is preserved"

if ($env:OS -ne "Windows_NT") {
    Reset-Sandbox
    [System.IO.File]::WriteAllText($agentsMd, "# mine`n")
    New-Item -ItemType SymbolicLink -Path (Join-Path $ProjectDir "CLAUDE.md") -Target $agentsMd | Out-Null
    Invoke-Installer -Project $ProjectDir -Target claude | Out-Null
    Assert-True ([bool](Get-Item -LiteralPath (Join-Path $ProjectDir "CLAUDE.md") -Force).LinkType) "a linked CLAUDE.md was replaced"
    Assert-True (-not [System.IO.File]::ReadAllText($agentsMd).Contains("@AGENTS.md")) "the CLAUDE.md import was written through the link"
    Invoke-Installer -Project $ProjectDir -Target claude | Out-Null
    Assert-True ($script:Output -match "Installed 0,") "a linked block file makes re-runs unstable"
    Complete-Test "a linked instruction file is skipped, not replaced or written through"
}

Reset-Sandbox
$wrapper = Join-Path (Join-Path $Root "scripts") "arsenal.ps1"
& $wrapper copy $ProjectDir -Target codex,cursor 2>&1 | Out-Null
Assert-True (Test-Path -LiteralPath (Join-Path (Join-Path $ProjectDir ".cursor") "rules")) "the arsenal wrapper dropped the second target of a comma list"
Assert-True (Test-Path -LiteralPath (Join-Path (Join-Path $ProjectDir ".codex") "agents")) "the arsenal wrapper dropped the first target of a comma list"
Complete-Test "the arsenal wrapper keeps comma-separated target lists intact"

Remove-Sandbox
Write-Host "all $($script:Passed) smoke tests passed"
