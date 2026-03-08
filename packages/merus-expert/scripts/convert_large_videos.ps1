# convert_large_videos.ps1
# Converts oversized VOB surveillance videos to MP4 for MerusCase upload
# Target: Files must be under 384 MB for MerusCase
# Requires: FFmpeg (will attempt to download if not found)

param(
    [string]$OutputFolder = "C:\4850 Law\_Converted_Videos",
    [int]$CRF = 23,  # Quality: 18=high, 23=medium, 28=low (smaller)
    [switch]$DryRun
)

# Large VOB files that need conversion (all from ELIZONDO JAMES J case)
$LargeVideos = @(
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 1 06-18-2018 40 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 2. 06-15-2018 39 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 1. 06-15-2018 39 MINUTE.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 1. 07-22-2018 25 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 1. 05-10-2018 32 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 2. 05-10-2018 32 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 2. PART 1. 05-11-2018 32 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 1 07-25-2018 25 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 2 07-25-2021 24 MINUTES.vob"
        SizeMB = 1024.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 2. PART 2. 05-11-2018 30 MINUTES.vob"
        SizeMB = 969.8
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 3. PART 2 07-24-2018 18 MINUTES.vob"
        SizeMB = 728.0
    },
    @{
        Path = "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 3 07-25--2018 24 MINUTES.vob"
        SizeMB = 391.4
    }
)

$CaseName = "ELIZONDO JAMES J"
$CaseID = 56171884
$MaxSizeMB = 384
$Results = @()

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "VOB to MP4 Video Conversion for MerusCase Upload" -ForegroundColor Cyan
Write-Host "Target: Files under $MaxSizeMB MB" -ForegroundColor Cyan
Write-Host "Quality Setting: CRF $CRF (lower = better quality, larger file)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Create output folder
if (-not (Test-Path $OutputFolder)) {
    if (-not $DryRun) {
        New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
    }
    Write-Host "Created output folder: $OutputFolder" -ForegroundColor Green
}

# Find FFmpeg
$FFmpegPath = $null
$PossiblePaths = @(
    "ffmpeg",  # In PATH
    "C:\ffmpeg\bin\ffmpeg.exe",
    "C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    "C:\Tools\ffmpeg\bin\ffmpeg.exe",
    "$env:USERPROFILE\ffmpeg\bin\ffmpeg.exe",
    "$env:LOCALAPPDATA\ffmpeg\bin\ffmpeg.exe"
)

foreach ($path in $PossiblePaths) {
    try {
        $result = & $path -version 2>&1
        if ($result -match "ffmpeg version") {
            $FFmpegPath = $path
            break
        }
    } catch {
        continue
    }
}

if (-not $FFmpegPath) {
    Write-Host "FFmpeg not found. Attempting to download..." -ForegroundColor Yellow

    $ffmpegDir = "C:\ffmpeg"
    $ffmpegZip = "$env:TEMP\ffmpeg.zip"
    $ffmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

    try {
        Write-Host "Downloading FFmpeg from GitHub..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $ffmpegUrl -OutFile $ffmpegZip -UseBasicParsing

        Write-Host "Extracting FFmpeg..." -ForegroundColor Cyan
        Expand-Archive -Path $ffmpegZip -DestinationPath $env:TEMP -Force

        # Find the extracted folder and move to C:\ffmpeg
        $extractedFolder = Get-ChildItem "$env:TEMP\ffmpeg-*" -Directory | Select-Object -First 1
        if ($extractedFolder) {
            if (Test-Path $ffmpegDir) {
                Remove-Item $ffmpegDir -Recurse -Force
            }
            Move-Item $extractedFolder.FullName $ffmpegDir
            $FFmpegPath = "$ffmpegDir\bin\ffmpeg.exe"

            Write-Host "FFmpeg installed to: $ffmpegDir" -ForegroundColor Green
        }

        Remove-Item $ffmpegZip -Force -ErrorAction SilentlyContinue

    } catch {
        Write-Host "ERROR: Could not download FFmpeg: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
        Write-Host "Please install FFmpeg manually:" -ForegroundColor Yellow
        Write-Host "1. Download from: https://ffmpeg.org/download.html" -ForegroundColor White
        Write-Host "2. Extract to C:\ffmpeg" -ForegroundColor White
        Write-Host "3. Add C:\ffmpeg\bin to your PATH" -ForegroundColor White
        exit 1
    }
}

if (-not (Test-Path $FFmpegPath -ErrorAction SilentlyContinue)) {
    # Try once more
    $FFmpegPath = "C:\ffmpeg\bin\ffmpeg.exe"
}

if (-not (Test-Path $FFmpegPath)) {
    Write-Host "ERROR: FFmpeg still not available at $FFmpegPath" -ForegroundColor Red
    exit 1
}

Write-Host "Using FFmpeg: $FFmpegPath" -ForegroundColor Green
Write-Host ""

# Calculate total size
$TotalOriginalMB = ($LargeVideos | Measure-Object -Property SizeMB -Sum).Sum
Write-Host "Total files to convert: $($LargeVideos.Count)" -ForegroundColor White
Write-Host "Total original size: $([math]::Round($TotalOriginalMB / 1024, 2)) GB" -ForegroundColor White
Write-Host ""

# Process each video
$TotalCompressedMB = 0
$SuccessCount = 0
$VideoCount = 0

