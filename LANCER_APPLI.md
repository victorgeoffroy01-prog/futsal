# Lancer l'appli Streamlit — pas à pas

## Préparation

Mets ces fichiers dans le même dossier que ta `futsal.db` :

```
mon_dossier_futsal/
├── futsal.db            ← déjà là
├── app.py               ← nouveau
├── requirements.txt     ← nouveau
└── schema.sql           ← déjà là (pour référence, pas utilisé par l'appli)
```

## Étape 1 — Installer les bibliothèques

Dans la console IPython de Spyder, tape :

```python
!pip install streamlit plotly pandas
```

Attends que ça finisse. Si déjà installé, tu vois "Requirement already satisfied", c'est bon.

## Étape 2 — Lancer l'appli

**Streamlit ne se lance pas comme un script Python normal.** Il faut le lancer depuis le terminal, pas avec F5 dans Spyder.

### Option A — Depuis l'invite de commande Windows (recommandé)

1. Ouvre l'**invite de commande Windows** (touche Windows → `cmd` → Entrée)
2. Va dans ton dossier :
   ```
   cd C:\chemin\vers\ton_dossier_futsal
   ```
3. Lance :
   ```
   streamlit run app.py
   ```

### Option B — Depuis la console Spyder

Dans la console IPython :

```python
import os
os.chdir(r"C:\chemin\vers\ton_dossier_futsal")
!streamlit run app.py
```

Remplace le chemin par le vrai. Le `r` devant le chemin sert à éviter les soucis avec les antislash Windows.

## Étape 3 — Ton navigateur s'ouvre

Au lancement, tu vois s'afficher :

```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

Ton navigateur s'ouvre automatiquement sur `http://localhost:8501`. Si ce n'est pas le cas, ouvre Chrome/Firefox et colle cette URL.

L'appli apparaît : sidebar à gauche (navigation + filtres), pages au centre.

## Étape 4 — Naviguer

- **Vue équipe** : bilan global, résultats, top buteurs, tableau complet
- **Fiche joueur** : sélectionne un joueur, vois tous ses indicateurs + radar
- **Comparaison** : 2 joueurs côte à côte avec radar superposé
- **Gardiens** : vue dédiée arrêts/relances

Les **filtres globaux** dans la sidebar :
- **Portée** : tous les matchs, ou un match précis
- **Mode** : stats brutes, par minute, ou per 40 min

Les modifs se répercutent instantanément sur toutes les pages.

## Étape 5 — Arrêter l'appli

Dans le terminal qui tourne, appuie sur **Ctrl + C**. L'appli s'éteint, le port se libère.

## Et après ?

Quand tu as validé que ça marche en local, on parlera :
- Déploiement sur **Streamlit Cloud** (gratuit, lien public à partager)
- Ajout des fonctionnalités manquantes : évolution saison, notes manuelles, saisie d'un nouveau match, export PDF

## Si ça plante

Copie-colle ici tout ce qui s'affiche dans le terminal après la commande `streamlit run app.py`, et je débogue.

## Erreurs fréquentes

**`streamlit n'est pas reconnu`** → l'installation a fini ailleurs que dans le PATH. Essaye `python -m streamlit run app.py` à la place.

**`FileNotFoundError: futsal.db`** → tu n'es pas dans le bon dossier. Vérifie avec `dir` (cmd) ou `os.listdir()` (Spyder) que `futsal.db` est bien là.

**Page blanche dans le navigateur** → laisse 5-10 secondes au premier chargement, c'est normal.

**Modifications du code non prises en compte** → en haut à droite de la page, clique sur le menu **⋮ → Rerun** ou tape **R** sur le clavier. Sinon Streamlit Cloud / local détecte les changements de fichier auto.
