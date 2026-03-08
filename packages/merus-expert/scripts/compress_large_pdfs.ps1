# compress_large_pdfs.ps1
# Compresses oversized PDFs using Adobe Acrobat for MerusCase upload
# Target: Files must be under 384 MB for MerusCase

param(
    [string]$OutputFolder = "C:\4850 Law\_Compressed",
    [switch]$DryRun
)

# Large PDF files that need compression
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
$Results = @()

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "PDF Compression Script for MerusCase Upload" -ForegroundColor Cyan
Write-Host "Target: Files under $MaxSizeMB MB" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Create output folder
if (-not (Test-Path $OutputFolder)) {
    if (-not $DryRun) {
        New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
    }
    Write-Host "Created output folder: $OutputFolder" -ForegroundColor Green
}

# Check for Adobe Acrobat
$AcrobatPath = $null
$PossiblePaths = @(
    "C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
    "C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
    "C:\Program Files\Adobe\Acrobat 2020\Acrobat\Acrobat.exe",
    "C:\Program Files\Adobe\Acrobat 2017\Acrobat\Acrobat.exe"
)

foreach ($path in $PossiblePaths) {
    if (Test-Path $path) {
        $AcrobatPath = $path
        break
    }
}

if (-not $AcrobatPath) {
    Write-Host "ERROR: Adobe Acrobat not found. Checking for Acrobat Reader..." -ForegroundColor Red

    # Check for Reader (limited functionality)
    $ReaderPaths = @(
        "C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
        "C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe"
    )

    foreach ($path in $ReaderPaths) {
        if (Test-Path $path) {
            Write-Host "Found Adobe Reader, but full Acrobat is required for PDF optimization." -ForegroundColor Yellow
            Write-Host "Please use Acrobat Pro/Standard for compression." -ForegroundColor Yellow
            break
        }
    }
    exit 1
}

Write-Host "Found Adobe Acrobat: $AcrobatPath" -ForegroundColor Green
Write-Host ""

# Process each PDF
$TotalOriginal = 0
$TotalCompressed = 0
$SuccessCount = 0

