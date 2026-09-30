<#
.SYNOPSIS
    Installs Senior Developer Arsenal skills and rules into a target project or globally for Antigravity.

.DESCRIPTION
    Options:
    -Global: Copies/links skills and rules into ~/.gemini/config/ so they are available across ALL projects.
    -Project <path>: Installs .agents/ and AGENTS.md directly into the specified project root directory.
    -Symlink: Creates symbolic links instead of copying (requires Developer Mode or Administrator privileges).

.EXAMPLE
    .\install.ps1 -Global
    .\install.ps1 -Project "C:\repos\my-dotnet-api"
    .\install.ps1 -Project "C:\repos\my-node-service" -Symlink
#>

[CmdletBinding()]
param (
    [Parameter(Mandatory = $false)]
    [switch]$Global,

    [Parameter(Mandatory = $false)]
    [string]$Project,

    [Parameter(Mandatory = $false)]
    [switch]$Symlink,

    [Parameter(Mandatory = $false)]
    [switch]$Hindsight,

    [Parameter(Mandatory = $false)]
    [switch]$CodeGraph
)

$ArsenalRoot = $PSScriptRoot
$SourceAgents = Join-Path $ArsenalRoot ".agents"
$SourceAgentsMd = Join-Path $ArsenalRoot "AGENTS.md"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   Senior Developer Arsenal Installer" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path $SourceAgents)) {
    Write-Error "Source directory '$SourceAgents' does not exist!"
    exit 1
}

# 1. Global Installation Mode
if ($Global) {
    $GlobalConfigDir = Join-Path $env:USERPROFILE ".gemini\config"
    $GlobalSkillsDir = Join-Path $GlobalConfigDir "skills"
    $GlobalRulesDir = Join-Path $GlobalConfigDir "rules"
    $GlobalWorkflowsDir = Join-Path $GlobalConfigDir "workflows"

    Write-Host "[+] Installing globally into: $GlobalConfigDir" -ForegroundColor Yellow

    if (-not (Test-Path $GlobalSkillsDir)) {
        New-Item -ItemType Directory -Path $GlobalSkillsDir -Force | Out-Null
    }
    if (-not (Test-Path $GlobalRulesDir)) {
        New-Item -ItemType Directory -Path $GlobalRulesDir -Force | Out-Null
    }
    if (-not (Test-Path $GlobalWorkflowsDir)) {
        New-Item -ItemType Directory -Path $GlobalWorkflowsDir -Force | Out-Null
    }

    # Remove stale duplicate skills if present in global directory
    $StaleSkills = @("senior-code-review", "root-cause-investigator", "skill-writer")
    foreach ($stale in $StaleSkills) {
        $stalePath = Join-Path $GlobalSkillsDir $stale
        if (Test-Path $stalePath) {
            Remove-Item -Path $stalePath -Recurse -Force
        }
    }

    # Copy Skills (Modern Agent Skills standard)
    $Skills = Get-ChildItem -Path (Join-Path $SourceAgents "skills") -Directory
    foreach ($skill in $Skills) {
        $target = Join-Path $GlobalSkillsDir $skill.Name
        Write-Host "  -> Installing skill: $($skill.Name)" -ForegroundColor Green
        Copy-Item -Path $skill.FullName -Destination $target -Recurse -Force
    }

    # Copy Rules
    $Rules = Get-ChildItem -Path (Join-Path $SourceAgents "rules") -Filter "*.md"
    foreach ($rule in $Rules) {
        $target = Join-Path $GlobalRulesDir $rule.Name
        Write-Host "  -> Installing rule: $($rule.Name)" -ForegroundColor Green
        Copy-Item -Path $rule.FullName -Destination $target -Force
    }

    # Archive any legacy unmigrated .md workflows in global directory to .md.bak
    if (Test-Path $GlobalWorkflowsDir) {
        Get-ChildItem -Path $GlobalWorkflowsDir -Filter "*.md" | ForEach-Object {
            $bakTarget = $_.FullName + ".bak"
            Move-Item -Path $_.FullName -Destination $bakTarget -Force
        }
    }

    Write-Host "`n[SUCCESS] Global installation completed! All 22 modern skills and 11 rules are active across Antigravity." -ForegroundColor Green
}

# 2. Project Installation Mode
if ($Project) {
    if (-not (Test-Path $Project)) {
        Write-Error "Target project path '$Project' does not exist."
        exit 1
    }

    $TargetProject = (Resolve-Path $Project).Path
    Write-Host "[+] Installing into Project: $TargetProject" -ForegroundColor Yellow

    $TargetAgents = Join-Path $TargetProject ".agents"
    $TargetAgentsMd = Join-Path $TargetProject "AGENTS.md"

    if ($Symlink) {
        Write-Host "  -> Creating live link for .agents directory..." -ForegroundColor Cyan
        if (Test-Path $TargetAgents) { Remove-Item -Path $TargetAgents -Recurse -Force }
        try {
            New-Item -ItemType Junction -Path $TargetAgents -Target $SourceAgents -ErrorAction Stop | Out-Null
        } catch {
            New-Item -ItemType SymbolicLink -Path $TargetAgents -Target $SourceAgents | Out-Null
        }

        Write-Host "  -> Creating live link for AGENTS.md..." -ForegroundColor Cyan
        if (Test-Path $TargetAgentsMd) { Remove-Item -Path $TargetAgentsMd -Force }
        try {
            New-Item -ItemType HardLink -Path $TargetAgentsMd -Target $SourceAgentsMd -ErrorAction Stop | Out-Null
        } catch {
            New-Item -ItemType SymbolicLink -Path $TargetAgentsMd -Target $SourceAgentsMd | Out-Null
        }
    } else {
        Write-Host "  -> Copying .agents directory..." -ForegroundColor Cyan
        Copy-Item -Path $SourceAgents -Destination $TargetAgents -Recurse -Force

        Write-Host "  -> Copying AGENTS.md..." -ForegroundColor Cyan
        Copy-Item -Path $SourceAgentsMd -Destination $TargetAgentsMd -Force
    }

    Write-Host "`n[SUCCESS] Project installation completed for '$TargetProject'!" -ForegroundColor Green
}