foreach ($video in $LargeVideos) {
    $VideoCount++
    $filePath = $video.Path

    if (-not (Test-Path $filePath)) {
        Write-Host "[$VideoCount/$($LargeVideos.Count)] SKIP: File not found - $filePath" -ForegroundColor Yellow
        continue
    }

    $file = Get-Item $filePath
    $originalSizeMB = [math]::Round($file.Length / 1MB, 1)
    $fileName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
    $outputFileName = "$fileName.mp4"
    $outputPath = Join-Path $OutputFolder $outputFileName

    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "[$VideoCount/$($LargeVideos.Count)] Converting: $($file.Name)" -ForegroundColor White
    Write-Host "  Original Size: $originalSizeMB MB" -ForegroundColor Red
    Write-Host "  Output: $outputFileName" -ForegroundColor Gray

    if ($DryRun) {
        Write-Host "  [DRY RUN] Would convert to: $outputPath" -ForegroundColor Yellow
        continue
    }

    # FFmpeg conversion command
    # -c:v libx264 = H.264 video codec
    # -crf = Constant Rate Factor (quality, 0-51, lower is better)
    # -preset medium = encoding speed/compression tradeoff
    # -c:a aac = AAC audio codec
    # -b:a 128k = audio bitrate
    # -movflags +faststart = optimize for web streaming

    $ffmpegArgs = @(
        "-i", "`"$filePath`"",
        "-c:v", "libx264",
        "-crf", "$CRF",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-y",  # Overwrite output
        "`"$outputPath`""
    )

    Write-Host "  Converting (this may take several minutes)..." -ForegroundColor Cyan
    $startTime = Get-Date

    try {
        $process = Start-Process -FilePath $FFmpegPath -ArgumentList $ffmpegArgs -Wait -NoNewWindow -PassThru -RedirectStandardError "$env:TEMP\ffmpeg_err.log"

        $duration = (Get-Date) - $startTime

        if (Test-Path $outputPath) {
            $compressedFile = Get-Item $outputPath
            $compressedSizeMB = [math]::Round($compressedFile.Length / 1MB, 1)
            $reduction = [math]::Round((1 - ($compressedSizeMB / $originalSizeMB)) * 100, 1)

            $TotalCompressedMB += $compressedSizeMB

            $status = if ($compressedSizeMB -le $MaxSizeMB) { "SUCCESS" } else { "STILL TOO LARGE" }
            $color = if ($compressedSizeMB -le $MaxSizeMB) { "Green" } else { "Yellow" }

            Write-Host "  Compressed Size: $compressedSizeMB MB ($reduction% reduction)" -ForegroundColor $color
            Write-Host "  Duration: $([math]::Round($duration.TotalMinutes, 1)) minutes" -ForegroundColor Gray
            Write-Host "  Status: $status" -ForegroundColor $color

            if ($compressedSizeMB -le $MaxSizeMB) {
                $SuccessCount++
            }

            $Results += [PSCustomObject]@{
                FileName = $file.Name
                OriginalMB = $originalSizeMB
                CompressedMB = $compressedSizeMB
                ReductionPct = $reduction
                DurationMin = [math]::Round($duration.TotalMinutes, 1)
                Status = $status
                OutputPath = $outputPath
            }
        } else {
            Write-Host "  ERROR: Output file not created" -ForegroundColor Red

            # Show FFmpeg error
            if (Test-Path "$env:TEMP\ffmpeg_err.log") {
                $errLog = Get-Content "$env:TEMP\ffmpeg_err.log" -Tail 10
                Write-Host "  FFmpeg output:" -ForegroundColor Yellow
                $errLog | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
            }
        }

    } catch {
        Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "CONVERSION SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Case: $CaseName (ID: $CaseID)" -ForegroundColor White
Write-Host "Files Processed: $($LargeVideos.Count)" -ForegroundColor White
Write-Host "Successfully Under 384MB: $SuccessCount" -ForegroundColor $(if ($SuccessCount -eq $LargeVideos.Count) { "Green" } else { "Yellow" })
Write-Host "Total Original Size: $([math]::Round($TotalOriginalMB, 0)) MB ($([math]::Round($TotalOriginalMB/1024, 2)) GB)" -ForegroundColor Gray
Write-Host "Total Compressed Size: $([math]::Round($TotalCompressedMB, 0)) MB ($([math]::Round($TotalCompressedMB/1024, 2)) GB)" -ForegroundColor Gray
Write-Host "Total Savings: $([math]::Round($TotalOriginalMB - $TotalCompressedMB, 0)) MB" -ForegroundColor Green
Write-Host ""
Write-Host "Converted files saved to: $OutputFolder" -ForegroundColor Cyan
Write-Host ""

# Output results table
if ($Results.Count -gt 0) {
    Write-Host "RESULTS:" -ForegroundColor White
    $Results | Format-Table -AutoSize FileName, OriginalMB, CompressedMB, ReductionPct, DurationMin, Status
}

# Save results to CSV
$csvPath = Join-Path $OutputFolder "conversion_results.csv"
if (-not $DryRun -and $Results.Count -gt 0) {
    $Results | Export-Csv -Path $csvPath -NoTypeInformation
    Write-Host "Results saved to: $csvPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "MerusCase Upload URL:" -ForegroundColor Yellow
Write-Host "https://meruscase.com/cms#/caseFiles/view/$CaseID?t=documents" -ForegroundColor Cyan
Write-Host ""

# Quality adjustment tips
if ($SuccessCount -lt $LargeVideos.Count) {
    Write-Host "TIPS for files still over 384MB:" -ForegroundColor Yellow
    Write-Host "  - Re-run with higher CRF: .\convert_large_videos.ps1 -CRF 28" -ForegroundColor White
    Write-Host "  - CRF 28-32 = lower quality but smaller files" -ForegroundColor White
    Write-Host "  - Or split long videos into segments" -ForegroundColor White
}
