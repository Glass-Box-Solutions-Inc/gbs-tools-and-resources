# compress_pdfs_ghostscript.ps1
# Aggressive PDF compression using Ghostscript
# Downloads Ghostscript if not installed

param(
    [string]$OutputFolder = "C:\4850 Law\_Compressed_GS",
    [ValidateSet("screen", "ebook", "printer", "prepress")]
    [string]$Quality = "ebook",  # screen=72dpi, ebook=150dpi, printer=300dpi
    [switch]$DryRun
)

$LargePDFs = @(
    @{
        Path = "C:\4850 Law\FLUKER JAN L_Case3201\INS PROPOSED LT DR TIRMIZI W- ECNLOSURES CLM 06235532, 03-19-2025.pdf"
        Case = "FLUKER JAN L"
        CaseID = 56171886
    },
    @{
        Path = "C:\4850 Law\WEBSTER CHRISTIAN V_Case3307\MED-LEGAL MRC'S- LAW OFFICES OF CHRISLIP & HERVATIN, 03-10-2021.pdf"
        Case = "WEBSTER CHRISTIAN V"
        CaseID = 56171914
    },
    @{
        Path = "C:\4850 Law\WEIDNER MICHAEL W_Case3364\POS- MEDICAL RECORDS- IRONWOOD PRIMARY CARE DATED 02-06-2025 (1).pdf"
        Case = "WEIDNER MICHAEL W"
        CaseID = 56171915
    },
    @{
        Path = "C:\4850 Law\DAVIS CHRISTINA Y_Case3241\INS PQME COVER LT- DR JACOBO CHODAKIEWITZ, CLM 06493938, 12-27-2023.pdf"
        Case = "DAVIS CHRISTINA Y"
        CaseID = 56171882
    },
    @{
        Path = "C:\4850 Law\DAVIS CHRISTINA Y_Case3241\INS LTR- PROPOSED PQME COVER LTR CLM 06493938, 12-06-2023.pdf"
        Case = "DAVIS CHRISTINA Y"
        CaseID = 56171882
    },
    @{
        Path = "C:\4850 Law\WEIDNER MICHAEL W_Case3364\WCH MRCS- BARTON HEALTH, MEDICAL RECORDS, 02-12-2025.pdf"
        Case = "WEIDNER MICHAEL W"
        CaseID = 56171915
    }
)

$MaxSizeMB = 384

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "PDF Compression with Ghostscript" -ForegroundColor Cyan
Write-Host "Quality: $Quality (screen=smallest, prepress=largest)" -ForegroundColor Cyan
Write-Host "Target: Under $MaxSizeMB MB" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Find or install Ghostscript
$GsPath = $null
$SearchPaths = @(
    "C:\Program Files\gs\gs*\bin\gswin64c.exe",
    "C:\Program Files (x86)\gs\gs*\bin\gswin32c.exe",
    "C:\gs\bin\gswin64c.exe"
)

foreach ($pattern in $SearchPaths) {
    $found = Get-ChildItem $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $GsPath = $found.FullName
        break
    }
}

if (-not $GsPath) {
    Write-Host "Ghostscript not found. Downloading..." -ForegroundColor Yellow

    $gsInstaller = "$env:TEMP\gs_installer.exe"
    $gsUrl = "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10030/gs10030w64.exe"

    try {
        Write-Host "Downloading Ghostscript 10.03.0..." -ForegroundColor Cyan
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $gsUrl -OutFile $gsInstaller -UseBasicParsing

        Write-Host "Installing Ghostscript (silent install)..." -ForegroundColor Cyan
        Start-Process -FilePath $gsInstaller -ArgumentList "/S" -Wait

        Start-Sleep -Seconds 5

        # Find the installed path
        $found = Get-ChildItem "C:\Program Files\gs\gs*\bin\gswin64c.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $GsPath = $found.FullName
            Write-Host "Ghostscript installed: $GsPath" -ForegroundColor Green
        }

        Remove-Item $gsInstaller -Force -ErrorAction SilentlyContinue

    } catch {
        Write-Host "ERROR: Could not download Ghostscript: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Please install manually from: https://ghostscript.com/releases/gsdnld.html" -ForegroundColor Yellow
        exit 1
    }
}

if (-not $GsPath -or -not (Test-Path $GsPath)) {
    Write-Host "ERROR: Ghostscript not available" -ForegroundColor Red
    exit 1
}

Write-Host "Using Ghostscript: $GsPath" -ForegroundColor Green
Write-Host ""

