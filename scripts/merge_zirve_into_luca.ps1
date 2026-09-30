param(
    [string]$ZirveRoot = "Z:\Evrak Çantası\eDefter",
    [string]$LucaRoot = "Z:\Evrak Çantası\LucaEdefter",
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $ReportPath = Join-Path $PSScriptRoot "..\reports\zirve-luca-merge-$timestamp.json"
}

$excludedRootNames = @(
    ".silinenler",
    "SİLİNENLER",
    "Sonuc",
    "sch",
    "xsd",
    "xslt",
    "xsl_2.0",
    "zrv_tmp",
    "ELedgerSigner",
    "ELedgerUtils",
    "MaliMuhurHelper",
    "WebServiceHelper",
    "_GIBOnayliEDefterSaklama"
)

function Test-IsTaxIdDirectory {
    param([string]$Name)
    return $Name -match '^\d{10,11}$'
}

function Test-IsPeriodDirectory {
    param([string]$Name)
    return $Name -match '^\d{2}\.\d{2}\.\d{4}-\d{2}\.\d{2}\.\d{4}$'
}

function Get-TreeCounts {
    param([string]$Path)
    $files = (Get-ChildItem -LiteralPath $Path -Recurse -File -Force | Measure-Object).Count
    $dirs = (Get-ChildItem -LiteralPath $Path -Recurse -Directory -Force | Measure-Object).Count
    return @{
        fileCount = $files
        dirCount = $dirs
    }
}

function Copy-MissingTree {
    param(
        [string]$SourcePath,
        [string]$TargetPath,
        [hashtable]$Stats
    )

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        New-Item -ItemType Directory -Path $TargetPath | Out-Null
        $Stats.createdDirectories += 1
    }

    foreach ($item in Get-ChildItem -LiteralPath $SourcePath -Force) {
        $destination = Join-Path $TargetPath $item.Name
        if ($item.PSIsContainer) {
            if (-not (Test-Path -LiteralPath $destination)) {
                Copy-Item -LiteralPath $item.FullName -Destination $destination -Recurse
                $counts = Get-TreeCounts -Path $destination
                $Stats.createdDirectories += ($counts.dirCount + 1)
                $Stats.copiedFiles += $counts.fileCount
            }
            else {
                Copy-MissingTree -SourcePath $item.FullName -TargetPath $destination -Stats $Stats
            }
        }
        else {
            if (-not (Test-Path -LiteralPath $destination)) {
                Copy-Item -LiteralPath $item.FullName -Destination $destination
                $Stats.copiedFiles += 1
            }
            else {
                $Stats.skippedExistingFiles += 1
            }
        }
    }
}

$reportDirectory = Split-Path -Parent $ReportPath
if (-not (Test-Path -LiteralPath $reportDirectory)) {
    New-Item -ItemType Directory -Path $reportDirectory | Out-Null
}

$stats = @{
    scannedRoots = 0
    skippedSystemRoots = 0
    sourceTaxpayers = 0
    createdVknFolders = 0
    createdYearFolders = 0
    mergedYearFolders = 0
    copiedFiles = 0
    skippedExistingFiles = 0
    createdDirectories = 0
}

$operations = New-Object System.Collections.Generic.List[object]

$zirveRoots = Get-ChildItem -LiteralPath $ZirveRoot -Directory -Force
foreach ($root in $zirveRoots) {
    $stats.scannedRoots += 1
    if ($excludedRootNames -contains $root.Name) {
        $stats.skippedSystemRoots += 1
        continue
    }

    $taxDirectories = @()
    if (Test-IsTaxIdDirectory -Name $root.Name) {
        $taxDirectories = @($root)
    }
    else {
        $taxDirectories = @(Get-ChildItem -LiteralPath $root.FullName -Directory -Force | Where-Object {
            Test-IsTaxIdDirectory -Name $_.Name
        })
    }

    foreach ($taxDirectory in $taxDirectories) {
        $stats.sourceTaxpayers += 1
        $vkn = $taxDirectory.Name
        $targetVknPath = Join-Path $LucaRoot $vkn
        if (-not (Test-Path -LiteralPath $targetVknPath)) {
            New-Item -ItemType Directory -Path $targetVknPath | Out-Null
            $stats.createdVknFolders += 1
        }

        $periodDirectories = @(Get-ChildItem -LiteralPath $taxDirectory.FullName -Directory -Force | Where-Object {
            Test-IsPeriodDirectory -Name $_.Name
        })

        foreach ($periodDirectory in $periodDirectories) {
            $targetPeriodPath = Join-Path $targetVknPath $periodDirectory.Name
            $operation = [ordered]@{
                sourceRoot = $root.Name
                vkn = $vkn
                period = $periodDirectory.Name
                sourcePath = $periodDirectory.FullName
                targetPath = $targetPeriodPath
                action = ""
            }

            if (-not (Test-Path -LiteralPath $targetPeriodPath)) {
                Copy-Item -LiteralPath $periodDirectory.FullName -Destination $targetPeriodPath -Recurse
                $counts = Get-TreeCounts -Path $targetPeriodPath
                $stats.createdYearFolders += 1
                $stats.createdDirectories += ($counts.dirCount + 1)
                $stats.copiedFiles += $counts.fileCount
                $operation.action = "created_period"
            }
            else {
                $stats.mergedYearFolders += 1
                Copy-MissingTree -SourcePath $periodDirectory.FullName -TargetPath $targetPeriodPath -Stats $stats
                $operation.action = "merged_missing_content"
            }

            $operations.Add([pscustomobject]$operation)
        }
    }
}

$report = [ordered]@{
    createdAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    zirveRoot = $ZirveRoot
    lucaRoot = $LucaRoot
    stats = $stats
    operations = $operations
}

$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8

Write-Output "RAPOR=$ReportPath"
Write-Output ("KAYNAK_MUKELLEF=" + $stats.sourceTaxpayers)
Write-Output ("YENI_VKN=" + $stats.createdVknFolders)
Write-Output ("YENI_YIL=" + $stats.createdYearFolders)
Write-Output ("BIRLESTIRILEN_YIL=" + $stats.mergedYearFolders)
Write-Output ("KOPYALANAN_DOSYA=" + $stats.copiedFiles)
Write-Output ("ATLANAN_DOSYA=" + $stats.skippedExistingFiles)
