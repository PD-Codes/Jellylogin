#!/usr/bin/env bash
# Baut das DKS JellyLogin SSO Jellyfin-Plugin (Linux / macOS).
# Benötigt .NET 8 SDK: https://dotnet.microsoft.com/download/dotnet/8.0
#
# Verwendung:
#   ./build.sh           # Debug
#   ./build.sh release   # Release (für Produktion)

set -euo pipefail

CONFIG="${1:-Debug}"
CONFIG="${CONFIG^}"   # Ersten Buchstaben groß
OUT="$(dirname "$0")/bin/$CONFIG/net8.0"

echo "▶  Baue DKS JellyLogin Plugin ($CONFIG)…"

dotnet build "$(dirname "$0")/JellyLoginPlugin.csproj" \
  --configuration "$CONFIG" \
  --output "$OUT"

echo ""
echo "✓  Build abgeschlossen."
echo ""
echo "Installation in Jellyfin:"
echo "  1. Erstelle den Ordner:  <Jellyfin-Config>/plugins/JellyLoginSSO_1.0.0.0/"
echo "  2. Kopiere alle Dateien aus '$OUT' in diesen Ordner."
echo "  3. Starte Jellyfin neu."
echo "  4. Gehe zu: Dashboard → Plugins → DKS JellyLogin SSO → Konfigurieren"
echo "  5. Trage Server-URL und Plugin-Secret ein (aus JellyLogin Admin → Einstellungen)."
