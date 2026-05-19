"""
================================================================================
MAJ_COEFFICIENTS.py — Met à jour les coefficients de notation dans futsal.db
================================================================================
À lancer une seule fois pour synchroniser les coefficients de la base SQLite
avec ceux de l'Excel original (CALCUL_NOTE).

USAGE :
    python maj_coefficients.py
================================================================================
"""

import sqlite3
import os

DB_PATH = "futsal.db"

# Paramètres globaux (note de départ + bonus résultat selon temps de présence)
parametres = [
    ("note_depart",     10.0, "Note de départ avant ajustements"),
    ("bonus_victoire",   3.0, "Bonus si victoire (fixe, indépendant du temps de jeu)"),
    ("bonus_nul",        1.5, "Bonus si nul"),
    ("bonus_defaite",    0.0, "Bonus si défaite"),
    ("note_min",         0.0, "Note minimale possible (plafond bas)"),
    ("note_max",        20.0, "Note maximale possible (plafond haut)"),
]

# Coefficients par action — repris EXACTEMENT de CALCUL_NOTE de l'Excel
coefficients = [
    # OFFENSIF
    ("buts",              1.5,  "OFFENSIF", "Buts"),
    ("passes_decisives",  1.0,  "OFFENSIF", "Passes décisives"),
    ("tirs_cadres",       0.75, "OFFENSIF", "Tirs cadrés"),
    ("tirs_contres",      0.25, "OFFENSIF", "Tirs contrés"),
    ("tirs_hors_cadre",   0.1,  "OFFENSIF", "Tirs hors cadre"),
    ("duels_off_gagnes",  0.5,  "OFFENSIF", "Duels OFF gagnés"),
    ("fautes_subies",     0.5,  "OFFENSIF", "Fautes subies"),
    # DÉFENSIF
    ("interceptions",     0.5,  "DEFENSIF", "Interceptions"),
    ("recuperations",     0.5,  "DEFENSIF", "Récupérations"),
    ("duels_def_gagnes",  0.5,  "DEFENSIF", "Duels DEF gagnés"),
    # NÉGATIF
    ("interceptions_adv", -0.5, "NEGATIF",  "Interceptions subies"),
    ("recuperations_adv", -0.5, "NEGATIF",  "Récupérations subies"),
    ("duels_perdus",      -0.5, "NEGATIF",  "Duels perdus"),
    ("fautes_commises",   -0.5, "NEGATIF",  "Fautes commises"),
    ("passes_loupees",    -0.25,"NEGATIF",  "Passes loupées"),
    ("ballons_rendus",    -0.25,"NEGATIF",  "Ballons rendus"),
    ("erreurs_techniques",-0.25,"NEGATIF",  "Erreurs techniques"),
    # GARDIEN
    ("arrets",                       1.0,   "GARDIEN", "Arrêts"),
    ("buts_encaisses",              -0.5,   "GARDIEN", "Buts encaissés"),
    ("relances_faciles_reussies",    0.05,  "GARDIEN", "Relances faciles réussies"),
    ("relances_difficiles_reussies", 0.5,   "GARDIEN", "Relances difficiles réussies"),
    ("relances_faciles_loupees",    -0.5,   "GARDIEN", "Relances faciles loupées"),
    ("relances_difficiles_loupees", -0.1,   "GARDIEN", "Relances difficiles loupées"),
]


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERREUR : {DB_PATH} introuvable.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    # Vider les anciennes valeurs
    conn.execute("DELETE FROM parametre")
    conn.execute("DELETE FROM coefficient")

    # Insérer les nouvelles
    for cle, val, desc in parametres:
        conn.execute(
            "INSERT INTO parametre (cle, valeur, description) VALUES (?, ?, ?)",
            (cle, val, desc)
        )

    for action, coef, famille, libelle in coefficients:
        conn.execute(
            "INSERT INTO coefficient (action, coef, famille, libelle) VALUES (?, ?, ?, ?)",
            (action, coef, famille, libelle)
        )

    conn.commit()

    # Vérification
    print(f"[parametres] {conn.execute('SELECT COUNT(*) FROM parametre').fetchone()[0]} lignes")
    print(f"[coefficients] {conn.execute('SELECT COUNT(*) FROM coefficient').fetchone()[0]} lignes")
    print("\nDétail des paramètres :")
    for row in conn.execute("SELECT cle, valeur, description FROM parametre").fetchall():
        print(f"  {row[0]:20s} = {row[1]:6} | {row[2]}")
    print("\nCoefficients par famille :")
    for f in ("OFFENSIF", "DEFENSIF", "NEGATIF", "GARDIEN"):
        print(f"\n  --- {f} ---")
        for row in conn.execute(
            "SELECT libelle, coef FROM coefficient WHERE famille = ? ORDER BY coef DESC",
            (f,)
        ).fetchall():
            sign = "+" if row[1] > 0 else ""
            print(f"    {row[0]:35s} {sign}{row[1]}")

    conn.close()
    print("\n✓ Mise à jour terminée")


if __name__ == "__main__":
    main()
