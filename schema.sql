-- ============================================================================
-- SCHÉMA SQLITE — Tableau de bord Futsal (générique : EDF, club, championnat)
-- ============================================================================
-- Principe : modèle relationnel normalisé.
--   - les STATS BRUTES sont stockées une seule fois (table performance)
--   - les STATS DÉRIVÉES (per 40 min, par minute, %) sont calculées à la volée
--     dans les vues SQL ou dans le code Python (Streamlit)
--   - les NOTES MANUELLES et la GRILLE DE COEFFICIENTS sont séparées,
--     ce qui permet de modifier les coefs sans toucher aux données
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. ENTITÉS DE BASE
-- ----------------------------------------------------------------------------

-- Une équipe = EDF U19, Goal FC U13, etc. Permet de gérer plusieurs équipes
-- dans la même base si besoin (sinon une seule ligne suffit).
CREATE TABLE IF NOT EXISTS equipe (
    equipe_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    nom          TEXT NOT NULL UNIQUE,           -- ex: "EDF U19 Futsal"
    categorie    TEXT,                            -- ex: "U19", "U13", "Senior"
    saison       TEXT,                            -- ex: "2025-2026"
    couleur_hex  TEXT DEFAULT '#FF4B4B',          -- pour la charte du dashboard
    logo_path    TEXT
);

-- Un joueur. Rattaché à une équipe.
-- Numéro et poste peuvent évoluer dans le temps, mais on simplifie : on stocke
-- la version "actuelle" ici, et si besoin la version "match" est dans la table
-- performance (colonnes numero_match, poste_match).
CREATE TABLE IF NOT EXISTS joueur (
    joueur_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    equipe_id    INTEGER NOT NULL REFERENCES equipe(equipe_id) ON DELETE CASCADE,
    nom          TEXT NOT NULL,                   -- ex: "L. LADIRE"
    numero       INTEGER,                          -- ex: 8
    poste        TEXT,                             -- Ailier, Meneur, Meneur côté, Pivot, Gardien
    pied         TEXT,                             -- Droitier, Gaucher
    club         TEXT,                             -- club d'origine
    taille_cm    INTEGER,
    poids_kg     INTEGER,
    actif        INTEGER DEFAULT 1,                -- 1 = actif, 0 = archivé
    UNIQUE(equipe_id, nom)
);

-- Un match.
CREATE TABLE IF NOT EXISTS match (
    match_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    equipe_id     INTEGER NOT NULL REFERENCES equipe(equipe_id) ON DELETE CASCADE,
    code          TEXT NOT NULL UNIQUE,             -- ex: "FRA_CROATIE_M1" (identifiant lisible)
    adversaire    TEXT NOT NULL,
    match_no      INTEGER,                          -- 1, 2... si plusieurs matchs contre même adversaire
    date_match    DATE,
    competition   TEXT,                             -- "Amical", "Tournoi UEFA", "Championnat", etc.
    lieu          TEXT,                             -- "Croatie", "France", ou stade précis
    score_pour    INTEGER NOT NULL DEFAULT 0,       -- buts marqués par l'équipe
    score_contre  INTEGER NOT NULL DEFAULT 0,       -- buts encaissés
    duree_min     INTEGER DEFAULT 40,               -- 40 min standard futsal (utile pour per 40)
    source_file   TEXT,                             -- nom du fichier PDF source si traçabilité
    notes         TEXT                              -- commentaire libre sur le match
);

-- ----------------------------------------------------------------------------
-- 2. TABLE DE FAITS — PERFORMANCES INDIVIDUELLES PAR MATCH
-- ----------------------------------------------------------------------------
-- Une ligne = un joueur dans un match. C'est le coeur des données.
-- Toutes les colonnes sont des stats BRUTES (rien de calculé ici).
-- Les colonnes _40, _pct sont calculées en vue (voir plus bas).