# Create output folder
if (-not (Test-Path $OutputFolder)) {
    New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
    Write-Host "Created: $OutputFolder" -ForegroundColor Green
}

$Results = @()
$TotalOriginal = 0
$TotalCompressed = 0
$SuccessCount = 0

foreach ($pdf in $LargePDFs) {
    $filePath = $pdf.Path
    $caseName = $pdf.Case
    $caseID = $pdf.CaseID

    if (-not (Test-Path $filePath)) {
        Write-Host "SKIP: Not found - $filePath" -ForegroundColor Yellow
        continue
    }

    $file = Get-Item $filePath
    $originalSizeMB = [math]::Round($file.Length / 1MB, 1)
    $outputPath = Join-Path $OutputFolder $file.Name

    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "File: $($file.Name)" -ForegroundColor White
    Write-Host "  Case: $caseName (ID: $caseID)" -ForegroundColor Gray
    Write-Host "  Original: $originalSizeMB MB" -ForegroundColor Red

    if ($DryRun) {
        Write-Host "  [DRY RUN] Would compress to: $outputPath" -ForegroundColor Yellow
        continue
    }

    $TotalOriginal += $originalSizeMB

    Write-Host "  Compressing with Ghostscript ($Quality)..." -ForegroundColor Cyan

    $gsArgs = @(
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/$Quality",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dColorImageResolution=150",
        "-dGrayImageResolution=150",
        "-dMonoImageResolution=150",
        "-sOutputFile=`"$outputPath`"",
        "`"$filePath`""
    )

    try {
        $startTime = Get-Date
        $process = Start-Process -FilePath $GsPath -ArgumentList $gsArgs -Wait -NoNewWindow -PassThru
        $duration = (Get-Date) - $startTime

        if (Test-Path $outputPath) {
            $compressedFile = Get-Item $outputPath
            $compressedSizeMB = [math]::Round($compressedFile.Length / 1MB, 1)
            $reduction = [math]::Round((1 - ($compressedSizeMB / $originalSizeMB)) * 100, 1)

            $TotalCompressed += $compressedSizeMB

            $status = if ($compressedSizeMB -le $MaxSizeMB) { "SUCCESS" } else { "STILL TOO LARGE" }
            $color = if ($compressedSizeMB -le $MaxSizeMB) { "Green" } else { "Yellow" }

            Write-Host "  Compressed: $compressedSizeMB MB ($reduction% reduction)" -ForegroundColor $color
            Write-Host "  Time: $([math]::Round($duration.TotalSeconds, 0)) seconds" -ForegroundColor Gray
            Write-Host "  Status: $status" -ForegroundColor $color

            if ($compressedSizeMB -le $MaxSizeMB) {
                $SuccessCount++
            }

            $Results += [PSCustomObject]@{
                Case = $caseName
                CaseID = $caseID
                FileName = $file.Name
                OriginalMB = $originalSizeMB
                CompressedMB = $compressedSizeMB
                ReductionPct = $reduction
                Status = $status
                OutputPath = $outputPath
            }
        } else {
            Write-Host "  ERROR: Compression failed" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "COMPRESSION SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Files Processed: $($LargePDFs.Count)"
Write-Host "Under 384MB: $SuccessCount" -ForegroundColor $(if ($SuccessCount -gt 0) { "Green" } else { "Yellow" })
Write-Host "Original Total: $([math]::Round($TotalOriginal, 0)) MB"
Write-Host "Compressed Total: $([math]::Round($TotalCompressed, 0)) MB"
Write-Host "Savings: $([math]::Round($TotalOriginal - $TotalCompressed, 0)) MB ($([math]::Round((1 - $TotalCompressed/$TotalOriginal) * 100, 1))%)" -ForegroundColor Green
Write-Host ""

if ($Results.Count -gt 0) {
    $Results | Format-Table Case, FileName, OriginalMB, CompressedMB, ReductionPct, Status -AutoSize

    $csvPath = Join-Path $OutputFolder "compression_results.csv"
    $Results | Export-Csv -Path $csvPath -NoTypeInformation
    Write-Host "Results: $csvPath" -ForegroundColor Green
}

# If still too large, suggest screen quality
$stillLarge = $Results | Where-Object { $_.Status -eq "STILL TOO LARGE" }
if ($stillLarge -and $Quality -ne "screen") {
    Write-Host ""
    Write-Host "TIP: For files still over 384MB, try:" -ForegroundColor Yellow
    Write-Host "  .\compress_pdfs_ghostscript.ps1 -Quality screen" -ForegroundColor White
}
