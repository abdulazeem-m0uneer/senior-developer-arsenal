<#
.SYNOPSIS
    Installs Senior Developer Arsenal skills, subagents, rules and MCP servers for any supported AI agent.

.DESCRIPTION
    Mirrors install.sh. Works on Windows PowerShell 5.1 and PowerShell 7+.

    -Global            Install into your user profile.
    -Project <path>    Install into a project repository.
    -Target <list>     Agents: antigravity (default), gemini, claude, codex, opencode, cursor, windsurf, copilot, all.
    -Symlink           Link instead of copy (junctions for folders; file links need Developer Mode or admin).
    -Force             Replace existing files that this installer did not create.
    -Uninstall         Remove what this installer created for the chosen targets.
    -DryRun            Print actions without changing anything.
    -Status            Show what is installed for the chosen targets.
    -Hindsight         Register the Hindsight memory MCP server.
    -CodeGraph         Register the CodeGraph MCP server.
    -Bank <id>         Hindsight bank id (default: project folder name).
    -Cli               Install the 'arsenal' command into ~\.local\bin.

.EXAMPLE
    .\install.ps1 -Global -Target all
    .\install.ps1 -Project "C:\repos\my-api" -Target claude,cursor -Symlink
    .\install.ps1 -Global -Target codex -CodeGraph
#>

[CmdletBinding()]
param (
    [switch]$Global,
    [string]$Project,
    [string[]]$Target = @("antigravity"),
    [Alias("Link")][switch]$Symlink,
    [switch]$Force,
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$Status,
    [switch]$Hindsight,
    [switch]$CodeGraph,
    [string]$Bank,
    [switch]$Cli
)

$ErrorActionPreference = "Stop"

$ArsenalRoot = (Resolve-Path -LiteralPath $PSScriptRoot).ProviderPath
$ManifestPath = Join-Path (Join-Path $ArsenalRoot "dist") "manifest.tsv"
$AllTargets = @("antigravity", "gemini", "claude", "codex", "opencode", "cursor", "windsurf", "copilot")
$BlockBegin = "<!-- BEGIN senior-developer-arsenal -->"
$BlockEnd = "<!-- END senior-developer-arsenal -->"
$IsWindowsHost = ($env:OS -eq "Windows_NT")
$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$script:Installed = 0
$script:Unchanged = 0
$script:Skipped = 0
$script:Removed = 0
$script:Failed = $false

