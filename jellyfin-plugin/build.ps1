<#
  .SYNOPSIS
  Baut das DKS JellyLogin SSO Jellyfin-Plugin (Windows).

  .DESCRIPTION
  Benötigt .NET 8 SDK: https://dotnet.microsoft.com/download/dotnet/8.0

  .EXAMPLE
  .\build.ps1              # Debug-Build
  .\build.ps1 -Release     # Release-Build (für Produktion)
#>
param(
  [switch]$Release
)

$config  = if ($Release) { "Release" } else { "Debug" }
$out     = "$PSScriptRoot\bin\$config\net8.0"

Write-Host "▶  Baue DKS JellyLogin Plugin ($config)…" -ForegroundColor Cyan

dotnet build "$PSScriptRoot\JellyLoginPlugin.csproj" `
  --configuration $config `
  --output $out

if ($LASTEXITCODE -ne 0) {
  Write-Error "Build fehlgeschlagen."
  exit 1
}

Write-Host ""
Write-Host "✓  Build abgeschlossen." -ForegroundColor Green
Write-Host ""
Write-Host "Installation in Jellyfin:" -ForegroundColor Yellow
Write-Host "  1. Erstelle den Ordner:  <Jellyfin-Config>/plugins/JellyLoginSSO_1.0.0.0/"
Write-Host "  2. Kopiere alle Dateien aus '$out' in diesen Ordner."
Write-Host "  3. Starte Jellyfin neu."
Write-Host "  4. Gehe zu: Dashboard → Plugins → DKS JellyLogin SSO → Konfigurieren"
Write-Host "  5. Trage Server-URL und Plugin-Secret ein (aus JellyLogin Admin → Einstellungen)."