CREATE TABLE IF NOT EXISTS performance (
    perf_id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id                      INTEGER NOT NULL REFERENCES match(match_id) ON DELETE CASCADE,
    joueur_id                     INTEGER NOT NULL REFERENCES joueur(joueur_id) ON DELETE CASCADE,

    -- Contexte : si le joueur a changé de poste/numéro pour ce match, on le note
    numero_match                  INTEGER,
    poste_match                   TEXT,
    role                          TEXT DEFAULT 'Joueur',   -- "Joueur", "Gardien"

    -- Temps de jeu
    temps_jeu_min                 REAL DEFAULT 0,    -- minutes jouées (peut être décimal: 23.5)
    temps_jeu_txt                 TEXT,              -- format texte original "23'00" si utile

    -- OFFENSIF
    buts                          INTEGER DEFAULT 0,
    passes_decisives              INTEGER DEFAULT 0,
    tirs_total                    INTEGER DEFAULT 0,
    tirs_cadres                   INTEGER DEFAULT 0,
    tirs_hors_cadre               INTEGER DEFAULT 0,
    tirs_contres                  INTEGER DEFAULT 0,
    poteau_barre                  INTEGER DEFAULT 0,

    -- NÉGATIF / PERTES
    pertes_de_balles              INTEGER DEFAULT 0,
    passes_loupees                INTEGER DEFAULT 0,
    ballons_rendus                INTEGER DEFAULT 0,
    interceptions_adv             INTEGER DEFAULT 0,   -- interceptions subies par l'adversaire
    duels_perdus                  INTEGER DEFAULT 0,
    erreurs_techniques            INTEGER DEFAULT 0,
    recuperations_adv             INTEGER DEFAULT 0,   -- récupérations subies

    -- DUELS
    duels_off_gagnes              INTEGER DEFAULT 0,
    duels_off_tentes              INTEGER DEFAULT 0,
    duels_def_gagnes              INTEGER DEFAULT 0,
    duels_def_tentes              INTEGER DEFAULT 0,

    -- DISCIPLINE
    fautes_commises               INTEGER DEFAULT 0,
    fautes_subies                 INTEGER DEFAULT 0,

    -- DÉFENSIF
    interceptions                 INTEGER DEFAULT 0,
    recuperations                 INTEGER DEFAULT 0,

    -- GARDIEN (NULL si joueur de champ)
    buts_encaisses                INTEGER,
    arrets                        INTEGER,
    relances_faciles_reussies     INTEGER,
    relances_faciles_loupees      INTEGER,
    relances_difficiles_reussies  INTEGER,
    relances_difficiles_loupees   INTEGER,

    UNIQUE(match_id, joueur_id)   -- un joueur ne peut figurer qu'une fois par match
);

-- ----------------------------------------------------------------------------
-- 3. NOTATION MANUELLE PAR MATCH
-- ----------------------------------------------------------------------------
-- Note 0/5/10 saisie manuellement. Sert à calculer un bonus qui rentre dans
-- la note finale (Brute) en complément des stats objectives.

CREATE TABLE IF NOT EXISTS note_match (
    note_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id     INTEGER NOT NULL REFERENCES match(match_id) ON DELETE CASCADE,
    joueur_id    INTEGER NOT NULL REFERENCES joueur(joueur_id) ON DELETE CASCADE,
    note         INTEGER NOT NULL CHECK (note IN (0, 5, 10)),
    commentaire  TEXT,
    UNIQUE(match_id, joueur_id)
);

-- ----------------------------------------------------------------------------
-- 4. GRILLE DE COEFFICIENTS — paramètres modifiables sans toucher au code
-- ----------------------------------------------------------------------------
-- Stocke : note de départ, bonus victoire/nul/défaite, coef par action.
-- Avantage : tu peux modifier dans l'interface Streamlit et tout est recalculé.

