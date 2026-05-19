# Migration Excel → SQLite — Tableau de bord Futsal

## Ce que fait ce dossier

Convertit ton fichier `Tableau_de_bord_EDF-U19.xlsx` en une base SQLite propre,
prête à être branchée sur l'appli Streamlit qu'on va construire ensuite.

## Fichiers

| Fichier | Rôle |
|---|---|
| `schema.sql` | Définition des tables, vues et index |
| `migration.py` | Script qui lit le xlsx et remplit la base SQLite |
| `Tableau_de_bord_EDF-U19.xlsx` | Ton fichier source (à placer ici) |
| `futsal.db` | La base SQLite générée (créée par le script) |

## Lancer la migration

### 1. Installer la dépendance

Une seule librairie nécessaire pour le script :

```bash
pip install openpyxl
```

### 2. Vérifier que les 3 fichiers sont dans le même dossier

```
mon_dossier/
├── schema.sql
├── migration.py
└── Tableau_de_bord_EDF-U19.xlsx
```

### 3. Exécuter

```bash
python migration.py
```

Tu dois voir une sortie qui finit par :

```
✓ Base créée : .../futsal.db
```

Et un bilan qui doit matcher ton Excel : 24 joueurs, 4 matchs, 57 performances,
58 notes, bilan 1V-1N-2D, 15 buts pour / 18 contre.

### 4. Inspecter la base (optionnel)

Soit avec un outil graphique gratuit comme [DB Browser for SQLite](https://sqlitebrowser.org/),
soit en ligne de commande :

```bash
sqlite3 futsal.db
.tables                    # liste des tables
SELECT * FROM v_equipe_bilan;
SELECT joueur, SUM(buts) FROM v_performance GROUP BY joueur ORDER BY 2 DESC;
.quit
```

## Architecture des données

### Tables

- **equipe** — une équipe (EDF U19, Goal FC U13...). Permet de gérer plusieurs
  équipes dans la même base si besoin.
- **joueur** — rattaché à une équipe.
- **match** — un match avec score, lieu, compétition.
- **performance** — *table de faits*. Une ligne = un joueur dans un match.
  Contient uniquement les **stats brutes**.
- **note_match** — note manuelle 0/5/10 par joueur par match.
- **parametre** — valeurs globales (note de départ, bonus victoire/nul/défaite).
- **coefficient** — grille de pondération par action (buts × 1.5, etc.).

### Vues (calculs automatiques)

Les colonnes dérivées (per 40 min, %, etc.) ne sont pas stockées :
elles sont calculées en temps réel par les vues SQL.

- **v_performance** — équivalent moderne de ta feuille BASE_DATA : stats brutes
  + per 40 + pourcentages, recalculés à chaque requête.
- **v_match** — match enrichi avec résultat (Victoire/Nul/Défaite) et diff de buts.
- **v_equipe_bilan** — bilan global de l'équipe.

### Pourquoi cette séparation

- **Ajouter un match** = ajouter quelques lignes en base, tout le reste se met
  à jour automatiquement (KPI, classements, per 40, %).
- **Modifier un coefficient de notation** = changer une valeur dans la table
  `coefficient`, toutes les notes se recalculent.
- **Réutiliser pour un club** = créer une nouvelle équipe, importer les joueurs
  et performances du club. Le même schéma fonctionne, et donc la même appli
  Streamlit fonctionnera dessus.

## Prochaine étape

Une fois `futsal.db` créée et vérifiée, on attaque l'appli Streamlit :
- vue équipe
- fiche joueur
- comparaison
- gardiens
- évolution saison
- notes manuelles
- export PDF

L'appli lira directement `futsal.db` — plus aucune référence à l'Excel.

## Si quelque chose ne marche pas

- **`ModuleNotFoundError: No module named 'openpyxl'`** → faire `pip install openpyxl`
- **`schema.sql introuvable`** → vérifier que les 3 fichiers sont bien dans
  le même dossier que `migration.py`
- **Joueur ou match introuvable dans les warnings** → un nom est mal orthographié
  dans BASE_DATA par rapport à JOUEURS, ou un Match_ID dans BASE_DATA n'existe
  pas dans MATCHS_REF. Corriger dans l'Excel puis relancer.
- **Relancer le script** efface l'ancienne base et la recrée from scratch.
  Tant qu'on est en phase de mise en place, ce n'est pas un souci.