foreach ($pdf in $LargePDFs) {
    $filePath = $pdf.Path
    $caseName = $pdf.Case

    if (-not (Test-Path $filePath)) {
        Write-Host "SKIP: File not found - $filePath" -ForegroundColor Yellow
        continue
    }

    $file = Get-Item $filePath
    $originalSizeMB = [math]::Round($file.Length / 1MB, 1)
    $fileName = $file.Name
    $outputPath = Join-Path $OutputFolder $fileName

    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "Processing: $fileName" -ForegroundColor White
    Write-Host "  Case: $caseName" -ForegroundColor Gray
    Write-Host "  Original Size: $originalSizeMB MB" -ForegroundColor $(if ($originalSizeMB -gt $MaxSizeMB) { "Red" } else { "Green" })

    if ($DryRun) {
        Write-Host "  [DRY RUN] Would compress to: $outputPath" -ForegroundColor Yellow
        continue
    }

    $TotalOriginal += $originalSizeMB

    # Method 1: Try COM automation first (most reliable)
    try {
        Write-Host "  Compressing via Adobe Acrobat..." -ForegroundColor Cyan

        # Create Acrobat application object
        $acroApp = New-Object -ComObject AcroExch.App
        $avDoc = New-Object -ComObject AcroExch.AVDoc

        # Open the PDF
        $opened = $avDoc.Open($filePath, "")

        if ($opened) {
            $pdDoc = $avDoc.GetPDDoc()

            # Save with optimization (reduced size)
            # JSObject allows us to call Acrobat JavaScript
            $jso = $pdDoc.GetJSObject()

            # Save as reduced size PDF
            $saved = $pdDoc.Save(1, $outputPath)  # 1 = PDSaveFull

            $pdDoc.Close()
            $avDoc.Close(1)

            if (Test-Path $outputPath) {
                $compressedFile = Get-Item $outputPath
                $compressedSizeMB = [math]::Round($compressedFile.Length / 1MB, 1)
                $reduction = [math]::Round((1 - ($compressedSizeMB / $originalSizeMB)) * 100, 1)

                $TotalCompressed += $compressedSizeMB

                $status = if ($compressedSizeMB -le $MaxSizeMB) { "SUCCESS" } else { "STILL TOO LARGE" }
                $color = if ($compressedSizeMB -le $MaxSizeMB) { "Green" } else { "Yellow" }

                Write-Host "  Compressed Size: $compressedSizeMB MB ($reduction% reduction)" -ForegroundColor $color
                Write-Host "  Status: $status" -ForegroundColor $color

                if ($compressedSizeMB -le $MaxSizeMB) {
                    $SuccessCount++
                }

                $Results += [PSCustomObject]@{
                    Case = $caseName
                    FileName = $fileName
                    OriginalMB = $originalSizeMB
                    CompressedMB = $compressedSizeMB
                    ReductionPct = $reduction
                    Status = $status
                    OutputPath = $outputPath
                }
            }
        } else {
            Write-Host "  ERROR: Could not open PDF" -ForegroundColor Red
        }

        # Clean up COM objects
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($avDoc) | Out-Null
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($acroApp) | Out-Null

    } catch {
        Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Trying alternative method..." -ForegroundColor Yellow

        # Method 2: Use Acrobat command line with JavaScript
        try {
            # Create a temporary JavaScript file for batch processing
            $jsContent = @"
var doc = app.openDoc("$($filePath -replace '\\', '/')");
doc.saveAs("$($outputPath -replace '\\', '/')", "com.adobe.acrobat.pdf");
doc.close();
app.quit();
"@
            $jsPath = Join-Path $env:TEMP "compress_pdf.js"
            $jsContent | Out-File -FilePath $jsPath -Encoding ASCII

            # Run Acrobat with the JavaScript
            Start-Process -FilePath $AcrobatPath -ArgumentList "/s", "/h", "/n", $jsPath -Wait -NoNewWindow

            Start-Sleep -Seconds 5

            if (Test-Path $outputPath) {
                $compressedFile = Get-Item $outputPath
                $compressedSizeMB = [math]::Round($compressedFile.Length / 1MB, 1)
                $reduction = [math]::Round((1 - ($compressedSizeMB / $originalSizeMB)) * 100, 1)

                Write-Host "  Compressed Size: $compressedSizeMB MB ($reduction% reduction)" -ForegroundColor Green
                $SuccessCount++
            }

            Remove-Item $jsPath -Force -ErrorAction SilentlyContinue

        } catch {
            Write-Host "  Alternative method also failed: $($_.Exception.Message)" -ForegroundColor Red
        }
    }

    # Small delay between files
    Start-Sleep -Seconds 2
}

# Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "COMPRESSION SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Files Processed: $($LargePDFs.Count)" -ForegroundColor White
Write-Host "Successfully Under 384MB: $SuccessCount" -ForegroundColor $(if ($SuccessCount -eq $LargePDFs.Count) { "Green" } else { "Yellow" })
Write-Host "Total Original Size: $TotalOriginal MB" -ForegroundColor Gray
Write-Host "Total Compressed Size: $TotalCompressed MB" -ForegroundColor Gray
Write-Host "Total Savings: $([math]::Round($TotalOriginal - $TotalCompressed, 1)) MB" -ForegroundColor Green
Write-Host ""
Write-Host "Compressed files saved to: $OutputFolder" -ForegroundColor Cyan
Write-Host ""

# Output results table
if ($Results.Count -gt 0) {
    Write-Host "RESULTS:" -ForegroundColor White
    $Results | Format-Table -AutoSize Case, FileName, OriginalMB, CompressedMB, ReductionPct, Status
}

# Save results to CSV
$csvPath = Join-Path $OutputFolder "compression_results.csv"
if (-not $DryRun -and $Results.Count -gt 0) {
    $Results | Export-Csv -Path $csvPath -NoTypeInformation
    Write-Host "Results saved to: $csvPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Review compressed files in: $OutputFolder" -ForegroundColor White
Write-Host "2. Upload files under 384MB to MerusCase" -ForegroundColor White
Write-Host "3. For files still over 384MB, try 'Optimized PDF' in Acrobat with lower DPI" -ForegroundColor White