CREATE TABLE IF NOT EXISTS parametre (
    cle         TEXT PRIMARY KEY,         -- ex: "note_depart", "bonus_victoire"
    valeur      REAL NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS coefficient (
    action      TEXT PRIMARY KEY,         -- ex: "buts", "passes_decisives"
    coef        REAL NOT NULL,
    famille     TEXT NOT NULL,            -- "OFFENSIF", "DEFENSIF", "NEGATIF", "GARDIEN"
    libelle     TEXT                       -- nom affiché : "Buts", "Passes décisives"
);

-- ----------------------------------------------------------------------------
-- 5. VUES — calculs dérivés (per 40 min, par minute, %, stats agrégées)
-- ----------------------------------------------------------------------------
-- Ces vues remplacent les colonnes _40, _pct de ton BASE_DATA Excel.
-- Elles se mettent à jour automatiquement quand tu ajoutes des données.

-- Vue 1 : Performance enrichie (brut + per 40 min + pourcentages)
DROP VIEW IF EXISTS v_performance;
CREATE VIEW v_performance AS
SELECT
    p.perf_id, p.match_id, p.joueur_id,
    m.code            AS match_code,
    m.adversaire,
    m.match_no,
    m.date_match,
    m.competition,
    m.lieu,
    j.nom             AS joueur,
    COALESCE(p.numero_match, j.numero) AS numero,
    COALESCE(p.poste_match, j.poste)   AS poste,
    j.pied,
    p.role,
    p.temps_jeu_min,
    p.temps_jeu_txt,
    -- Pourcentage du match joué (sur durée du match)
    CASE WHEN m.duree_min > 0 THEN ROUND(p.temps_jeu_min * 1.0 / m.duree_min, 4) ELSE NULL END AS pct_match,

    -- Stats brutes
    p.buts, p.passes_decisives, p.tirs_total, p.tirs_cadres, p.tirs_hors_cadre, p.tirs_contres,
    p.poteau_barre, p.pertes_de_balles, p.passes_loupees, p.ballons_rendus, p.interceptions_adv,
    p.duels_perdus, p.erreurs_techniques, p.recuperations_adv,
    p.duels_off_gagnes, p.duels_off_tentes, p.duels_def_gagnes, p.duels_def_tentes,
    p.fautes_commises, p.fautes_subies, p.interceptions, p.recuperations,
    p.buts_encaisses, p.arrets,
    p.relances_faciles_reussies, p.relances_faciles_loupees,
    p.relances_difficiles_reussies, p.relances_difficiles_loupees,

    -- Pourcentages calculés
    CASE WHEN p.tirs_total > 0 THEN ROUND(p.tirs_cadres * 1.0 / p.tirs_total, 4) ELSE NULL END AS tirs_cadres_pct,
    CASE WHEN p.duels_off_tentes > 0 THEN ROUND(p.duels_off_gagnes * 1.0 / p.duels_off_tentes, 4) ELSE NULL END AS duels_off_pct,
    CASE WHEN p.duels_def_tentes > 0 THEN ROUND(p.duels_def_gagnes * 1.0 / p.duels_def_tentes, 4) ELSE NULL END AS duels_def_pct,

    -- Stats per 40 min (basées sur le temps joué effectif, pas la durée du match)
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.buts * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS buts_40,
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.passes_decisives * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS pd_40,
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.tirs_total * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS tirs_40,
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.interceptions * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS interceptions_40,
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.recuperations * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS recuperations_40,
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.pertes_de_balles * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS pertes_40,
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.arrets * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS arrets_40,
    CASE WHEN p.temps_jeu_min > 0 THEN ROUND(p.buts_encaisses * 40.0 / p.temps_jeu_min, 4) ELSE NULL END AS buts_encaisses_40,

    -- Relances synthèse
    (COALESCE(p.relances_faciles_reussies,0) + COALESCE(p.relances_difficiles_reussies,0)) AS relances_reussies_total,
    (COALESCE(p.relances_faciles_loupees,0) + COALESCE(p.relances_difficiles_loupees,0)) AS relances_loupees_total,
    CASE
        WHEN (COALESCE(p.relances_faciles_reussies,0) + COALESCE(p.relances_difficiles_reussies,0)
            + COALESCE(p.relances_faciles_loupees,0) + COALESCE(p.relances_difficiles_loupees,0)) > 0
        THEN ROUND(
            (COALESCE(p.relances_faciles_reussies,0) + COALESCE(p.relances_difficiles_reussies,0)) * 1.0 /
            (COALESCE(p.relances_faciles_reussies,0) + COALESCE(p.relances_difficiles_reussies,0)
            + COALESCE(p.relances_faciles_loupees,0) + COALESCE(p.relances_difficiles_loupees,0)), 4)
        ELSE NULL END AS relances_reussite_pct
FROM performance p
JOIN match m  ON m.match_id = p.match_id
JOIN joueur j ON j.joueur_id = p.joueur_id;

-- Vue 2 : Bilan match (résultat, différence de buts)
DROP VIEW IF EXISTS v_match;
CREATE VIEW v_match AS
SELECT
    m.*,
    (m.score_pour - m.score_contre) AS diff_buts,
    CASE
        WHEN m.score_pour > m.score_contre THEN 'Victoire'
        WHEN m.score_pour = m.score_contre THEN 'Nul'
        ELSE 'Défaite'
    END AS resultat
FROM match m;

-- Vue 3 : Cumul équipe (total tous matchs)
DROP VIEW IF EXISTS v_equipe_bilan;
CREATE VIEW v_equipe_bilan AS
SELECT
    e.equipe_id,
    e.nom AS equipe,
    COUNT(DISTINCT m.match_id) AS matchs,
    SUM(CASE WHEN m.score_pour > m.score_contre THEN 1 ELSE 0 END) AS victoires,
    SUM(CASE WHEN m.score_pour = m.score_contre THEN 1 ELSE 0 END) AS nuls,
    SUM(CASE WHEN m.score_pour < m.score_contre THEN 1 ELSE 0 END) AS defaites,
    SUM(m.score_pour) AS buts_pour,
    SUM(m.score_contre) AS buts_contre
FROM equipe e
LEFT JOIN match m ON m.equipe_id = e.equipe_id
GROUP BY e.equipe_id, e.nom;

-- ----------------------------------------------------------------------------
-- 6. INDEX pour les requêtes fréquentes
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_perf_match  ON performance(match_id);
CREATE INDEX IF NOT EXISTS idx_perf_joueur ON performance(joueur_id);
CREATE INDEX IF NOT EXISTS idx_match_equipe ON match(equipe_id);
CREATE INDEX IF NOT EXISTS idx_joueur_equipe ON joueur(equipe_id);
