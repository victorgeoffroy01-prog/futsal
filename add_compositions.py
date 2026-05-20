"""
add_compositions.py
===================
Script à lancer UNE SEULE FOIS pour ajouter la table 'composition_match' à la base.

Usage :
    python add_compositions.py

La table est créée si elle n'existe pas. Si elle existe déjà, le script ne fait rien
(aucun risque de perdre des données).
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = "futsal.db"

SQL_CREATE = """
CREATE TABLE IF NOT EXISTS composition_match (
    compo_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id     INTEGER NOT NULL REFERENCES match(match_id) ON DELETE CASCADE,
    joueur_id    INTEGER NOT NULL REFERENCES joueur(joueur_id) ON DELETE CASCADE,
    -- Type de poste dans la compo du match
    --   quatuor1 / quatuor2 / quatuor3 : un des 3 quatuors de champ
    --   remplacant                     : joueur de champ remplaçant (peut entrer dans n'importe quel quatuor)
    --   gardien_titulaire              : gardien qui a démarré
    --   gardien_remplacant             : 2e gardien éventuel
    type_compo   TEXT NOT NULL CHECK (type_compo IN (
                    'quatuor1', 'quatuor2', 'quatuor3',
                    'remplacant',
                    'gardien_titulaire', 'gardien_remplacant'
                 )),
    UNIQUE(match_id, joueur_id)
);
"""

SQL_INDEX = """
CREATE INDEX IF NOT EXISTS idx_compo_match ON composition_match(match_id);
"""


def main():
    db_path = Path(DB_PATH)
    if not db_path.exists():
        print(f"❌ Base introuvable : {db_path.resolve()}")
        sys.exit(1)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(SQL_CREATE)
        conn.execute(SQL_INDEX)
        conn.commit()

        # Vérif
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='composition_match'"
        )
        if cur.fetchone():
            print("✅ Table 'composition_match' présente.")
        else:
            print("❌ Échec création.")
            sys.exit(1)

        # Compte existant
        cur = conn.execute("SELECT COUNT(*) FROM composition_match")
        n = cur.fetchone()[0]
        print(f"   {n} entrées de composition en base.")


if __name__ == "__main__":
    main()