# 3. Optional Hindsight MCP Configuration
if ($Hindsight) {
    Write-Host "[+] Configuring Hindsight MCP Memory Server..." -ForegroundColor Yellow
    $McpConfigDir = Join-Path $env:USERPROFILE ".gemini\antigravity"
    if (-not (Test-Path $McpConfigDir)) {
        New-Item -ItemType Directory -Path $McpConfigDir -Force | Out-Null
    }
    $McpConfigFile = Join-Path $McpConfigDir "mcp.json"

    $McpData = @{
        mcpServers = @{}
    }

    if (Test-Path $McpConfigFile) {
        try {
            $RawJson = Get-Content -Path $McpConfigFile -Raw
            if ($RawJson.Trim().Length -gt 0) {
                $McpData = ConvertFrom-Json $RawJson -AsHashtable
                if (-not $McpData.ContainsKey("mcpServers")) {
                    $McpData["mcpServers"] = @{}
                }
            }
        } catch {
            Write-Warning "Failed to parse existing mcp.json; creating new structure."
        }
    }

    $McpData["mcpServers"]["hindsight"] = @{
        command = "npx"
        args = @("-y", "@vectorize-io/hindsight-mcp")
        env = @{
            HINDSIGHT_BASE_URL = "http://localhost:8888"
            HINDSIGHT_BANK_ID = if ($Project) { Split-Path $Project -Leaf } else { "senior-developer-arsenal" }
        }
    }

    $UpdatedJson = ConvertTo-Json $McpData -Depth 10
    Set-Content -Path $McpConfigFile -Value $UpdatedJson -Encoding UTF8
    Write-Host "  -> Registered 'hindsight' in $McpConfigFile" -ForegroundColor Green
    Write-Host "[SUCCESS] Hindsight MCP server successfully configured!" -ForegroundColor Green
}

# 4. Optional CodeGraph MCP Configuration
if ($CodeGraph) {
    Write-Host "[+] Configuring CodeGraph MCP Intelligence Server..." -ForegroundColor Yellow
    $McpConfigDir = Join-Path $env:USERPROFILE ".gemini\antigravity"
    if (-not (Test-Path $McpConfigDir)) {
        New-Item -ItemType Directory -Path $McpConfigDir -Force | Out-Null
    }
    $McpConfigFile = Join-Path $McpConfigDir "mcp.json"

    $McpData = @{
        mcpServers = @{}
    }

    if (Test-Path $McpConfigFile) {
        try {
            $RawJson = Get-Content -Path $McpConfigFile -Raw
            if ($RawJson.Trim().Length -gt 0) {
                $McpData = ConvertFrom-Json $RawJson -AsHashtable
                if (-not $McpData.ContainsKey("mcpServers")) {
                    $McpData["mcpServers"] = @{}
                }
            }
        } catch {
            Write-Warning "Failed to parse existing mcp.json; creating new structure."
        }
    }

    $TargetDir = if ($Project) { (Resolve-Path $Project).Path } else { (Get-Location).Path }
    $McpData["mcpServers"]["codegraph"] = @{
        command = "npx"
        args = @("-y", "@colbymchenry/codegraph", "serve")
        env = @{
            CODEGRAPH_ROOT = $TargetDir
        }
    }

    $UpdatedJson = ConvertTo-Json $McpData -Depth 10
    Set-Content -Path $McpConfigFile -Value $UpdatedJson -Encoding UTF8
    Write-Host "  -> Registered 'codegraph' in $McpConfigFile (Root: $TargetDir)" -ForegroundColor Green
    Write-Host "[SUCCESS] CodeGraph MCP server successfully configured!" -ForegroundColor Green
}

if (-not $Global -and -not $Project -and -not $Hindsight -and -not $CodeGraph) {
    Write-Host "No action specified. Run with:" -ForegroundColor White
    Write-Host "  .\install.ps1 -Global                      # Installs for all projects on this machine" -ForegroundColor Gray
    Write-Host "  .\install.ps1 -Project <path-to-project>   # Installs into a specific project" -ForegroundColor Gray
    Write-Host "  .\install.ps1 -Project <path> -Symlink     # Links directly to this repository" -ForegroundColor Gray
    Write-Host "  .\install.ps1 -Hindsight                   # Configures Hindsight MCP memory server" -ForegroundColor Gray
    Write-Host "  .\install.ps1 -CodeGraph                   # Configures CodeGraph AST intelligence server" -ForegroundColor Gray
}