function Write-Info([string]$Message) { Write-Host "[+] $Message" -ForegroundColor Yellow }
function Write-Skip([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow; $script:Skipped++ }
function Stop-Install([string]$Message) { Write-Host "Error: $Message" -ForegroundColor Red; exit 1 }

# --- Resolve targets, scopes and inputs -----------------------------------------
$Targets = @()
foreach ($requested in ($Target | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    if ($requested -eq "all") { $Targets = $AllTargets; break }
    if ($AllTargets -notcontains $requested) {
        Stop-Install "Unknown target '$requested'. Valid: $($AllTargets -join ', '), all."
    }
    $Targets += $requested
}
if ($Targets.Count -eq 0) { Stop-Install "-Target requires at least one agent." }

$ProjectRoot = ""
if ($Project) {
    if (-not (Test-Path -LiteralPath $Project -PathType Container)) {
        Stop-Install "Target project directory '$Project' not found."
    }
    $ProjectRoot = (Resolve-Path -LiteralPath $Project).ProviderPath.TrimEnd("\", "/")
    if ($ProjectRoot -eq $ArsenalRoot.TrimEnd("\", "/")) {
        Stop-Install "Refusing to install the arsenal into its own repository."
    }
}

if (-not $Bank) {
    $Bank = if ($ProjectRoot) { Split-Path -Leaf $ProjectRoot } else { "senior-developer-arsenal" }
}
if ($Bank -notmatch "^[A-Za-z0-9._-]+$") {
    Stop-Install "Bank id '$Bank' may only contain letters, digits, '.', '_' and '-' (use -Bank)."
}

$McpMode = ($Hindsight -or $CodeGraph)
$InstallFiles = ($Global -or [bool]$ProjectRoot)
$Scopes = @()
if ($Global) { $Scopes += "global" }
if ($ProjectRoot) { $Scopes += "project" }
# MCP registration, status and uninstall default to the global scope.
if ($Scopes.Count -eq 0 -and ($McpMode -or $Status -or $Uninstall)) { $Scopes += "global" }

if ($Scopes.Count -eq 0 -and -not $Cli) {
    Get-Help $PSCommandPath
    exit 0
}
if ($Scopes.Count -gt 0 -and -not (Test-Path -LiteralPath $ManifestPath)) {
    Stop-Install "Missing dist/manifest.tsv. Run: python3 scripts/build.py"
}
$Manifest = @()
if ($Scopes.Count -gt 0) { $Manifest = @(Import-Csv -LiteralPath $ManifestPath -Delimiter "`t") }

# --- Helpers ----------------------------------------------------------------------
function Get-ScopeBase([string]$Scope) {
    if ($Scope -eq "global") { return $UserHome }
    return $ProjectRoot
}

function Get-StatePath([string]$Scope) {
    if ($Scope -eq "global") {
        return Join-Path (Join-Path (Join-Path $UserHome ".config") "senior-developer-arsenal") "manifest"
    }
    return Join-Path (Join-Path $ProjectRoot ".agents") ".arsenal-manifest"
}

function Get-ManifestRows([string]$TargetName, [string]$Scope) {
    return @($Manifest | Where-Object { $_.target -eq $TargetName -and $_.scope -eq $Scope })
}

function Get-StateLines([string]$StatePath) {
    if (-not (Test-Path -LiteralPath $StatePath)) { return @() }
    return @([System.IO.File]::ReadAllLines($StatePath) | Where-Object { $_ })
}

function Test-Recorded([string]$StatePath, [string]$Destination, [string]$TargetName) {
    foreach ($line in (Get-StateLines $StatePath)) {
        $parts = $line -split "`t", 2
        if ($parts[1] -eq $Destination -and (-not $TargetName -or $parts[0] -eq $TargetName)) { return $true }
    }
    return $false
}

function Write-TextFile([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Add-StateRecord([string]$StatePath, [string]$TargetName, [string]$Destination) {
    if (Test-Recorded $StatePath $Destination $TargetName) { return }
    $lines = @(Get-StateLines $StatePath) + "$TargetName`t$Destination"
    Write-TextFile $StatePath (($lines -join "`n") + "`n")
}

function Remove-StateRecord([string]$StatePath, [string]$TargetName, [string]$Destination) {
    $lines = @(Get-StateLines $StatePath | Where-Object { $_ -ne "$TargetName`t$Destination" })
    if ($lines.Count -eq 0) {
        if (Test-Path -LiteralPath $StatePath) { [System.IO.File]::Delete($StatePath) }
        return
    }
    Write-TextFile $StatePath (($lines -join "`n") + "`n")
}

function Test-PathOrLink([string]$Path) {
    return [bool](Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue)
}

function Get-LinkTarget([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item -or -not $item.LinkType) { return $null }
    return [string](@($item.Target)[0])
}

function Test-LinksIntoArsenal([string]$Path) {
    $linkTarget = Get-LinkTarget $Path
    if (-not $linkTarget) { return $false }
    $root = $ArsenalRoot.TrimEnd("\", "/")
    return ($linkTarget -eq $root -or $linkTarget.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar))
}

# Deletes a path without following links (Remove-Item -Recurse can empty a junction's target on 5.1).
function Remove-PathSafely([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item) { return }
    if ($item.LinkType) {
        if ($item.PSIsContainer) { [System.IO.Directory]::Delete($Path, $false) } else { [System.IO.File]::Delete($Path) }
        return
    }
    Remove-Item -LiteralPath $Path -Recurse -Force
}

function Get-ContentSignature([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
    $root = (Resolve-Path -LiteralPath $Path).ProviderPath
    $entries = Get-ChildItem -LiteralPath $root -Recurse -File -Force | ForEach-Object {
        $_.FullName.Substring($root.Length).Replace("\", "/") + "=" + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
    return (@($entries) | Sort-Object) -join "|"
}

# True when the destination already holds exactly what this run would install.
function Test-Current([string]$Source, [string]$Path) {
    $linkTarget = Get-LinkTarget $Path
    if ($Symlink) { return ($linkTarget -eq $Source) }
    if ($linkTarget) { return $false }
    $sourceIsDirectory = Test-Path -LiteralPath $Source -PathType Container
    if ($sourceIsDirectory -ne (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    return ((Get-ContentSignature $Source) -eq (Get-ContentSignature $Path))
}

function Get-TextLines([string]$Path) {
    $text = [System.IO.File]::ReadAllText($Path)
    if ($text.Length -eq 0) { return @() }
    return @(($text -replace "`r`n", "`n").TrimEnd("`n") -split "`n")
}

function Get-BlockMarkerCounts([string[]]$Lines) {
    $begin = @($Lines | Where-Object { $_ -eq $BlockBegin }).Count
    $end = @($Lines | Where-Object { $_ -eq $BlockEnd }).Count
    return "$begin $end"
}

function Remove-Block([string[]]$Lines) {
    $kept = @()
    $skipping = $false
    foreach ($line in $Lines) {
        if ($line -eq $BlockBegin) { $skipping = $true; continue }
        if ($line -eq $BlockEnd) { $skipping = $false; continue }
        if (-not $skipping) { $kept += $line }
    }
    return (($kept -join "`n").TrimEnd())
}

function Get-LineEnding([string]$Path) {
    if ((Test-Path -LiteralPath $Path -PathType Leaf) -and [System.IO.File]::ReadAllText($Path).Contains("`r`n")) { return "`r`n" }
    return "`n"
}

function Remove-EmptyParents([string]$Path, [string]$Base) {
    $directory = Split-Path -Parent $Path
    $stop = $Base.TrimEnd("\", "/")
    while ($directory -and $directory.TrimEnd("\", "/") -ne $stop -and (Test-Path -LiteralPath $directory -PathType Container)) {
        if (@(Get-ChildItem -LiteralPath $directory -Force).Count -gt 0) { return }
        [System.IO.Directory]::Delete($directory, $false)
        $directory = Split-Path -Parent $directory
    }
}

# Older releases linked the whole .agents directory and AGENTS.md into the project.
function Remove-LegacyLinks {
    foreach ($legacy in @((Join-Path $ProjectRoot ".agents"), (Join-Path $ProjectRoot "AGENTS.md"))) {
        if (-not (Test-LinksIntoArsenal $legacy)) { continue }
        if ($DryRun) { Write-Host "[dry-run] would remove legacy link $legacy"; continue }
        Remove-PathSafely $legacy
        Write-Host "  -> Removed legacy link: $legacy" -ForegroundColor Green
    }
}

function New-Link([string]$Source, [string]$Path) {
    if (Test-Path -LiteralPath $Source -PathType Container) {
        $linkType = if ($IsWindowsHost) { "Junction" } else { "SymbolicLink" }
        New-Item -ItemType $linkType -Path $Path -Target $Source | Out-Null
        return
    }
    try {
        New-Item -ItemType SymbolicLink -Path $Path -Target $Source -ErrorAction Stop | Out-Null
    } catch {
        Write-Host "[WARN] Could not link $Path (enable Developer Mode or run as administrator); copied instead." -ForegroundColor Yellow
        Copy-Item -LiteralPath $Source -Destination $Path -Force
    }
}

function Install-Item([string]$TargetName, [string]$Scope, [string]$RelativeSource, [string]$Destination) {
    $source = Join-Path $ArsenalRoot $RelativeSource
    $statePath = Get-StatePath $Scope
    $path = Join-Path (Get-ScopeBase $Scope) $Destination
    if (-not (Test-Path -LiteralPath $source)) { Stop-Install "Missing source '$RelativeSource'. Run: python3 scripts/build.py" }

    if (Test-PathOrLink $path) {
        if (Test-Current $source $path) {
            if (-not $DryRun) { Add-StateRecord $statePath $TargetName $Destination }
            $script:Unchanged++
            return
        }
        if (-not $Force -and -not (Test-Recorded $statePath $Destination "") -and -not (Test-LinksIntoArsenal $path)) {
            Write-Skip "Skipped $path (exists and was not created by this installer; use -Force to replace)."
            return
        }
    }
    if ($DryRun) { Write-Host "[dry-run] would install $path"; return }
    Remove-PathSafely $path
    $parent = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    if ($Symlink) {
        New-Link $source $path
    } elseif (Test-Path -LiteralPath $source -PathType Container) {
        Copy-Item -LiteralPath $source -Destination $path -Recurse -Force
    } else {
        Copy-Item -LiteralPath $source -Destination $path -Force
    }
    Add-StateRecord $statePath $TargetName $Destination
    $script:Installed++
}

function Install-Block([string]$TargetName, [string]$Scope, [string]$RelativeSource, [string]$Destination) {
    $source = Join-Path $ArsenalRoot $RelativeSource
    $statePath = Get-StatePath $Scope
    $path = Join-Path (Get-ScopeBase $Scope) $Destination
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { Stop-Install "Missing source '$RelativeSource'. Run: python3 scripts/build.py" }

    $sourceLines = Get-TextLines $source
    $body = ""
    $existing = $null
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $existing = [System.IO.File]::ReadAllText($path)
        $lines = Get-TextLines $path
        $counts = Get-BlockMarkerCounts $lines
        if ($counts -ne "0 0" -and $counts -ne "1 1") {
            Write-Skip "Skipped $path (unbalanced arsenal block markers; fix the file manually)."
            return
        }
        # A file copied verbatim by an older release is replaced, not duplicated.
        if (($lines -join "`n") -ne ($sourceLines -join "`n")) { $body = Remove-Block $lines }
    } elseif (Test-PathOrLink $path) {
        Write-Skip "Skipped $path (not a regular file)."
        return
    }
    if ($DryRun) { Write-Host "[dry-run] would write the arsenal block in $path"; return }

    $newline = Get-LineEnding $path
    $output = @()
    if ($body) { $output += @($body -split "`n") + "" }
    $output += $BlockBegin
    $output += $sourceLines
    $output += $BlockEnd
    $text = ($output -join $newline) + $newline
    Add-StateRecord $statePath $TargetName $Destination
    if ($existing -ceq $text) { $script:Unchanged++; return }
    Write-TextFile $path $text
    $script:Installed++
}

function Test-BlockDestination([string]$Destination) {
    return [bool]($Manifest | Where-Object { $_.kind -eq "block" -and $_.destination -eq $Destination } | Select-Object -First 1)
}

function Uninstall-Item([string]$TargetName, [string]$Scope, [string]$Destination) {
    $base = Get-ScopeBase $Scope
    $statePath = Get-StatePath $Scope
    $path = Join-Path $base $Destination
    if ($DryRun) { Write-Host "[dry-run] would remove $path"; return }
    Remove-StateRecord $statePath $TargetName $Destination
    if (-not (Test-Path -LiteralPath $statePath)) { Remove-EmptyParents $statePath $base }
    # Another installed target still shares this path.
    if (Test-Recorded $statePath $Destination "") { return }
    if (Test-BlockDestination $Destination) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $lines = Get-TextLines $path
            if ((Get-BlockMarkerCounts $lines) -eq "1 1") {
                $newline = Get-LineEnding $path
                $remaining = Remove-Block $lines
                if ($remaining.Trim()) {
                    Write-TextFile $path ((($remaining -split "`n") -join $newline) + $newline)
                } else {
                    [System.IO.File]::Delete($path)
                }
            }
        }
    } else {
        Remove-PathSafely $path
    }
    Remove-EmptyParents $path $base
    $script:Removed++
}

# Removes everything recorded for a target, including items a newer manifest no longer lists.
function Uninstall-Target([string]$TargetName, [string]$Scope) {
    foreach ($line in (Get-StateLines (Get-StatePath $Scope))) {
        $parts = $line -split "`t", 2
        if ($parts[0] -eq $TargetName) { Uninstall-Item $TargetName $Scope $parts[1] }
    }
}

function Test-ServerEnabled([string]$Name) {
    return (($Name -eq "hindsight" -and $Hindsight) -or ($Name -eq "codegraph" -and $CodeGraph))
}

function Backup-File([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Copy-Item -LiteralPath $Path -Destination ("$Path.bak-" + (Get-Date -Format "yyyyMMddHHmmss")) -Force
    }
}

function Register-JsonServer([string]$Path, [string]$Key, [string]$Name, [string]$EntryText) {
    $entry = $EntryText | ConvertFrom-Json
    $data = New-Object PSObject
    $exists = Test-Path -LiteralPath $Path -PathType Leaf
    if ($exists -and (Get-Item -LiteralPath $Path).Length -gt 0) {
        try { $data = [System.IO.File]::ReadAllText($Path) | ConvertFrom-Json } catch { $data = $null }
    }
    $servers = $null
    if ($data -is [System.Management.Automation.PSCustomObject]) {
        $property = $data.PSObject.Properties[$Key]
        if (-not $property) {
            $servers = New-Object PSObject
            $data | Add-Member -MemberType NoteProperty -Name $Key -Value $servers
        } elseif ($property.Value -is [System.Management.Automation.PSCustomObject]) {
            $servers = $property.Value
        }
    }
    if (-not $servers) {
        Write-Host "Error: $Path is not valid JSON or '$Key' is not an object; file left untouched. Add this manually:" -ForegroundColor Red
        Write-Host "{ `"$Key`": { `"$Name`": $EntryText } }"
        $script:Failed = $true
        return
    }
    $current = $servers.PSObject.Properties[$Name]
    if ($current -and ((ConvertTo-Json $current.Value -Depth 64 -Compress) -eq (ConvertTo-Json $entry -Depth 64 -Compress))) {
        Write-Host "unchanged: '$Name' already registered in $Path"
        return
    }
    if ($DryRun) { Write-Host "[dry-run] would register '$Name' in $Path"; return }
    if ($current) { $servers.PSObject.Properties.Remove($Name) }
    $servers | Add-Member -MemberType NoteProperty -Name $Name -Value $entry
    Backup-File $Path
    Write-TextFile $Path ((ConvertTo-Json $data -Depth 64) + "`n")
    Write-Host "registered '$Name' in $Path"
}

function Register-TomlServer([string]$Path, [string]$Key, [string]$Name, [string]$EntryText) {
    $header = "[$Key.$Name]"
    $existing = ""
    if (Test-Path -LiteralPath $Path -PathType Leaf) { $existing = [System.IO.File]::ReadAllText($Path) }
    if ($existing.Contains($header)) { Write-Host "unchanged: '$Name' already registered in $Path"; return }
    if ($DryRun) { Write-Host "[dry-run] would register '$Name' in $Path"; return }
    Backup-File $Path
    $separator = if ($existing) { "`n" } else { "" }
    Write-TextFile $Path ($existing + $separator + $header + "`n" + ($EntryText -replace "`r`n", "`n"))
    Write-Host "registered '$Name' in $Path"
}

function Register-Mcp([string]$Scope, $Row) {
    $path = Join-Path (Get-ScopeBase $Scope) $Row.destination
    if ($Row.kind -eq "mcp-if-exists" -and -not (Test-Path -LiteralPath $path -PathType Leaf)) { return }
    $source = Join-Path $ArsenalRoot $Row.source
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { Stop-Install "Missing source '$($Row.source)'. Run: python3 scripts/build.py" }
    $key, $format = $Row.extra -split ":", 2
    $entryText = [System.IO.File]::ReadAllText($source).Replace("{{BANK_ID}}", $Bank)
    if ($format -eq "json") {
        Register-JsonServer $path $key $Row.name $entryText
    } else {
        Register-TomlServer $path $key $Row.name $entryText
    }
}

function Show-Status([string]$TargetName, [string]$Scope) {
    $base = Get-ScopeBase $Scope
    $present = 0
    $rows = @(Get-ManifestRows $TargetName $Scope | Where-Object { @("dir", "file", "block") -contains $_.kind })
    foreach ($row in $rows) {
        $path = Join-Path $base $row.destination
        if ($row.kind -eq "block") {
            if ((Test-Path -LiteralPath $path -PathType Leaf) -and ((Get-TextLines $path) -contains $BlockBegin)) { $present++ }
        } elseif (Test-PathOrLink $path) {
            $present++
        }
    }
    Write-Host ("  {0,-12} {1,-8} {2}/{3} items present" -f $TargetName, $Scope, $present, $rows.Count)
}

function Invoke-Target([string]$TargetName, [string]$Scope) {
    foreach ($row in (Get-ManifestRows $TargetName $Scope)) {
        switch ($row.kind) {
            { $_ -in "dir", "file" } { if ($InstallFiles) { Install-Item $TargetName $Scope $row.source $row.destination } }
            "block" { if ($InstallFiles) { Install-Block $TargetName $Scope $row.source $row.destination } }
            { $_ -in "mcp", "mcp-if-exists" } { if (Test-ServerEnabled $row.name) { Register-Mcp $Scope $row } }
            "mcp-note" { if (Test-ServerEnabled $row.name) { Write-Host "  note: $($row.extra)" -ForegroundColor Cyan } }
            "note" { if ($InstallFiles) { Write-Host "  note: $($row.extra)" -ForegroundColor Cyan } }
            default { Stop-Install "Unknown manifest row kind '$($row.kind)'. Update install.ps1 to match scripts/build.py." }
        }
    }
}

function Install-Cli {
    if (-not $IsWindowsHost) { Stop-Install "-Cli is for Windows; on Linux and macOS run: ./install.sh --cli" }
    $shim = Join-Path (Join-Path (Join-Path $UserHome ".local") "bin") "arsenal.cmd"
    $script = Join-Path (Join-Path $ArsenalRoot "scripts") "arsenal.ps1"
    $content = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$script`" %*`r`n"
    if ((Test-Path -LiteralPath $shim) -and -not $Force -and ([System.IO.File]::ReadAllText($shim) -ne $content)) {
        Write-Skip "Skipped $shim (exists; use -Force to replace)."
        return
    }
    if ($DryRun) { Write-Host "[dry-run] would write $shim"; return }
    Write-TextFile $shim $content
    Write-Host "  -> CLI installed: $shim (add its folder to PATH)" -ForegroundColor Green
}

# --- Main -------------------------------------------------------------------------
if ($Status) {
    Write-Host "=== Senior Developer Arsenal status ===" -ForegroundColor Cyan
    foreach ($scope in $Scopes) { foreach ($name in $Targets) { Show-Status $name $scope } }
    exit 0
}

foreach ($scope in $Scopes) {
    if ($scope -eq "project" -and -not $Uninstall -and $InstallFiles) { Remove-LegacyLinks }
    foreach ($name in $Targets) {
        Write-Info "$name ($scope): $(Get-ScopeBase $scope)"
        if ($Uninstall) { Uninstall-Target $name $scope } else { Invoke-Target $name $scope }
    }
}

if ($Cli) { Install-Cli }

Write-Host ""
if ($Uninstall) {
    Write-Host "[DONE] Removed $($script:Removed) item(s). MCP server entries are left in place." -ForegroundColor Green
} else {
    Write-Host "[DONE] Installed $($script:Installed), already current $($script:Unchanged), skipped $($script:Skipped)." -ForegroundColor Green
}
if ($script:Failed) { Stop-Install "One or more MCP configurations could not be updated (see messages above)." }
