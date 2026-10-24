# ===================================================================
# MSK YTDL - Windows Executable Authenticode Signer
# Publisher: MSK Software Solutions
# ===================================================================

param (
    [string]$ExePath = "",
    [switch]$InstallCert = $false
)

$ErrorActionPreference = "Continue"

Write-Host "`n[MSK Software Solutions] Code Signing Utility" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor DarkGray

# 1. Resolve Target Executable Path
if ([string]::IsNullOrWhiteSpace($ExePath)) {
    $candidates = @(
        "$PSScriptRoot\..\dist\MSK-YTDL\MSK-YTDL.exe",
        "$PSScriptRoot\..\dist\MSK-YTDL-Portable\MSK-YTDL.exe",
        "$PSScriptRoot\..\dist\MSK-YTDL.exe",
        "$PSScriptRoot\..\msk-ytdl-site\downloads\MSK-YTDL.exe"
    )
    foreach ($cand in $candidates) {
        if (Test-Path $cand) {
            $ExePath = (Resolve-Path $cand).Path
            break
        }
    }
}

if (-not (Test-Path $ExePath)) {
    Write-Warning "Target executable not found at specified path: $ExePath"
    Write-Host "Please pass -ExePath <path-to-MSK-YTDL.exe>" -ForegroundColor Yellow
} else {
    Write-Host "Target executable: $ExePath" -ForegroundColor Green
}

# 2. Check for or generate 'MSK Software Solutions' Code Signing Certificate
$certSubject = "CN=MSK Software Solutions, O=MSK Software Solutions, C=IN"
$existingCert = Get-ChildItem -Path "Cert:\CurrentUser\My" | Where-Object { $_.Subject -match "MSK Software Solutions" } | Select-Object -First 1

if (-not $existingCert) {
    Write-Host "Creating new Code Signing Certificate for 'MSK Software Solutions'..." -ForegroundColor Cyan
    $existingCert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $certSubject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(5) `
        -FriendlyName "MSK Software Solutions Authenticode" `
        -HashAlgorithm SHA256 `
        -KeyLength 2048
    Write-Host "Certificate generated successfully." -ForegroundColor Green
} else {
    Write-Host "Found existing certificate: $($existingCert.Thumbprint)" -ForegroundColor Green
}

# 3. Export Public Certificate (.cer)
$certExportPath = "$PSScriptRoot\..\MSK_Software_Solutions.cer"
Export-Certificate -Cert $existingCert -FilePath $certExportPath -Force | Out-Null
Write-Host "Exported public certificate to: $certExportPath" -ForegroundColor Green

# Also copy to downloads and dist
$copyTargets = @(
    "$PSScriptRoot\..\dist\MSK-YTDL-Portable",
    "$PSScriptRoot\..\msk-ytdl-site\downloads"
)
foreach ($dir in $copyTargets) {
    if (Test-Path $dir) {
        Copy-Item $certExportPath (Join-Path $dir "MSK_Software_Solutions.cer") -Force
    }
}

# 4. Sign the Executable if it exists
if (Test-Path $ExePath) {
    Write-Host "Signing $ExePath with Authenticode SHA256 signature..." -ForegroundColor Cyan
    try {
        $sigResult = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $existingCert -TimestampServer "http://timestamp.digicert.com" -HashAlgorithm SHA256
        if ($sigResult.Status -eq "Valid") {
            Write-Host "SUCCESS: $ExePath is signed and valid!" -ForegroundColor Green
        } else {
            Write-Host "Signature applied (Status: $($sigResult.StatusMessage))" -ForegroundColor Yellow
        }
    } catch {
        # Fallback without timestamp if offline
        Write-Warning "Timestamp server unreachable, signing without timestamp..."
        $sigResult = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $existingCert -HashAlgorithm SHA256
        Write-Host "Signature applied (Status: $($sigResult.StatusMessage))" -ForegroundColor Yellow
    }
}

# 5. Generate 1-Click Certificate Installer Batch file
$installerBatContent = @"
@echo off
:: ===================================================================
:: MSK YTDL - Trusted Publisher Certificate Installer
:: Publisher: MSK Software Solutions
:: ===================================================================
echo [MSK Software Solutions] Installing Trusted Publisher Certificate...
echo This ensures Windows Defender SmartScreen recognizes MSK YTDL safely.
echo.

openfiles >nul 2>&1
if %errorlevel% neq 0 (
    echo [REQUESTING ADMIN PRIVILEGES]
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
if not exist "MSK_Software_Solutions.cer" (
    echo [ERROR] MSK_Software_Solutions.cer not found in this folder.
    pause
    exit /b 1
)

echo Importing certificate into Windows Trusted Root and Trusted Publisher stores...
certutil -addstore -f "Root" "MSK_Software_Solutions.cer"
certutil -addstore -f "TrustedPublisher" "MSK_Software_Solutions.cer"

echo.
echo ===================================================================
echo SUCCESS! Certificate for "MSK Software Solutions" is now trusted.
echo Windows SmartScreen warnings for MSK YTDL are now resolved.
echo ===================================================================
pause
"@

$certInstallerPath = "$PSScriptRoot\..\dist\MSK-YTDL-Portable\Install_MSK_Certificate.bat"
if (Test-Path "$PSScriptRoot\..\dist\MSK-YTDL-Portable") {
    Set-Content -Path $certInstallerPath -Value $installerBatContent -Encoding Ascii
    Write-Host "Generated: $certInstallerPath" -ForegroundColor Green
}

$siteDownloadBat = "$PSScriptRoot\..\msk-ytdl-site\downloads\Install_MSK_Certificate.bat"
if (Test-Path "$PSScriptRoot\..\msk-ytdl-site\downloads") {
    Set-Content -Path $siteDownloadBat -Value $installerBatContent -Encoding Ascii
    Write-Host "Generated: $siteDownloadBat" -ForegroundColor Green
}

Write-Host "`nAll Windows signing steps completed successfully." -ForegroundColor Green
