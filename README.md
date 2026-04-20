# FlashScore Scraper

Outil CLI Python qui scrape les matchs de volleyball et hockey sur [FlashScore.fr](https://www.flashscore.fr) (résultats, classements, statistiques tête-à-tête) et les injecte automatiquement dans Google Sheets.

Tourne quotidiennement sur un VPS via Docker + ofelia.

## Fonctionnement

1. Lance un navigateur headless (Playwright/Chromium) sur FlashScore.fr
2. Extrait les matchs du jour avec pays, ligue, équipes et horaires
3. Récupère les classements de chaque ligue pour les rangs des équipes
4. Pour chaque match, scrape la page tête-à-tête (stats de sets pour le volley, stats de buts pour le hockey)
5. Sauvegarde le tout en JSON puis injecte dans Google Sheets (dédoublonnage, tri par date, formules)

## Utilisation

```bash
# Installation
pip install -e . && playwright install chromium

# Configuration
cp .env.example .env   # renseigner SPREADSHEET_ID au minimum

# Lancer
flashscore-scraper                    # scrape + injection Sheets
flashscore-scraper --scrape-only      # scrape uniquement (JSON dans output/)
flashscore-scraper --sport=hockey     # hockey au lieu du volley
flashscore-scraper --days=-2          # date spécifique (offset en jours)
```

## Déploiement

Un push sur `main` déclenche le pipeline GitHub Actions (lint, tests, déploiement SSH sur le VPS).

```bash
# Docker avec scheduler (scripts Docker montés, 1h00 UTC chaque jour)
docker compose --profile scheduled up -d
```
