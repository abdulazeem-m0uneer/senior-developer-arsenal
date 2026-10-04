<#
.SYNOPSIS
    arsenal - Senior Developer Arsenal CLI for Windows (thin wrapper over install.ps1).

.EXAMPLE
    arsenal sync -Target all
    arsenal link . -Target claude,cursor
    arsenal remove . -Target cursor
#>
$ErrorActionPreference = "Stop"

$Installer = Join-Path (Split-Path -Parent $PSScriptRoot) "install.ps1"
$CommandName = if ($args.Count -gt 0) { [string]$args[0] } else { "help" }
$Rest = @()
if ($args.Count -gt 1) { $Rest = @($args[1..($args.Count - 1)]) }

function Show-Help {
    Write-Host @"
Usage: arsenal <command> [path] [install.ps1 options]

Commands:
  sync | global          Install globally (default target: antigravity)
  link [project_path]    Link into a project (default: current directory)
  copy [project_path]    Copy into a project (default: current directory)
  remove [project_path]  Uninstall from a project, or globally with -Global
  status                 Show what is installed
  update                 Pull the latest arsenal and re-sync globally
  help                   Show this help
"@
}

# Forwards to install.ps1 through a child process so -Switch tokens bind as parameters.
function Invoke-Installer([object[]]$Arguments) {
    $shell = (Get-Process -Id $PID).Path
    # "-Target a,b" arrives as an array; rejoin it so it stays one argument.
    $flattened = @($Arguments | ForEach-Object { if ($_ -is [array]) { $_ -join "," } else { $_ } })
    & $shell -NoProfile -ExecutionPolicy Bypass -File $Installer @flattened
    exit $LASTEXITCODE
}

# Splits "[path] [options...]" into the project path and the remaining options.
function Split-ProjectArguments([object[]]$Arguments) {
    if ($Arguments.Count -gt 0 -and -not ([string]$Arguments[0]).StartsWith("-")) {
        $remaining = @()
        if ($Arguments.Count -gt 1) { $remaining = @($Arguments[1..($Arguments.Count - 1)]) }
        return @{ Project = [string]$Arguments[0]; Options = $remaining }
    }
    return @{ Project = "."; Options = @($Arguments) }
}

switch ($CommandName) {
    { $_ -in "sync", "global" } { Invoke-Installer (@("-Global") + $Rest) }
    "link" {
        $parsed = Split-ProjectArguments $Rest
        Invoke-Installer (@("-Project", $parsed.Project, "-Symlink") + $parsed.Options)
    }
    "copy" {
        $parsed = Split-ProjectArguments $Rest
        Invoke-Installer (@("-Project", $parsed.Project) + $parsed.Options)
    }
    "remove" {
        if ($Rest -contains "-Global") { Invoke-Installer (@("-Uninstall") + $Rest) }
        $parsed = Split-ProjectArguments $Rest
        Invoke-Installer (@("-Project", $parsed.Project, "-Uninstall") + $parsed.Options)
    }
    "status" { Invoke-Installer (@("-Status") + $Rest) }
    "update" {
        $root = Split-Path -Parent $PSScriptRoot
        if (Test-Path -LiteralPath (Join-Path $root ".git")) {
            & git -C $root pull --ff-only
            if ($LASTEXITCODE -ne 0) { Write-Host "[WARN] git pull failed or the repository has local changes." -ForegroundColor Yellow }
        }
        Invoke-Installer (@("-Global") + $Rest)
    }
    { $_ -in "help", "--help", "-h" } { Show-Help }
    default {
        Write-Host "Unknown command: $CommandName" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
