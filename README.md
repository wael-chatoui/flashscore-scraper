# FlashScore Scraper

Outil CLI Python qui scrape les matchs de volleyball, hockey et football sur [FlashScore.fr](https://www.flashscore.fr) (résultats, classements, statistiques tête-à-tête) et les injecte automatiquement dans Google Sheets.

Le projet était hébergé sur un VPS Hostinger via Docker + ofelia jusqu'à l'arrêt du service le 18 avril 2026.

## Important

Avant toute reprise, maintenance, analyse ou utilisation du projet, lire impérativement le fichier de clôture :

[docs/CLOTURE_PROJET_2026-04-18.md](docs/CLOTURE_PROJET_2026-04-18.md)

Ce fichier documente la livraison du scraper hockey, l'arrêt du VPS Hostinger au 18 avril 2026 et la clôture du projet à cette date.

## Fonctionnement

1. Lance un navigateur headless (Playwright/Chromium) sur FlashScore.fr
2. Extrait les matchs du jour avec pays, ligue, équipes et horaires
3. Récupère les classements de chaque ligue pour les rangs des équipes
4. Pour chaque match, scrape la page tête-à-tête et les statistiques propres au sport
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
flashscore-scraper --sport=football   # football
flashscore-scraper --days=-2          # date spécifique (offset en jours)
```

## Déploiement

Un push sur `main` déclenche le pipeline GitHub Actions (lint, tests, déploiement SSH sur le VPS) si l'infrastructure VPS est active.

```bash
# Docker avec scheduler ofelia
docker compose --profile scheduled up -d
```

## Documentation

- Clôture du projet : [docs/CLOTURE_PROJET_2026-04-18.md](docs/CLOTURE_PROJET_2026-04-18.md)
- Exploitation VPS : [docs/VPS.md](docs/VPS.md)
- Note hockey : [docs/HOCKEY_COLONNE_MANQUANTE.md](docs/HOCKEY_COLONNE_MANQUANTE.md)
- Architecture : [ARCHITECTURE.md](ARCHITECTURE.md)
- Historique : [CHANGELOG.md](CHANGELOG.md)
