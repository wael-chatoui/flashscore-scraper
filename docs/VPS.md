# Documentation VPS

Ce document sert de runbook pour exploiter le scraper FlashScore sur le VPS de production.

## Informations serveur

| Élément | Valeur |
| --- | --- |
| IP publique | `76.13.46.236` |
| Accès SSH | `root@76.13.46.236` |
| OS connu | Ubuntu 24.04 |
| Dossier projet | `/root/flashscore-scraper` |
| Runtime | Docker Compose + ofelia |
| Branche déployée | `main` |

État signalé : le VPS est down depuis le 18 avril 2026. Les commandes ci-dessous servent à confirmer l'état, redémarrer les services et vérifier que les tâches repartent correctement.

## Prérequis sur le VPS

Le serveur doit contenir :

- Docker et Docker Compose fonctionnels.
- Le dépôt cloné dans `/root/flashscore-scraper`.
- Le fichier `/root/flashscore-scraper/.env`.
- Le fichier `/root/flashscore-scraper/credentials.json`.
- Une clé SSH GitHub valide pour `git pull`, ou un accès HTTPS configuré.

Ne jamais committer `.env` ni `credentials.json`.

## Connexion SSH

```bash
ssh root@76.13.46.236
cd /root/flashscore-scraper
```

Si la connexion échoue :

```bash
ping 76.13.46.236
ssh -vvv root@76.13.46.236
```

À vérifier côté hébergeur si le SSH ne répond pas :

- VPS démarré.
- IP publique toujours assignée au serveur.
- Firewall autorisant le port 22.
- Charge CPU/RAM/disque.
- Console de secours disponible.

## Déploiement automatique

Un push sur `main` déclenche GitHub Actions :

1. `ruff check flashscore_scraper/`
2. `ruff format --check flashscore_scraper/`
3. `pytest tests/ -v`
4. Déploiement SSH sur `76.13.46.236`

Le job de déploiement exécute :

```bash
cd /root/flashscore-scraper
git pull
docker compose --profile scheduled up -d --build
```

Secret GitHub requis : `VPS_SSH_KEY`.

## Déploiement manuel

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && git pull && docker compose --profile scheduled up -d --build"
```

Après déploiement, vérifier :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose --profile scheduled ps"
```

## Services Docker

| Service Compose | Conteneur | Rôle |
| --- | --- | --- |
| `scraper` | `flashscore-volleyball-scraper` | Scrape volleyball |
| `hockey-scraper` | `flashscore-hockey-scraper` | Scrape hockey |
| `football-scraper` | `flashscore-football-scraper` | Scrape football |
| `scheduler` | `flashscore-scheduler` | Lance les jobs planifiés ofelia |

Lister les conteneurs :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose --profile scheduled ps"
```

Voir tous les conteneurs Docker :

```bash
ssh root@76.13.46.236 "docker ps -a"
```

## Planning

Les horaires sont en UTC.

| Sport | Heure | Commande |
| --- | --- | --- |
| Volleyball | 01:00 | `scripts/run_volleyball_docker.sh` |
| Hockey | 02:00 | `scripts/run_hockey_docker.sh` |
| Football | 03:00 | `scripts/run_football_docker.sh` |

Vérifier l'heure du serveur :

```bash
ssh root@76.13.46.236 "date && date -u"
```

## Logs

Logs Docker du scraper volleyball :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose logs --tail=100 scraper"
```

Logs Docker hockey :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose logs --tail=100 hockey-scraper"
```

Logs Docker football :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose logs --tail=100 football-scraper"
```

Logs scheduler :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose logs --tail=100 scheduler"
```

Logs applicatifs écrits par les scripts :

```bash
ssh root@76.13.46.236 "ls -lh /root/flashscore-scraper/logs/"
ssh root@76.13.46.236 "tail -n 100 /root/flashscore-scraper/logs/scheduler_volleyball_$(date +%Y-%m-%d).log"
ssh root@76.13.46.236 "tail -n 100 /root/flashscore-scraper/logs/scheduler_hockey_$(date +%Y-%m-%d).log"
ssh root@76.13.46.236 "tail -n 100 /root/flashscore-scraper/logs/scheduler_football_$(date +%Y-%m-%d).log"
```

## Exécution manuelle

Lancer tous les jobs définis par défaut :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose run --rm scraper"
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose run --rm hockey-scraper"
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose run --rm football-scraper"
```

Lancer une date précise avec l'offset `--days` :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose run --rm scraper python -m flashscore_scraper --days=-2"
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose run --rm hockey-scraper python -m flashscore_scraper --sport=hockey --days=-2"
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose run --rm football-scraper python -m flashscore_scraper --sport=football --days=-2"
```

## Fichiers de sortie

```bash
ssh root@76.13.46.236 "ls -lh /root/flashscore-scraper/output/"
```

Les fichiers JSON dans `output/` sont des artefacts d'exécution. Ils ne doivent pas être commités.

## Redémarrage

Redémarrer tous les conteneurs du profil planifié :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose --profile scheduled restart"
```

Reconstruire et relancer :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose --profile scheduled up -d --build"
```

Arrêter :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && docker compose --profile scheduled down"
```

## Diagnostic si le VPS est down

Depuis la machine locale :

```bash
ping 76.13.46.236
ssh -vvv root@76.13.46.236
```

Si le SSH répond, vérifier sur le serveur :

```bash
cd /root/flashscore-scraper
git status --short
docker --version
docker compose version
docker compose --profile scheduled ps
docker compose logs --tail=100 scheduler
df -h
free -h
uptime
```

Si les conteneurs sont arrêtés :

```bash
cd /root/flashscore-scraper
docker compose --profile scheduled up -d --build
docker compose --profile scheduled ps
```

Si le serveur ne répond pas du tout, passer par le panel de l'hébergeur pour :

1. Vérifier que le VPS est allumé.
2. Redémarrer le VPS.
3. Ouvrir la console de secours.
4. Contrôler le firewall et l'IP publique.
5. Vérifier que le disque n'est pas plein.

## Rollback

Lister les derniers commits :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && git log --oneline -10"
```

Revenir temporairement sur un commit :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && git checkout <commit> && docker compose --profile scheduled up -d --build"
```

Après diagnostic, revenir sur `main` :

```bash
ssh root@76.13.46.236 "cd /root/flashscore-scraper && git checkout main && git pull && docker compose --profile scheduled up -d --build"
```

## Checklist après remise en service

1. `ssh root@76.13.46.236` fonctionne.
2. `docker compose --profile scheduled ps` montre `flashscore-scheduler` actif.
3. Les trois jobs manuels peuvent être lancés sans erreur.
4. Les logs dans `/root/flashscore-scraper/logs/` se mettent à jour.
5. Les fichiers JSON apparaissent dans `/root/flashscore-scraper/output/`.
6. Les données arrivent dans Google Sheets.
7. GitHub Actions peut déployer après un push sur `main`.
