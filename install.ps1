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
    [switch]$Symlink
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

    Write-Host "[+] Installing globally into: $GlobalConfigDir" -ForegroundColor Yellow

    if (-not (Test-Path $GlobalSkillsDir)) {
        New-Item -ItemType Directory -Path $GlobalSkillsDir -Force | Out-Null
    }
    if (-not (Test-Path $GlobalRulesDir)) {
        New-Item -ItemType Directory -Path $GlobalRulesDir -Force | Out-Null
    }

    # Copy Skills
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

    Write-Host "`n[SUCCESS] Global installation completed! All projects in Antigravity will now load these skills." -ForegroundColor Green
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
        Write-Host "  -> Creating symbolic link for .agents directory..." -ForegroundColor Cyan
        if (Test-Path $TargetAgents) { Remove-Item -Path $TargetAgents -Recurse -Force }
        New-Item -ItemType SymbolicLink -Path $TargetAgents -Target $SourceAgents | Out-Null

        Write-Host "  -> Creating symbolic link for AGENTS.md..." -ForegroundColor Cyan
        if (Test-Path $TargetAgentsMd) { Remove-Item -Path $TargetAgentsMd -Force }
        New-Item -ItemType SymbolicLink -Path $TargetAgentsMd -Target $SourceAgentsMd | Out-Null
    } else {
        Write-Host "  -> Copying .agents directory..." -ForegroundColor Cyan
        Copy-Item -Path $SourceAgents -Destination $TargetAgents -Recurse -Force

        Write-Host "  -> Copying AGENTS.md..." -ForegroundColor Cyan
        Copy-Item -Path $SourceAgentsMd -Destination $TargetAgentsMd -Force
    }

    Write-Host "`n[SUCCESS] Project installation completed for '$TargetProject'!" -ForegroundColor Green
}

if (-not $Global -and -not $Project) {
    Write-Host "No action specified. Run with:" -ForegroundColor White
    Write-Host "  .\install.ps1 -Global                      # Installs for all projects on this machine" -ForegroundColor Gray
    Write-Host "  .\install.ps1 -Project <path-to-project>   # Installs into a specific project" -ForegroundColor Gray
    Write-Host "  .\install.ps1 -Project <path> -Symlink     # Links directly to this repository" -ForegroundColor Gray
}
