# Déployer l'appli sur Streamlit Cloud (gratuit)

Objectif : avoir un lien public type `edf-u19-futsal.streamlit.app` que tu peux partager au staff. La base de données est hébergée chez Streamlit avec ton code.

Temps total : **20-30 minutes** la première fois.

---

## Étape 1 — Préparer ton dossier futsal

Vérifie que ton dossier `C:\Users\victo\OneDrive\Desktop\futsal` contient au minimum :

```
futsal/
├── app.py
├── futsal.db
├── requirements.txt
├── logo_fff.webp        (optionnel mais recommandé)
├── schema.sql           (peut rester)
├── migration.py         (peut rester)
└── maj_coefficients.py  (peut rester)
```

**Mets à jour requirements.txt** : ouvre-le dans Bloc-notes ou Spyder, et remplace son contenu par :

```
streamlit>=1.30
pandas>=2.0
plotly>=5.18
openpyxl>=3.1
reportlab>=4.0
```

Sauvegarde. **Important** : on a ajouté `reportlab` qui sert pour les PDF.

---

## Étape 2 — Créer un compte GitHub

GitHub est un service gratuit qui stocke ton code en ligne. Streamlit Cloud va se brancher dessus.

1. Va sur https://github.com/signup
2. Renseigne un email, mot de passe, nom d'utilisateur (ex: `victorgoalfutsal`)
3. Valide ton email
4. C'est tout.

---

## Étape 3 — Installer GitHub Desktop

C'est l'outil graphique qui te permet d'envoyer ton dossier sur GitHub sans passer par la ligne de commande.

1. Va sur https://desktop.github.com/
2. Clique sur **"Download for Windows"**
3. Lance l'installation
4. Au premier lancement, il te demande de te connecter avec ton compte GitHub → fais-le

---

## Étape 4 — Mettre ton dossier futsal sur GitHub

Dans GitHub Desktop :

1. Menu **File → Add Local Repository** (ou Ctrl+O)
2. Clique **Choose...** → sélectionne ton dossier `C:\Users\victo\OneDrive\Desktop\futsal`
3. Il va dire "This directory does not appear to be a Git repository" → clique **"create a repository"**
4. Dans la nouvelle fenêtre :
   - **Name** : `edf-u19-futsal` (ou autre nom sans espace)
   - **Description** : "Tableau de bord EDF U19 Futsal"
   - **Local path** : déjà rempli avec ton dossier
   - **Initialize this repository with a README** : décoche (tu as déjà ton README)
   - **Git ignore** : laisse "None"
   - **License** : laisse "None"
   - Clique **"Create repository"**

5. En haut, clique sur **"Publish repository"**
6. Une fenêtre s'ouvre :
   - **Name** : laisse `edf-u19-futsal`
   - **Description** : pareil
   - **Keep this code private** : ⚠️ **DÉCOCHE** cette case. Streamlit Cloud gratuit nécessite un repo public.
   - Clique **"Publish Repository"**

Ton code est maintenant en ligne sur GitHub. Tu peux vérifier en allant sur `https://github.com/TON_USERNAME/edf-u19-futsal`.

> **Note importante** : ton repo est public, ça veut dire que **n'importe qui peut voir le code**. C'est OK parce que le code n'a aucune valeur stratégique. Ce qui est **privé** par contre, c'est qu'on n'a aucune info sensible dedans (pas de mot de passe, pas de données personnelles). Le fichier `futsal.db` est sur GitHub aussi (c'est nécessaire pour que l'appli en ligne y accède), il contient juste des stats sportives.

---

## Étape 5 — Créer un compte Streamlit Cloud

