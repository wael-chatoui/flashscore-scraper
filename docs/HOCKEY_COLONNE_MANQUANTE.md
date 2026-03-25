# Colonne manquante : Team B <=4 buts

## Contexte

Dans la feuille **SCRAPING UND 5.5/6**, les statistiques par equipe sont reparties ainsi :

| Colonnes | Equipe | Stats |
|----------|--------|-------|
| O-R | Team A | <=4, <=5, =6, >=7 |
| W-Y | Team B | <=5, =6, >=7 |

## Statut

Corrige : la colonne manquante a ete ajoutee dans la structure cible et le preset `HOCKEY UND` pointe maintenant vers `V` pour Team B.

## Probleme

La colonne **<=4 buts** (equivalent de la colonne O pour Team A) **n'existait pas** cote Team B.

- Team A a 4 colonnes de stats : O (<=4), P (<=5), Q (=6), R (>=7)
- Team B a seulement 3 colonnes de stats : W (<=5), X (=6), Y (>=7)

La colonne V est desormais reservee a "<=4 buts Team B".

## Impact

Le scraper ecrit correctement les 3 colonnes disponibles pour Team B (W-Y) mais **ne peut pas ecrire** la stat <=4 buts pour Team B car il n'y a pas de colonne prevue.

## Solution appliquee

Pour ajouter cette donnee, il fallait :

1. Inserer une colonne avant W dans la feuille Google Sheets
2. Mettre a jour le preset `HOCKEY UND` dans `sheets.py` pour ajouter `'set2': 'V'` dans `teamB`
