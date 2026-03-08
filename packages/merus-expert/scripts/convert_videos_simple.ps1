# Simple video conversion script
$FFmpeg = "C:\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
$OutputDir = "C:\4850 Law\_Converted_Videos"
$CRF = 28  # Higher compression for smaller files

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

Write-Host "Video Conversion - ELIZONDO JAMES J" -ForegroundColor Cyan
Write-Host "FFmpeg: $FFmpeg"
Write-Host "Output: $OutputDir"
Write-Host "CRF: $CRF (higher = smaller files)"
Write-Host ""

$Videos = @(
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 1 06-18-2018 40 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 2. 06-15-2018 39 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 1. 06-15-2018 39 MINUTE.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 1. 07-22-2018 25 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 1. 05-10-2018 32 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 1. PART 2. 05-10-2018 32 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 2. PART 1. 05-11-2018 32 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 1 07-25-2018 25 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 2 07-25-2021 24 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 2. PART 2. 05-11-2018 30 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 3. PART 2 07-24-2018 18 MINUTES.vob",
    "C:\4850 Law\ELIZONDO JAMES J_Case3013\VIDEO. SUBROSA FOOTAGE VIDEO 4. PART 3 07-25--2018 24 MINUTES.vob"
)

$Count = 0
$Success = 0
$Results = @()

foreach ($video in $Videos) {
    $Count++

    if (-not (Test-Path $video)) {
        Write-Host "[$Count/12] SKIP: Not found - $video" -ForegroundColor Yellow
        continue
    }

    $file = Get-Item $video
    $originalMB = [math]::Round($file.Length / 1MB, 1)
    $outputName = [System.IO.Path]::GetFileNameWithoutExtension($file.Name) + ".mp4"
    $outputPath = Join-Path $OutputDir $outputName

    Write-Host "[$Count/12] Converting: $($file.Name)" -ForegroundColor White
    Write-Host "  Original: $originalMB MB" -ForegroundColor Gray

    $startTime = Get-Date

    & $FFmpeg -i $video -c:v libx264 -crf $CRF -preset fast -c:a aac -b:a 96k -movflags +faststart -y $outputPath 2>&1 | Out-Null

    $duration = (Get-Date) - $startTime

    if (Test-Path $outputPath) {
        $compressedMB = [math]::Round((Get-Item $outputPath).Length / 1MB, 1)
        $reduction = [math]::Round((1 - ($compressedMB / $originalMB)) * 100, 1)

        $status = if ($compressedMB -le 384) { "SUCCESS" } else { "TOO LARGE" }
        $color = if ($compressedMB -le 384) { "Green" } else { "Yellow" }

        Write-Host "  Compressed: $compressedMB MB ($reduction% reduction) - $status" -ForegroundColor $color
        Write-Host "  Time: $([math]::Round($duration.TotalMinutes, 1)) min" -ForegroundColor Gray

        if ($compressedMB -le 384) { $Success++ }

        $Results += [PSCustomObject]@{
            File = $file.Name
            OriginalMB = $originalMB
            CompressedMB = $compressedMB
            Reduction = $reduction
            Status = $status
        }
    } else {
        Write-Host "  ERROR: Conversion failed" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "SUMMARY: $Success/12 videos under 384MB" -ForegroundColor $(if ($Success -eq 12) { "Green" } else { "Yellow" })
$Results | Format-Table -AutoSize