1. Va sur https://streamlit.io/cloud
2. Clique sur **"Sign up"** (ou "Get started")
3. Choisis **"Continue with GitHub"** (le plus simple)
4. Autorise Streamlit à voir tes repos GitHub
5. Bienvenue sur ton dashboard Streamlit Cloud (vide pour l'instant)

---

## Étape 6 — Déployer l'appli

Sur le dashboard Streamlit Cloud :

1. Clique sur le bouton **"Create app"** (ou "New app" en haut à droite)
2. Tu as 3 options, choisis **"Deploy a public app from GitHub"**
3. Remplis :
   - **Repository** : sélectionne `TON_USERNAME/edf-u19-futsal`
   - **Branch** : `main`
   - **Main file path** : `app.py`
   - **App URL (optional)** : tu peux personnaliser, par exemple `edf-u19-futsal` → ça donnera `edf-u19-futsal.streamlit.app`
4. Clique **"Deploy!"**

Streamlit prend 2-3 minutes pour installer Python, les bibliothèques, et lancer ton appli. Tu vois défiler des logs.

Quand c'est prêt, tu vois ton appli dans le navigateur sur l'URL `edf-u19-futsal.streamlit.app` (ou ce que tu as choisi).

**Ce lien, tu peux le partager à n'importe qui** : le staff, les joueurs, sur les réseaux. Pas besoin d'installer quoi que ce soit, ils cliquent et voient l'appli.

---

## Étape 7 — Tester le partage

Envoie-toi le lien sur ton téléphone, ouvre-le → l'appli s'affiche, responsive, lisible. C'est bon.

---

## Comment ça marche après ?

### Tu veux ajouter un match

1. Chez toi, tu ouvres l'appli en local (`python -m streamlit run app.py`)
2. Tu vas dans la page **Saisie**
3. Tu remplis le match + les stats
4. Tu cliques **Enregistrer**

Le match est dans ta `futsal.db` locale. Pour le voir en ligne aussi :

1. Ouvre **GitHub Desktop**
2. Il détecte automatiquement que `futsal.db` a changé
3. En bas à gauche, tape un petit message type "Ajout match Espagne M1"
4. Clique **"Commit to main"**
5. Puis en haut, clique **"Push origin"**

30 secondes après, Streamlit Cloud détecte la mise à jour et redéploie ton appli automatiquement. Le staff voit la nouvelle version au prochain rafraîchissement.

### Tu modifies le code (couleurs, page, etc.)

Pareil :
1. Tu modifies `app.py` en local (Spyder ou Bloc-notes)
2. GitHub Desktop détecte le changement
3. Commit + Push
4. Streamlit Cloud redéploie automatiquement

### Tu veux annuler une modif

Dans GitHub Desktop, **Menu History** → tu vois la liste des modifs. Clic droit sur une ancienne version → **Revert this commit** → Push. Tu reviens en arrière sans perdre tes données.

---

## Limites du plan gratuit

- L'appli "s'endort" après ~7 jours sans visite → premier accès met ~30s à réveiller. Solution : visite l'URL toi-même de temps en temps, ou diffuse-la souvent.
- 1 Go de RAM par appli, largement suffisant pour ton volume.
- Le repo GitHub doit rester public.
- Pas d'authentification native (tout le monde voit l'appli si on a le lien). Si tu veux limiter, on peut ajouter un mot de passe simple en début d'appli.

---

## Si quelque chose se passe mal

**L'appli ne se déploie pas, erreur dans les logs Streamlit**
→ Vérifie que `requirements.txt` est correct (5 lignes, voir Étape 1)
→ Vérifie que `app.py` et `futsal.db` sont bien dans le repo GitHub (tu peux le voir sur github.com)

**"Module not found" pour reportlab ou plotly**
→ Vérifie le contenu de `requirements.txt`, modifie-le si besoin via GitHub Desktop, commit + push

**Le logo FFF ne s'affiche pas**
→ Vérifie que `logo_fff.webp` est bien dans le repo (visible sur github.com)

**Tu ne vois pas tes modifs après un push**
→ Va sur le dashboard Streamlit Cloud, clic sur ton appli → "Manage app" en bas à droite → "Reboot app"

---

Quand tu auras déployé, envoie-moi le lien, je teste de mon côté.
