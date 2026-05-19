"""
================================================================================
TABLEAU DE BORD FUTSAL — EDF U19   (v5)
================================================================================
Nouveautés v5 :
- Fiche joueur vs Moyenne équipe : choix du mode (Brutes / Par min / Per 40)
- Logo FFF affiché en haut (sidebar + accueil)
- Page Saisie : ajouter un nouveau match directement dans l'appli
- Export PDF : fiche joueur + tableau de notation d'un match (ReportLab)
================================================================================
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
from pathlib import Path
from datetime import date, datetime
from io import BytesIO

# Pour l'export PDF
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
    PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ============================================================================
# CONFIG
# ============================================================================

DB_PATH = "futsal.db"
PHOTOS_DIR = Path("photos")
LOGO_PATH = Path("logo_fff.webp")  # ou .png si tu changes

COULEUR_PRIMAIRE = "#FF4B4B"
COULEUR_BLEU     = "#185FA5"
COULEUR_VERT     = "#1D9E75"
COULEUR_AMBRE    = "#EF9F27"
COULEUR_GRIS     = "#888888"
COULEUR_MOY      = "#EF9F27"

st.set_page_config(
    page_title="EDF U19 Futsal",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; }
    h1 { font-size: 2rem !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# UTILS
# ============================================================================

def normaliser_nom(nom):
    if not nom:
        return nom
    return str(nom).upper().strip()


def photo_joueur(nom):
    if not PHOTOS_DIR.exists():
        return None
    safe = nom.replace(" ", "_").replace(".", "")
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = PHOTOS_DIR / f"{safe}.{ext}"
        if p.exists():
            return str(p)
    return None


# ============================================================================
# ACCÈS DONNÉES
# ============================================================================

@st.cache_data(ttl=30)
def charger(query, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    if "joueur" in df.columns:
        df["joueur"] = df["joueur"].apply(normaliser_nom)
    return df


def executer(query, params=()):
    """Pour les écritures (INSERT/UPDATE)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid


def get_equipe():
    return charger("SELECT * FROM equipe LIMIT 1").iloc[0]


def get_matchs():
    return charger("""
        SELECT match_id, code, adversaire, match_no, lieu,
               score_pour, score_contre, resultat, diff_buts,
               (adversaire || ' M' || match_no) AS libelle
        FROM v_match
        ORDER BY match_id
    """)


def get_perfs(match_filter=None):
    if match_filter is None:
        return charger("SELECT * FROM v_performance ORDER BY joueur, match_id")
    return charger("SELECT * FROM v_performance WHERE match_id = ? ORDER BY joueur",
                   (match_filter,))


def get_coefficients():
    df = charger("SELECT action, coef FROM coefficient")
    return dict(zip(df["action"], df["coef"]))


def get_parametres():
    df = charger("SELECT cle, valeur FROM parametre")
    return dict(zip(df["cle"], df["valeur"]))


def get_joueurs_liste():
    """Liste de tous les joueurs (pour la saisie)."""
    return charger("""
        SELECT joueur_id, nom, numero, poste
        FROM joueur
        WHERE actif = 1
        ORDER BY nom
    """)


# ============================================================================
# CALCULS
# ============================================================================

STATS_MODE = [
    "buts", "passes_decisives", "tirs_total", "tirs_cadres", "tirs_hors_cadre",
    "tirs_contres", "pertes_de_balles", "passes_loupees", "ballons_rendus",
    "interceptions_adv", "duels_perdus", "erreurs_techniques", "recuperations_adv",
    "duels_off_gagnes", "duels_def_gagnes", "duels_off_tentes", "duels_def_tentes",
    "fautes_commises", "fautes_subies",
    "interceptions", "recuperations", "buts_encaisses", "arrets",
    "relances_reussies_total", "relances_loupees_total",
    "relances_faciles_reussies", "relances_difficiles_reussies",
    "relances_faciles_loupees", "relances_difficiles_loupees"
]


def appliquer_mode(df, mode):
    if mode == "Stats brutes":
        return df
    df = df.copy()
    for col in STATS_MODE:
        if col in df.columns:
            if mode == "Par minute":
                df[col] = df.apply(
                    lambda r: r[col] / r["temps_jeu_min"] if r["temps_jeu_min"] and r["temps_jeu_min"] > 0 else None,
                    axis=1
                )
            elif mode == "Per 40 min":
                df[col] = df.apply(
                    lambda r: r[col] * 40 / r["temps_jeu_min"] if r["temps_jeu_min"] and r["temps_jeu_min"] > 0 else None,
                    axis=1
                )
    return df


def agreger_joueur(df, mode):
    if df.empty:
        return df
    texte_cols = ["joueur", "poste", "pied", "numero", "role"]
    texte_cols = [c for c in texte_cols if c in df.columns]
    sums = df.groupby("joueur_id").agg(
        **{c: (c, "first") for c in texte_cols},
        matchs=("match_id", "nunique"),
        temps_jeu_min=("temps_jeu_min", "sum"),
        **{c: (c, "sum") for c in STATS_MODE if c in df.columns}
    ).reset_index()
    sums["tirs_cadres_pct"] = sums.apply(
        lambda r: r["tirs_cadres"] / r["tirs_total"] if r["tirs_total"] else None, axis=1)
    if mode == "Par minute":
        for c in STATS_MODE:
            if c in sums.columns:
                sums[c] = sums.apply(
                    lambda r: r[c] / r["temps_jeu_min"] if r["temps_jeu_min"] > 0 else None, axis=1)
    elif mode == "Per 40 min":
        for c in STATS_MODE:
            if c in sums.columns:
                sums[c] = sums.apply(
                    lambda r: r[c] * 40 / r["temps_jeu_min"] if r["temps_jeu_min"] > 0 else None, axis=1)
    return sums


def fmt(v, mode):
    if v is None or pd.isna(v):
        return "-"
    if mode == "Stats brutes":
        return f"{int(round(v))}"
    return f"{v:.2f}"


def fmt_pct(v):
    if v is None or pd.isna(v):
        return "-"
    return f"{v*100:.0f}%"


def calculer_note_match(perf_row, match_row, coefs, params):
    """Calcule la note Brute pour une perf joueur dans un match."""
    note = params["note_depart"]

    delta_off = (
        (perf_row.get("buts", 0) or 0) * coefs.get("buts", 0) +
        (perf_row.get("passes_decisives", 0) or 0) * coefs.get("passes_decisives", 0) +
        (perf_row.get("tirs_cadres", 0) or 0) * coefs.get("tirs_cadres", 0) +
        (perf_row.get("tirs_contres", 0) or 0) * coefs.get("tirs_contres", 0) +
        (perf_row.get("tirs_hors_cadre", 0) or 0) * coefs.get("tirs_hors_cadre", 0) +
        (perf_row.get("duels_off_gagnes", 0) or 0) * coefs.get("duels_off_gagnes", 0) +
        (perf_row.get("fautes_subies", 0) or 0) * coefs.get("fautes_subies", 0)
    )
    delta_def = (
        (perf_row.get("interceptions", 0) or 0) * coefs.get("interceptions", 0) +
        (perf_row.get("recuperations", 0) or 0) * coefs.get("recuperations", 0) +
        (perf_row.get("duels_def_gagnes", 0) or 0) * coefs.get("duels_def_gagnes", 0)
    )
    delta_neg = (
        (perf_row.get("interceptions_adv", 0) or 0) * coefs.get("interceptions_adv", 0) +
        (perf_row.get("recuperations_adv", 0) or 0) * coefs.get("recuperations_adv", 0) +
        (perf_row.get("duels_perdus", 0) or 0) * coefs.get("duels_perdus", 0) +
        (perf_row.get("fautes_commises", 0) or 0) * coefs.get("fautes_commises", 0) +
        (perf_row.get("passes_loupees", 0) or 0) * coefs.get("passes_loupees", 0) +
        (perf_row.get("ballons_rendus", 0) or 0) * coefs.get("ballons_rendus", 0) +
        (perf_row.get("erreurs_techniques", 0) or 0) * coefs.get("erreurs_techniques", 0)
    )
    delta_gk = 0
    if perf_row.get("role") == "Gardien":
        delta_gk = (
            (perf_row.get("arrets", 0) or 0) * coefs.get("arrets", 0) +
            (perf_row.get("buts_encaisses", 0) or 0) * coefs.get("buts_encaisses", 0) +
            (perf_row.get("relances_faciles_reussies", 0) or 0) * coefs.get("relances_faciles_reussies", 0) +
            (perf_row.get("relances_difficiles_reussies", 0) or 0) * coefs.get("relances_difficiles_reussies", 0) +
            (perf_row.get("relances_faciles_loupees", 0) or 0) * coefs.get("relances_faciles_loupees", 0) +
            (perf_row.get("relances_difficiles_loupees", 0) or 0) * coefs.get("relances_difficiles_loupees", 0)
        )

    if match_row["resultat"] == "Victoire":
        bonus = params["bonus_victoire"]
    elif match_row["resultat"] == "Nul":
        bonus = params["bonus_nul"]
    else:
        bonus = params["bonus_defaite"]

    brute = note + delta_off + delta_def + delta_neg + delta_gk + bonus
    note_finale = max(params["note_min"], min(params["note_max"], brute))

    return {
        "delta_off": round(delta_off, 2), "delta_def": round(delta_def, 2),
        "delta_neg": round(delta_neg, 2), "delta_gk": round(delta_gk, 2),
        "bonus": round(bonus, 2), "brute": round(brute, 2),
        "note": round(note_finale, 2)
    }


# ============================================================================
# COMPOSANTS VISUELS
# ============================================================================

def barres_horizontales(df, col_val, titre, couleur=COULEUR_PRIMAIRE, top_n=10):
    df = df.copy()
    df = df[df[col_val] > 0].sort_values(col_val, ascending=True).tail(top_n)
    if df.empty:
        st.caption(f"_{titre} : aucune donnée_")
        return
    fig = go.Figure(go.Bar(
        x=df[col_val], y=df["joueur"], orientation="h",
        marker=dict(color=couleur),
        text=df[col_val].apply(lambda v: f"{int(v)}" if v == int(v) else f"{v:.2f}"),
        textposition="outside", textfont=dict(size=12)
    ))
    fig.update_layout(
        title=dict(text=titre, font=dict(size=15)),
        height=max(280, 32 * len(df) + 80),
        margin=dict(l=10, r=40, t=50, b=20),
        xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
        yaxis=dict(showgrid=False, automargin=True),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)


def barres_horizontales_comparaison(labels, val_joueur, val_moyenne,
                                     nom_joueur="Joueur", nom_ref="Moy. Équipe"):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=val_moyenne, orientation='h', name=nom_ref,
        marker=dict(color=COULEUR_MOY),
        text=[f"{v:.1f}" if isinstance(v, (int, float)) and not pd.isna(v) else "" for v in val_moyenne],
        textposition="outside", textfont=dict(size=11)
    ))
    fig.add_trace(go.Bar(
        y=labels, x=val_joueur, orientation='h', name=nom_joueur,
        marker=dict(color=COULEUR_BLEU),
        text=[f"{v:.1f}" if isinstance(v, (int, float)) and not pd.isna(v) else "" for v in val_joueur],
        textposition="outside", textfont=dict(size=11)
    ))
    fig.update_layout(
        barmode='group',
        height=max(380, 50 * len(labels) + 50),
        margin=dict(l=10, r=50, t=30, b=20),
        xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
        yaxis=dict(showgrid=False, automargin=True),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=-0.08)
    )
    return fig


def radar_normalise(valeurs_joueur, valeurs_ref, libelles, nom_joueur="Joueur",
                    nom_ref="Moy. équipe"):
    n = len(libelles)
    maxes = [max(abs(valeurs_joueur[i] or 0), abs(valeurs_ref[i] or 0), 0.001) for i in range(n)]
    v_j_norm = [(valeurs_joueur[i] or 0) / maxes[i] for i in range(n)]
    v_r_norm = [(valeurs_ref[i] or 0) / maxes[i] for i in range(n)]
    labels_enrichis = [
        f"{libelles[i]}<br>(J: {valeurs_joueur[i]:.1f} / M: {valeurs_ref[i]:.1f})"
        for i in range(n)
    ]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=v_r_norm + [v_r_norm[0]],
        theta=labels_enrichis + [labels_enrichis[0]],
        fill='toself', name=nom_ref,
        line=dict(color=COULEUR_MOY, width=2.5),
        fillcolor=COULEUR_MOY, opacity=0.35,
        marker=dict(size=7)
    ))
    fig.add_trace(go.Scatterpolar(
        r=v_j_norm + [v_j_norm[0]],
        theta=labels_enrichis + [labels_enrichis[0]],
        fill='toself', name=nom_joueur,
        line=dict(color=COULEUR_BLEU, width=2.5),
        fillcolor=COULEUR_BLEU, opacity=0.45,
        marker=dict(size=7)
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1.1],
                            tickfont=dict(size=9, color="#666"),
                            gridcolor="rgba(128,128,128,0.3)",
                            tickvals=[0.25, 0.5, 0.75, 1.0],
                            ticktext=["", "", "", "max"]),
            angularaxis=dict(tickfont=dict(size=11, color="#FAFAFA"),
                             gridcolor="rgba(128,128,128,0.3)"),
            bgcolor="rgba(0,0,0,0)"
        ),
        showlegend=True, height=460,
        legend=dict(orientation="h", yanchor="bottom", y=-0.18,
                    xanchor="center", x=0.5, font=dict(size=12)),
        margin=dict(l=70, r=70, t=30, b=70),
        paper_bgcolor="rgba(0,0,0,0)"
    )
    return fig


def radar_comparaison_2joueurs(stats1, stats2, nom1, nom2):
    libelles = list(stats1.keys())
    v1 = [stats1[k] or 0 for k in libelles]
    v2 = [stats2[k] or 0 for k in libelles]
    n = len(libelles)
    maxes = [max(abs(v1[i]), abs(v2[i]), 0.001) for i in range(n)]
    v1n = [v1[i] / maxes[i] for i in range(n)]
    v2n = [v2[i] / maxes[i] for i in range(n)]
    labels_enrichis = [
        f"{libelles[i]}<br>({nom1[:8]}: {v1[i]:.1f} / {nom2[:8]}: {v2[i]:.1f})"
        for i in range(n)
    ]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=v1n + [v1n[0]], theta=labels_enrichis + [labels_enrichis[0]], fill='toself',
        name=nom1, line=dict(color=COULEUR_PRIMAIRE, width=2.5),
        fillcolor=COULEUR_PRIMAIRE, opacity=0.4, marker=dict(size=7)
    ))
    fig.add_trace(go.Scatterpolar(
        r=v2n + [v2n[0]], theta=labels_enrichis + [labels_enrichis[0]], fill='toself',
        name=nom2, line=dict(color=COULEUR_BLEU, width=2.5),
        fillcolor=COULEUR_BLEU, opacity=0.4, marker=dict(size=7)
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1.1],
                            tickfont=dict(size=9, color="#666"),
                            gridcolor="rgba(128,128,128,0.3)",
                            tickvals=[0.25, 0.5, 0.75, 1.0],
                            ticktext=["", "", "", "max"]),
            angularaxis=dict(tickfont=dict(size=11, color="#FAFAFA"),
                             gridcolor="rgba(128,128,128,0.3)"),
            bgcolor="rgba(0,0,0,0)"
        ),
        showlegend=True, height=460,
        legend=dict(orientation="h", yanchor="bottom", y=-0.18,
                    xanchor="center", x=0.5, font=dict(size=12)),
        margin=dict(l=70, r=70, t=30, b=70),
        paper_bgcolor="rgba(0,0,0,0)"
    )
    return fig


def graphe_evolution_equipe(matchs):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=matchs["libelle"], y=matchs["score_pour"],
        mode='lines+markers+text', name='Buts pour',
        line=dict(color=COULEUR_PRIMAIRE, width=3),
        marker=dict(size=12),
        text=matchs["score_pour"], textposition='top center',
        textfont=dict(size=13, color=COULEUR_PRIMAIRE)
    ))
    fig.add_trace(go.Scatter(
        x=matchs["libelle"], y=matchs["score_contre"],
        mode='lines+markers+text', name='Buts contre',
        line=dict(color=COULEUR_GRIS, width=3, dash='dash'),
        marker=dict(size=12),
        text=matchs["score_contre"], textposition='bottom center',
        textfont=dict(size=13, color=COULEUR_GRIS)
    ))
    fig.update_layout(
        title="Évolution buts pour / contre",
        height=380, margin=dict(l=10, r=10, t=50, b=20),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)", title="Buts"),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=-0.15)
    )
    return fig


def graphe_evolution_joueur(df_j, indicateur, libelle, couleur=COULEUR_PRIMAIRE):
    df = df_j.copy()
    df["match_label"] = df["adversaire"] + " M" + df["match_no"].astype(str)
    fig = go.Figure(go.Bar(
        x=df["match_label"], y=df[indicateur],
        marker=dict(color=couleur),
        text=df[indicateur].apply(lambda v: f"{int(v)}" if pd.notna(v) and v == int(v) else (f"{v:.2f}" if pd.notna(v) else "")),
        textposition="outside", textfont=dict(size=12)
    ))
    fig.update_layout(
        title=libelle, height=300,
        margin=dict(l=10, r=10, t=50, b=20),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False
    )
    return fig


# ============================================================================
# EXPORT PDF
# ============================================================================

def pdf_fiche_joueur(joueur, agg_brut, agg_40, perfs_joueur, notes_joueur, equipe_nom):
    """Génère un PDF de fiche joueur (BytesIO)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=18,
                        textColor=colors.HexColor("#185FA5"))
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontSize=13,
                        textColor=colors.HexColor("#FF4B4B"), spaceAfter=6)
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=9,
                           textColor=colors.grey)

    # En-tête
    story.append(Paragraph(f"<b>{equipe_nom}</b> — Fiche joueur", h1))
    story.append(Paragraph(joueur, ParagraphStyle('j', parent=styles['Heading2'],
                                                   fontSize=22, alignment=TA_LEFT)))
    story.append(Paragraph(
        f"{agg_brut.get('poste','-')} · N°{int(agg_brut['numero']) if pd.notna(agg_brut.get('numero')) else '-'} · "
        f"{int(agg_brut['matchs'])} matchs · {agg_brut['temps_jeu_min']:.1f} minutes jouées",
        small
    ))
    story.append(Paragraph(
        f"<i>Document généré le {date.today().strftime('%d/%m/%Y')}</i>", small
    ))
    story.append(Spacer(1, 0.5*cm))

    # Stats brutes vs per 40
    story.append(Paragraph("Statistiques", h2))
    data = [["Indicateur", "Total (brut)", "Per 40 min"]]
    rows = [
        ("Buts", "buts"),
        ("Passes décisives", "passes_decisives"),
        ("Tirs total", "tirs_total"),
        ("Tirs cadrés", "tirs_cadres"),
        ("Interceptions", "interceptions"),
        ("Récupérations", "recuperations"),
        ("Duels OFF gagnés", "duels_off_gagnes"),
        ("Duels DEF gagnés", "duels_def_gagnes"),
        ("Pertes de balle", "pertes_de_balles"),
        ("Fautes commises", "fautes_commises"),
        ("Fautes subies", "fautes_subies"),
    ]
    for lbl, col in rows:
        v_brut = agg_brut.get(col, 0)
        v_40 = agg_40.get(col, 0)
        data.append([
            lbl,
            f"{int(v_brut)}" if pd.notna(v_brut) else "-",
            f"{v_40:.2f}" if pd.notna(v_40) else "-"
        ])
    t = Table(data, colWidths=[6*cm, 4*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#185FA5")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ('PADDING', (0,0), (-1,-1), 5)
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # Détail match par match
    if not perfs_joueur.empty and len(perfs_joueur) > 1:
        story.append(Paragraph("Détail match par match", h2))
        det = [["Match", "Min", "B", "PD", "Tirs", "T.cad", "Inter.", "Récup.", "Pertes"]]
        for _, p in perfs_joueur.iterrows():
            det.append([
                p["match_code"],
                f"{p['temps_jeu_min']:.1f}",
                str(int(p["buts"] or 0)),
                str(int(p["passes_decisives"] or 0)),
                str(int(p["tirs_total"] or 0)),
                str(int(p["tirs_cadres"] or 0)),
                str(int(p["interceptions"] or 0)),
                str(int(p["recuperations"] or 0)),
                str(int(p["pertes_de_balles"] or 0)),
            ])
        t2 = Table(det, colWidths=[3.5*cm, 1.5*cm, 1*cm, 1*cm, 1*cm, 1.2*cm, 1.4*cm, 1.4*cm, 1.4*cm])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#FF4B4B")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
            ('PADDING', (0,0), (-1,-1), 4)
        ]))
        story.append(t2)
        story.append(Spacer(1, 0.5*cm))

    # Notes
    if notes_joueur:
        story.append(Paragraph("Notation", h2))
        note_data = [["Match", "Δ OFF", "Δ DEF", "Δ NEG", "Bonus", "Brute", "Note /20"]]
        for n in notes_joueur:
            note_data.append([
                n["match"], f"{n['delta_off']:+.2f}", f"{n['delta_def']:+.2f}",
                f"{n['delta_neg']:+.2f}", f"{n['bonus']:+.1f}",
                f"{n['brute']:.2f}", f"{n['note']:.2f}"
            ])
        # Moyenne
        avg_note = sum(n["note"] for n in notes_joueur) / len(notes_joueur)
        note_data.append(["MOYENNE", "", "", "", "", "", f"{avg_note:.2f}"])

        t3 = Table(note_data, colWidths=[3.5*cm, 2*cm, 2*cm, 2*cm, 1.8*cm, 2*cm, 2*cm])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1D9E75")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.whitesmoke, colors.white]),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#185FA5")),
            ('TEXTCOLOR', (0,-1), (-1,-1), colors.white),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('PADDING', (0,0), (-1,-1), 4)
        ]))
        story.append(t3)

    doc.build(story)
    buf.seek(0)
    return buf


def pdf_notation_match(match_libelle, notes_match, equipe_nom):
    """PDF avec les notes de tous les joueurs d'un match."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=18,
                        textColor=colors.HexColor("#185FA5"))
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=9,
                           textColor=colors.grey)

    story.append(Paragraph(f"<b>{equipe_nom}</b> — Notation du match", h1))
    story.append(Paragraph(match_libelle, ParagraphStyle('m', parent=styles['Heading2'],
                                                          fontSize=18)))
    story.append(Paragraph(f"<i>Document généré le {date.today().strftime('%d/%m/%Y')}</i>", small))
    story.append(Spacer(1, 0.5*cm))

    data = [["Joueur", "Poste", "Min", "Δ OFF", "Δ DEF", "Δ NEG", "Δ GK", "Bonus", "Brute", "Note /20"]]
    notes_sorted = sorted(notes_match, key=lambda x: x["note"], reverse=True)
    for n in notes_sorted:
        data.append([
            n["joueur"], n["poste"] or "-", f"{n['min']:.1f}",
            f"{n['delta_off']:+.2f}", f"{n['delta_def']:+.2f}",
            f"{n['delta_neg']:+.2f}", f"{n['delta_gk']:+.2f}",
            f"{n['bonus']:+.1f}", f"{n['brute']:.2f}", f"{n['note']:.2f}"
        ])
    t = Table(data, colWidths=[4*cm, 2.5*cm, 1.5*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.5*cm, 1.5*cm, 1.8*cm, 2*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#185FA5")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ('ALIGN', (2,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ('PADDING', (0,0), (-1,-1), 4)
    ]))
    story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf
# ============================================================================
# SIDEBAR
# ============================================================================

equipe = get_equipe()
matchs = get_matchs()

with st.sidebar:
    # Logo FFF
    if LOGO_PATH.exists():
        col_logo1, col_logo2, col_logo3 = st.columns([1, 2, 1])
        with col_logo2:
            st.image(str(LOGO_PATH), width=110)
    st.markdown("### ⚽ EDF U19 Futsal")
    st.caption(f"{equipe['categorie']} · Saison {equipe['saison']}")

    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["Accueil", "Vue équipe", "Fiche joueur", "Comparaison",
         "Gardiens", "Évolution", "Notation", "Saisie", "Légende"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.markdown("**Filtres globaux**")
    portee = st.selectbox("Portée", ["Tous les matchs"] + matchs["libelle"].tolist())
    mode = st.selectbox("Mode", ["Stats brutes", "Par minute", "Per 40 min"])

    st.markdown("---")
    st.caption(f"{len(matchs)} matchs · {charger('SELECT COUNT(*) AS n FROM joueur').iloc[0]['n']} joueurs")


match_id_filtre = None
if portee != "Tous les matchs":
    match_id_filtre = int(matchs.loc[matchs["libelle"] == portee, "match_id"].iloc[0])

perfs_raw = get_perfs(match_id_filtre)
perfs_mode = appliquer_mode(perfs_raw, mode) if match_id_filtre else perfs_raw


# ============================================================================
# PAGE — ACCUEIL
# ============================================================================

if page == "Accueil":
    # En-tête avec logo
    col_logo, col_titre = st.columns([1, 5])
    with col_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=100)
    with col_titre:
        st.markdown("# Tableau de bord — EDF U19 Futsal")
        st.markdown(f"_{equipe['categorie']} · Saison {equipe['saison']}_")

    st.markdown("---")
    bilan = charger("SELECT * FROM v_equipe_bilan").iloc[0]
    st.markdown("### Bilan de la saison")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Matchs joués", int(bilan["matchs"]))
    c2.metric("Victoires", int(bilan["victoires"]))
    c3.metric("Nuls", int(bilan["nuls"]))
    c4.metric("Défaites", int(bilan["defaites"]))
    c5.metric("Buts pour", int(bilan["buts_pour"]))
    c6.metric("Buts contre", int(bilan["buts_contre"]))

    st.markdown("---")
    col_g, col_d = st.columns([1.3, 1])

    with col_g:
        st.markdown("### Derniers matchs")
        derniers = matchs.tail(5)[::-1]
        for _, m in derniers.iterrows():
            couleur = COULEUR_VERT if m["resultat"] == "Victoire" else (COULEUR_AMBRE if m["resultat"] == "Nul" else COULEUR_PRIMAIRE)
            st.markdown(f"""
            <div style="background:rgba(128,128,128,0.08);padding:10px 14px;border-radius:6px;
                        border-left:4px solid {couleur};margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <strong>{m['libelle']}</strong>
                        <span style="color:#888;margin-left:8px;">· {m['lieu'] or '-'}</span>
                    </div>
                    <div style="font-size:18px;font-weight:600;">
                        {m['score_pour']} - {m['score_contre']}
                        <span style="color:{couleur};margin-left:10px;font-size:14px;">{m['resultat']}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with col_d:
        agg_all = agreger_joueur(get_perfs(), "Stats brutes")
        agg_all = agg_all[agg_all["role"] != "Gardien"].copy()
        st.markdown("### Top buteur")
        top1 = agg_all.sort_values("buts", ascending=False).iloc[0]
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,{COULEUR_PRIMAIRE}33,{COULEUR_PRIMAIRE}10);
                    padding:18px;border-radius:8px;border:1px solid {COULEUR_PRIMAIRE};
                    text-align:center;">
            <div style="font-size:13px;color:#888;text-transform:uppercase;">Meilleur buteur</div>
            <div style="font-size:22px;font-weight:600;margin-top:6px;">{top1['joueur']}</div>
            <div style="font-size:13px;color:#888;">{top1['poste'] or ''}</div>
            <div style="font-size:38px;font-weight:700;color:{COULEUR_PRIMAIRE};margin-top:8px;">
                {int(top1['buts'])}
            </div>
            <div style="font-size:12px;color:#888;">buts</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(" ")
        st.markdown("### Top passeur")
        top_pd = agg_all.sort_values("passes_decisives", ascending=False).iloc[0]
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,{COULEUR_BLEU}33,{COULEUR_BLEU}10);
                    padding:18px;border-radius:8px;border:1px solid {COULEUR_BLEU};
                    text-align:center;">
            <div style="font-size:13px;color:#888;text-transform:uppercase;">Meilleur passeur</div>
            <div style="font-size:22px;font-weight:600;margin-top:6px;">{top_pd['joueur']}</div>
            <div style="font-size:13px;color:#888;">{top_pd['poste'] or ''}</div>
            <div style="font-size:38px;font-weight:700;color:{COULEUR_BLEU};margin-top:8px;">
                {int(top_pd['passes_decisives'])}
            </div>
            <div style="font-size:12px;color:#888;">passes décisives</div>
        </div>
        """, unsafe_allow_html=True)


# ============================================================================
# PAGE — VUE ÉQUIPE
# ============================================================================

elif page == "Vue équipe":
    st.title("Vue équipe")
    st.caption(f"Portée : {portee} · Mode : {mode}")

    if match_id_filtre is None:
        bilan = charger("SELECT * FROM v_equipe_bilan").iloc[0]
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Matchs", int(bilan["matchs"]))
        c2.metric("Victoires", int(bilan["victoires"]))
        c3.metric("Nuls", int(bilan["nuls"]))
        c4.metric("Défaites", int(bilan["defaites"]))
        c5.metric("Buts pour", int(bilan["buts_pour"]))
        c6.metric("Buts contre", int(bilan["buts_contre"]))
    else:
        m = matchs[matchs["match_id"] == match_id_filtre].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Adversaire", m["adversaire"])
        c2.metric("Score", f"{m['score_pour']} - {m['score_contre']}")
        c3.metric("Résultat", m["resultat"])
        c4.metric("Lieu", m["lieu"] or "-")

    st.markdown("---")
    col_gauche, col_droite = st.columns([1, 1])

    with col_gauche:
        st.subheader("Résultats")
        tab = matchs[["libelle", "lieu", "score_pour", "score_contre", "resultat", "diff_buts"]].copy()
        tab.columns = ["Match", "Lieu", "Buts pour", "Buts contre", "Résultat", "Diff"]
        st.dataframe(tab, hide_index=True, use_container_width=True)

    with col_droite:
        st.subheader("Top contributeurs (cumul tous matchs)")
        agg_all = agreger_joueur(get_perfs(), "Stats brutes")
        top = agg_all[(agg_all["buts"] > 0) | (agg_all["passes_decisives"] > 0)].copy()
        top["B + PD"] = top["buts"] + top["passes_decisives"]
        top = top.sort_values("B + PD", ascending=False).head(8)
        top_display = top[["joueur", "poste", "buts", "passes_decisives", "B + PD"]].copy()
        top_display.columns = ["Joueur", "Poste", "Buts", "PD", "B+PD"]
        st.dataframe(top_display, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Stats équipe — tous joueurs")

    if match_id_filtre is None:
        df_aff = agreger_joueur(perfs_mode, mode)
    else:
        df_aff = perfs_mode.copy()
        df_aff["matchs"] = 1

    if not df_aff.empty:
        df_aff = df_aff[df_aff["role"] != "Gardien"].copy()
        cols_aff = {
            "joueur": "Joueur", "poste": "Poste", "matchs": "M", "temps_jeu_min": "Min",
            "buts": "B", "passes_decisives": "PD",
            "tirs_total": "Tirs", "tirs_cadres": "T.cad",
            "interceptions": "Inter.", "recuperations": "Récup.",
            "pertes_de_balles": "Pertes", "duels_off_gagnes": "D.OFF+", "duels_def_gagnes": "D.DEF+"
        }
        df_aff = df_aff[[c for c in cols_aff if c in df_aff.columns]]
        df_aff.columns = [cols_aff[c] for c in df_aff.columns]
        for c in df_aff.columns:
            if c not in ["Joueur", "Poste"]:
                if mode == "Stats brutes" or c in ["M", "Min"]:
                    df_aff[c] = df_aff[c].apply(lambda v: int(round(v)) if pd.notna(v) else None)
                else:
                    df_aff[c] = df_aff[c].apply(lambda v: round(v, 2) if pd.notna(v) else None)
        st.dataframe(df_aff.sort_values("B", ascending=False), hide_index=True, use_container_width=True)


# ============================================================================
# PAGE — FICHE JOUEUR
# ============================================================================

elif page == "Fiche joueur":
    st.title("Fiche joueur")
    st.caption(f"Portée : {portee} · Mode : {mode}")

    joueurs_dispo = sorted(perfs_mode[perfs_mode["role"] != "Gardien"]["joueur"].unique())
    if len(joueurs_dispo) == 0:
        st.warning("Aucun joueur de champ sur cette portée.")
        st.stop()

    joueur_sel = st.selectbox("Sélectionner un joueur", joueurs_dispo)

    df_j = perfs_mode[perfs_mode["joueur"] == joueur_sel].copy()
    df_j_brut = perfs_raw[perfs_raw["joueur"] == joueur_sel].copy()

    if match_id_filtre is None:
        agg = agreger_joueur(df_j, mode).iloc[0]
        agg_brut = agreger_joueur(df_j_brut, "Stats brutes").iloc[0]
    else:
        agg = df_j.iloc[0]
        agg_brut = df_j_brut.iloc[0]
        agg = pd.concat([agg, pd.Series({"matchs": 1})])
        agg_brut = pd.concat([agg_brut, pd.Series({"matchs": 1})])

    photo = photo_joueur(joueur_sel)
    c_photo, c_info = st.columns([1, 4])
    with c_photo:
        if photo:
            st.image(photo, width=140)
        else:
            initiales = "".join([p[0] for p in joueur_sel.split() if p])[:2]
            st.markdown(f"""
                <div style="width:120px;height:120px;border-radius:50%;
                            background:{COULEUR_PRIMAIRE};display:flex;
                            align-items:center;justify-content:center;
                            color:white;font-size:42px;font-weight:600;">
                    {initiales}
                </div>
                <div style="font-size:11px;color:#888;margin-top:8px;">
                    photo : photos/{joueur_sel.replace(' ', '_').replace('.', '')}.jpg
                </div>
            """, unsafe_allow_html=True)
    with c_info:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Poste", agg["poste"] or "-")
        c2.metric("N°", int(agg["numero"]) if pd.notna(agg["numero"]) else "-")
        c3.metric("Matchs", int(agg["matchs"]))
        c4.metric("Minutes jouées", f"{agg_brut['temps_jeu_min']:.1f}")

    st.markdown("---")
    c_off, c_def, c_disc = st.columns(3)
    with c_off:
        st.markdown("##### Contribution offensive")
        st.metric("Buts", fmt(agg["buts"], mode))
        st.metric("Passes décisives", fmt(agg["passes_decisives"], mode))
        st.metric("Tirs", fmt(agg["tirs_total"], mode))
        st.metric("Tirs cadrés", fmt(agg["tirs_cadres"], mode))
        if agg_brut["tirs_total"] > 0:
            st.metric("% tirs cadrés", fmt_pct(agg_brut["tirs_cadres"] / agg_brut["tirs_total"]))
    with c_def:
        st.markdown("##### Contribution défensive")
        st.metric("Interceptions", fmt(agg["interceptions"], mode))
        st.metric("Récupérations", fmt(agg["recuperations"], mode))
        st.metric("Duels OFF gagnés", fmt(agg["duels_off_gagnes"], mode))
        st.metric("Duels DEF gagnés", fmt(agg["duels_def_gagnes"], mode))
    with c_disc:
        st.markdown("##### Pertes & discipline")
        st.metric("Pertes de balle", fmt(agg["pertes_de_balles"], mode))
        st.metric("Passes loupées", fmt(agg["passes_loupees"], mode))
        st.metric("Fautes commises", fmt(agg["fautes_commises"], mode))
        st.metric("Fautes subies", fmt(agg["fautes_subies"], mode))

    st.markdown("---")
    st.subheader("Joueur vs Moyenne équipe")

    # Choix du mode pour la comparaison (indépendant du mode global)
    mode_comp = st.radio(
        "Mode de comparaison",
        ["Stats brutes", "Par minute", "Per 40 min"],
        horizontal=True, key="mode_comp_fj"
    )

    perfs_all_mode = appliquer_mode(get_perfs(), mode_comp)
    perfs_all_mode = perfs_all_mode[perfs_all_mode["role"] != "Gardien"]
    agg_all_mode = agreger_joueur(perfs_all_mode, mode_comp)
    moy_equipe = agg_all_mode.mean(numeric_only=True)

    df_j_mode = appliquer_mode(df_j_brut, mode_comp)
    if match_id_filtre is None:
        agg_j_mode = agreger_joueur(df_j_mode, mode_comp).iloc[0]
    else:
        agg_j_mode = df_j_mode.iloc[0]

    indicateurs_comp = [
        ("Buts", "buts"),
        ("Passes D.", "passes_decisives"),
        ("Tirs", "tirs_total"),
        ("Tirs cadrés", "tirs_cadres"),
        ("Interceptions", "interceptions"),
        ("Récupérations", "recuperations"),
        ("D.OFF gagnés", "duels_off_gagnes"),
        ("D.DEF gagnés", "duels_def_gagnes"),
        ("Pertes", "pertes_de_balles"),
    ]
    labels = [lbl for lbl, _ in indicateurs_comp]
    val_j = [agg_j_mode[col] if pd.notna(agg_j_mode[col]) else 0 for _, col in indicateurs_comp]
    val_m = [moy_equipe[col] if pd.notna(moy_equipe.get(col)) else 0 for _, col in indicateurs_comp]

    col_bar, col_rad = st.columns([1.1, 1])
    with col_bar:
        fig_bar = barres_horizontales_comparaison(
            labels, val_j, val_m, nom_joueur=joueur_sel, nom_ref="Moy. Équipe"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_rad:
        st.markdown("**Radar profil (échelle normalisée par axe)**")
        fig_rad = radar_normalise(val_j, val_m, labels,
                                  nom_joueur=joueur_sel, nom_ref="Moy. équipe")
        st.plotly_chart(fig_rad, use_container_width=True)

    if match_id_filtre is None and len(df_j_brut) > 1:
        st.markdown("---")
        st.subheader("Détail match par match")
        detail = df_j_brut[["match_code", "adversaire", "temps_jeu_min",
                            "buts", "passes_decisives", "tirs_total", "tirs_cadres",
                            "interceptions", "recuperations", "pertes_de_balles"]].copy()
        detail.columns = ["Match", "Adversaire", "Min", "B", "PD", "Tirs", "T.cad",
                          "Inter.", "Récup.", "Pertes"]
        st.dataframe(detail, hide_index=True, use_container_width=True)

    # === BOUTON EXPORT PDF ===
    st.markdown("---")
    st.subheader("Exporter")
    if st.button("📄 Générer un PDF de cette fiche", type="primary"):
        # Préparer les notes du joueur
        coefs = get_coefficients()
        params = get_parametres()
        matchs_idx = matchs.set_index("match_id")
        notes_j = []
        for _, p in df_j_brut.iterrows():
            m_row = matchs_idx.loc[p["match_id"]]
            n = calculer_note_match(p, m_row, coefs, params)
            notes_j.append({
                "match": m_row["libelle"], **n
            })

        # Agrégats brut et per 40 pour le PDF
        agg_b = agreger_joueur(df_j_brut, "Stats brutes").iloc[0] if match_id_filtre is None else df_j_brut.iloc[0]
        agg_40 = agreger_joueur(appliquer_mode(df_j_brut, "Per 40 min"), "Per 40 min").iloc[0] if match_id_filtre is None else appliquer_mode(df_j_brut, "Per 40 min").iloc[0]
        if "matchs" not in agg_b:
            agg_b = pd.concat([agg_b, pd.Series({"matchs": 1})])
        if "matchs" not in agg_40:
            agg_40 = pd.concat([agg_40, pd.Series({"matchs": 1})])

        pdf_buf = pdf_fiche_joueur(joueur_sel, agg_b, agg_40, df_j_brut, notes_j, equipe["nom"])
        nom_fichier = f"fiche_{joueur_sel.replace(' ', '_').replace('.', '')}_{date.today().strftime('%Y%m%d')}.pdf"
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=nom_fichier,
            mime="application/pdf"
        )
        st.success("PDF prêt, clique sur 'Télécharger'.")


# ============================================================================
# PAGE — COMPARAISON
# ============================================================================

elif page == "Comparaison":
    st.title("Comparaison de joueurs")
    st.caption(f"Portée : {portee} · Mode : Per 40 min (forcé pour comparabilité)")

    joueurs_dispo = sorted(perfs_raw[perfs_raw["role"] != "Gardien"]["joueur"].unique())
    if len(joueurs_dispo) < 2:
        st.warning("Pas assez de joueurs.")
        st.stop()

    c1, c2 = st.columns(2)
    j1 = c1.selectbox("Joueur 1", joueurs_dispo, index=0)
    j2 = c2.selectbox("Joueur 2", joueurs_dispo,
                      index=1 if joueurs_dispo[1] != j1 else 0)

    if j1 == j2:
        st.info("Sélectionne deux joueurs différents.")
        st.stop()

    df_40 = appliquer_mode(perfs_raw, "Per 40 min")

    def stats_joueur(nom):
        sub = df_40[df_40["joueur"] == nom]
        if match_id_filtre is None:
            return agreger_joueur(sub, "Per 40 min").iloc[0]
        return sub.iloc[0]

    s1 = stats_joueur(j1)
    s2 = stats_joueur(j2)

    indicateurs = [
        ("Buts/40", "buts"), ("PD/40", "passes_decisives"),
        ("Tirs/40", "tirs_total"), ("Tirs cadrés/40", "tirs_cadres"),
        ("Interceptions/40", "interceptions"), ("Récupérations/40", "recuperations"),
        ("D.OFF gagnés/40", "duels_off_gagnes"), ("D.DEF gagnés/40", "duels_def_gagnes"),
        ("Pertes/40", "pertes_de_balles"), ("Fautes commises/40", "fautes_commises"),
    ]
    tab_comp = pd.DataFrame({
        "Indicateur": [lbl for lbl, _ in indicateurs],
        j1: [round(s1[c], 2) if pd.notna(s1[c]) else "-" for _, c in indicateurs],
        j2: [round(s2[c], 2) if pd.notna(s2[c]) else "-" for _, c in indicateurs],
    })

    col_t, col_b = st.columns([1, 1.3])
    with col_t:
        st.subheader("Tableau comparatif")
        st.dataframe(tab_comp, hide_index=True, use_container_width=True)
    with col_b:
        st.subheader("Comparaison par indicateur")
        labels = [lbl for lbl, _ in indicateurs]
        v1 = [s1[c] if pd.notna(s1[c]) else 0 for _, c in indicateurs]
        v2 = [s2[c] if pd.notna(s2[c]) else 0 for _, c in indicateurs]
        fig = barres_horizontales_comparaison(labels, v1, v2, nom_joueur=j1, nom_ref=j2)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Radar comparé (échelle normalisée par axe)")
    radar_s1 = {
        "Buts": s1["buts"] or 0, "Passes D.": s1["passes_decisives"] or 0,
        "Tirs cad.": s1["tirs_cadres"] or 0, "Récup.": s1["recuperations"] or 0,
        "Inter.": s1["interceptions"] or 0,
        "Duels +": (s1["duels_off_gagnes"] or 0) + (s1["duels_def_gagnes"] or 0)
    }
    radar_s2 = {
        "Buts": s2["buts"] or 0, "Passes D.": s2["passes_decisives"] or 0,
        "Tirs cad.": s2["tirs_cadres"] or 0, "Récup.": s2["recuperations"] or 0,
        "Inter.": s2["interceptions"] or 0,
        "Duels +": (s2["duels_off_gagnes"] or 0) + (s2["duels_def_gagnes"] or 0)
    }
    st.plotly_chart(radar_comparaison_2joueurs(radar_s1, radar_s2, j1, j2),
                    use_container_width=True)


# ============================================================================
# PAGE — GARDIENS
# ============================================================================

elif page == "Gardiens":
    st.title("Gardiens")
    st.caption(f"Portée : {portee} · Mode : {mode}")

    gks = perfs_mode[perfs_mode["role"] == "Gardien"].copy()
    gks_brut = perfs_raw[perfs_raw["role"] == "Gardien"].copy()

    if gks.empty:
        st.info("Aucun gardien sur cette portée.")
        st.stop()

    if match_id_filtre is None:
        agg = agreger_joueur(gks, mode)
        agg_brut = agreger_joueur(gks_brut, "Stats brutes")
        agg = agg.merge(agg_brut[["joueur_id", "temps_jeu_min"]].rename(
            columns={"temps_jeu_min": "min_brut"}), on="joueur_id")
    else:
        agg = gks.copy()
        agg["matchs"] = 1
        agg["min_brut"] = gks_brut["temps_jeu_min"].values

    cols_aff = {
        "joueur": "Gardien", "matchs": "M", "min_brut": "Min",
        "buts_encaisses": "BE", "arrets": "Arrêts",
        "relances_reussies_total": "Rel.+", "relances_loupees_total": "Rel.-"
    }
    agg_disp = agg[[c for c in cols_aff if c in agg.columns]].copy()
    agg_disp.columns = [cols_aff[c] for c in agg_disp.columns]

    for c in agg_disp.columns:
        if c not in ["Gardien"]:
            if mode == "Stats brutes" or c in ["M", "Min"]:
                agg_disp[c] = agg_disp[c].apply(lambda v: int(round(v)) if pd.notna(v) else "-")
            else:
                agg_disp[c] = agg_disp[c].apply(lambda v: round(v, 2) if pd.notna(v) else "-")

    st.subheader("Synthèse gardiens")
    st.dataframe(agg_disp, hide_index=True, use_container_width=True)

    if match_id_filtre is None and len(gks_brut) > 0:
        st.markdown("---")
        st.subheader("Détail match par match (stats brutes)")
        detail = gks_brut[["joueur", "match_code", "adversaire", "temps_jeu_min",
                           "buts_encaisses", "arrets",
                           "relances_reussies_total", "relances_loupees_total",
                           "relances_reussite_pct"]].copy()
        detail["relances_reussite_pct"] = detail["relances_reussite_pct"].apply(
            lambda v: f"{v*100:.0f}%" if pd.notna(v) else "-")
        detail.columns = ["Gardien", "Match", "Adv.", "Min", "BE", "Arrêts",
                          "Relances+", "Relances-", "% Rel."]
        st.dataframe(detail, hide_index=True, use_container_width=True)


# ============================================================================
# PAGE — ÉVOLUTION
# ============================================================================

elif page == "Évolution":
    st.title("Évolution sur la saison")
    st.caption("Suivi des performances match par match")

    tab1, tab2 = st.tabs(["Équipe", "Joueur"])

    INDICATEURS_EVOL = {
        "Buts": "buts", "Passes décisives": "passes_decisives",
        "Tirs total": "tirs_total", "Tirs cadrés": "tirs_cadres",
        "Interceptions": "interceptions", "Récupérations": "recuperations",
        "Pertes de balles": "pertes_de_balles",
        "Duels OFF gagnés": "duels_off_gagnes", "Duels DEF gagnés": "duels_def_gagnes",
        "Fautes commises": "fautes_commises", "Fautes subies": "fautes_subies",
        "Arrêts (gardien)": "arrets",
    }

    with tab1:
        st.subheader("Bilan équipe match par match")
        st.plotly_chart(graphe_evolution_equipe(matchs), use_container_width=True)

        st.markdown("---")
        st.subheader("Stats équipe par match")
        perfs_all = get_perfs()
        ind_choisi = st.selectbox("Indicateur à afficher", list(INDICATEURS_EVOL.keys()))
        col_choisie = INDICATEURS_EVOL[ind_choisi]

        if col_choisie == "arrets":
            perfs_pour_calcul = perfs_all
        else:
            perfs_pour_calcul = perfs_all[perfs_all["role"] != "Gardien"]

        stats_par_match = perfs_pour_calcul.groupby("match_id").agg(
            valeur=(col_choisie, "sum")
        ).reset_index()
        stats_par_match = stats_par_match.merge(
            matchs[["match_id", "libelle"]], on="match_id"
        ).sort_values("match_id")

        fig = go.Figure(go.Bar(
            x=stats_par_match["libelle"], y=stats_par_match["valeur"],
            marker=dict(color=COULEUR_BLEU),
            text=stats_par_match["valeur"].astype(int),
            textposition="outside", textfont=dict(size=12)
        ))
        fig.update_layout(
            title=f"{ind_choisi} — match par match",
            height=350, margin=dict(l=10, r=10, t=50, b=20),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Évolution d'un joueur")
        joueurs_dispo = sorted(get_perfs()["joueur"].unique())
        joueur_sel = st.selectbox("Joueur", joueurs_dispo, key="evol_joueur")
        df_joueur = get_perfs()
        df_joueur = df_joueur[df_joueur["joueur"] == joueur_sel].sort_values("match_id")

        if df_joueur.empty:
            st.info("Aucune donnée pour ce joueur.")
        else:
            cev1, cev2, cev3 = st.columns(3)
            with cev1:
                st.plotly_chart(graphe_evolution_joueur(
                    df_joueur, "buts", "Buts par match", COULEUR_PRIMAIRE),
                    use_container_width=True)
            with cev2:
                st.plotly_chart(graphe_evolution_joueur(
                    df_joueur, "passes_decisives", "Passes décisives", COULEUR_BLEU),
                    use_container_width=True)
            with cev3:
                st.plotly_chart(graphe_evolution_joueur(
                    df_joueur, "temps_jeu_min", "Minutes jouées", COULEUR_VERT),
                    use_container_width=True)

            st.markdown("---")
            st.subheader("Autre indicateur à suivre")
            ind_j = st.selectbox("Indicateur", list(INDICATEURS_EVOL.keys()), key="evol_ind_j")
            st.plotly_chart(graphe_evolution_joueur(
                df_joueur, INDICATEURS_EVOL[ind_j], ind_j, COULEUR_AMBRE),
                use_container_width=True)


# ============================================================================
# PAGE — NOTATION
# ============================================================================

elif page == "Notation":
    st.title("Notation des joueurs")
    st.caption("Note Brute calculée pour chaque joueur dans chaque match")

    coefs = get_coefficients()
    params = get_parametres()
    perfs_all = get_perfs()
    matchs_idx = matchs.set_index("match_id")

    notes = []
    for _, p in perfs_all.iterrows():
        m_row = matchs_idx.loc[p["match_id"]]
        n = calculer_note_match(p, m_row, coefs, params)
        notes.append({
            "match_id": p["match_id"], "match": m_row["libelle"],
            "joueur": p["joueur"], "poste": p["poste"], "role": p["role"],
            "min": round(p["temps_jeu_min"], 1),
            **n
        })
    df_notes = pd.DataFrame(notes)

    tab1, tab2 = st.tabs(["Vue détaillée", "Classement cumulé"])

    with tab1:
        match_sel = st.selectbox("Match", ["Tous"] + matchs["libelle"].tolist(), key="notation_match")
        if match_sel == "Tous":
            df_aff = df_notes.copy()
        else:
            df_aff = df_notes[df_notes["match"] == match_sel].copy()

        df_aff = df_aff.sort_values("note", ascending=False)
        df_aff_disp = df_aff[["joueur", "poste", "match", "min", "delta_off",
                              "delta_def", "delta_neg", "delta_gk", "bonus",
                              "brute", "note"]].copy()
        df_aff_disp.columns = ["Joueur", "Poste", "Match", "Min", "Δ OFF",
                               "Δ DEF", "Δ NEG", "Δ GK", "Bonus",
                               "Brute", "Note /20"]
        st.dataframe(df_aff_disp, hide_index=True, use_container_width=True)

        st.caption("**Brute** = 10 + Δ OFF + Δ DEF + Δ NEG + Δ GK + Bonus. **Note /20** = Brute bornée entre 0 et 20.")

        # === BOUTON EXPORT PDF ===
        if match_sel != "Tous":
            st.markdown("---")
            if st.button("📄 Exporter ce match en PDF", type="primary"):
                notes_match = df_notes[df_notes["match"] == match_sel].to_dict("records")
                pdf_buf = pdf_notation_match(match_sel, notes_match, equipe["nom"])
                nom_fichier = f"notation_{match_sel.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf"
                st.download_button(
                    label="⬇ Télécharger le PDF",
                    data=pdf_buf,
                    file_name=nom_fichier,
                    mime="application/pdf"
                )

    with tab2:
        st.subheader("Classement cumulé (moyenne des notes)")
        classement = df_notes.groupby("joueur").agg(
            matchs=("match_id", "nunique"),
            note_moy=("note", "mean"),
            note_min=("note", "min"),
            note_max=("note", "max"),
            min_total=("min", "sum")
        ).reset_index().sort_values("note_moy", ascending=False)

        classement_disp = classement.copy()
        classement_disp["note_moy"] = classement_disp["note_moy"].round(2)
        classement_disp["note_min"] = classement_disp["note_min"].round(2)
        classement_disp["note_max"] = classement_disp["note_max"].round(2)
        classement_disp["min_total"] = classement_disp["min_total"].round(1)
        classement_disp.columns = ["Joueur", "Matchs", "Note moy.", "Note min", "Note max", "Min joués"]
        st.dataframe(classement_disp, hide_index=True, use_container_width=True)

        top10 = classement.head(10)
        fig = go.Figure(go.Bar(
            x=top10["note_moy"], y=top10["joueur"], orientation='h',
            marker=dict(color=COULEUR_PRIMAIRE),
            text=top10["note_moy"].round(2), textposition="outside"
        ))
        fig.update_layout(
            title="Top 10 — note moyenne",
            height=400, margin=dict(l=10, r=40, t=50, b=20),
            xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)", range=[0, 22]),
            yaxis=dict(autorange="reversed", automargin=True),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# PAGE — SAISIE
# ============================================================================

elif page == "Saisie":
    st.title("Saisie d'un nouveau match")
    st.caption("Remplis les infos du match puis les stats de chaque joueur. Tout est enregistré dans futsal.db")

    # --- Étape 1 : infos du match ---
    st.markdown("### 1. Informations du match")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        adversaire_in = st.text_input("Adversaire", placeholder="Ex: Espagne")
        date_in = st.date_input("Date du match", value=date.today())
    with col_m2:
        score_pour_in = st.number_input("Buts France", min_value=0, max_value=50, value=0, step=1)
        score_contre_in = st.number_input("Buts adverse", min_value=0, max_value=50, value=0, step=1)
    with col_m3:
        lieu_in = st.text_input("Lieu", placeholder="Ex: France")
        competition_in = st.text_input("Compétition", placeholder="Ex: Amical")

    # Calculer le match_no auto et le code
    adversaire_norm = adversaire_in.strip().capitalize() if adversaire_in else ""
    code_match = ""
    match_no_auto = 1
    if adversaire_norm:
        existants = matchs[matchs["adversaire"] == adversaire_norm]
        match_no_auto = len(existants) + 1
        code_match = f"FRA_{adversaire_norm.upper()}_M{match_no_auto}"
        st.caption(f"Code généré : **{code_match}** (match n°{match_no_auto} contre {adversaire_norm})")

    st.markdown("---")
    st.markdown("### 2. Stats des joueurs")
    st.caption("Coche chaque joueur ayant participé, et remplis ses stats. Tu peux laisser à zéro ce qui ne s'applique pas.")

    # Récupérer la liste des joueurs
    joueurs_liste = get_joueurs_liste()

    if joueurs_liste.empty:
        st.warning("Aucun joueur en base. Ajoute des joueurs d'abord.")
        st.stop()

    # Stocker les saisies en session_state
    if "saisie_perfs" not in st.session_state:
        st.session_state.saisie_perfs = {}

    # Pour chaque joueur, un expander
    for _, j in joueurs_liste.iterrows():
        jid = int(j["joueur_id"])
        nom = j["nom"]
        with st.expander(f"{nom} · {j['poste'] or '-'} · N°{int(j['numero']) if pd.notna(j['numero']) else '-'}"):
            participe = st.checkbox(f"A participé", key=f"part_{jid}",
                                     value=(jid in st.session_state.saisie_perfs))

            if participe:
                role = "Gardien" if (j["poste"] or "").lower() == "gardien" else "Joueur"
                role_sel = st.radio("Rôle", ["Joueur", "Gardien"],
                                    index=1 if role == "Gardien" else 0,
                                    horizontal=True, key=f"role_{jid}")

                cs1, cs2, cs3 = st.columns(3)
                with cs1:
                    temps = st.number_input("Minutes jouées", min_value=0.0, max_value=60.0,
                                            value=0.0, step=0.5, key=f"temps_{jid}")
                with cs2:
                    numero = st.number_input("N° (ce match)", min_value=1, max_value=99,
                                              value=int(j["numero"]) if pd.notna(j["numero"]) else 1,
                                              step=1, key=f"num_{jid}")
                with cs3:
                    poste = st.text_input("Poste (ce match)",
                                           value=j["poste"] or "", key=f"poste_{jid}")

                if role_sel == "Joueur":
                    st.markdown("**Offensif**")
                    co1, co2, co3, co4 = st.columns(4)
                    buts = co1.number_input("Buts", 0, 20, 0, key=f"b_{jid}")
                    pd_ = co2.number_input("Passes décisives", 0, 20, 0, key=f"pd_{jid}")
                    tirs_cad = co3.number_input("Tirs cadrés", 0, 30, 0, key=f"tc_{jid}")
                    tirs_hc = co4.number_input("Tirs hors cadre", 0, 30, 0, key=f"thc_{jid}")
                    co5, co6, co7, _ = st.columns(4)
                    tirs_ctr = co5.number_input("Tirs contrés", 0, 30, 0, key=f"tctr_{jid}")
                    poteau = co6.number_input("Poteau/barre", 0, 10, 0, key=f"pot_{jid}")
                    tirs_total = tirs_cad + tirs_hc + tirs_ctr
                    co7.metric("Tirs total (auto)", tirs_total)

                    st.markdown("**Défensif**")
                    cd1, cd2, cd3, cd4 = st.columns(4)
                    inter = cd1.number_input("Interceptions", 0, 50, 0, key=f"int_{jid}")
                    recup = cd2.number_input("Récupérations", 0, 50, 0, key=f"rec_{jid}")
                    duels_off_g = cd3.number_input("Duels OFF gagnés", 0, 30, 0, key=f"dofg_{jid}")
                    duels_off_t = cd4.number_input("Duels OFF tentés", 0, 30, 0, key=f"doft_{jid}")
                    cd5, cd6, _, _ = st.columns(4)
                    duels_def_g = cd5.number_input("Duels DEF gagnés", 0, 30, 0, key=f"ddfg_{jid}")
                    duels_def_t = cd6.number_input("Duels DEF tentés", 0, 30, 0, key=f"ddft_{jid}")

                    st.markdown("**Pertes / discipline**")
                    cp1, cp2, cp3, cp4 = st.columns(4)
                    pertes = cp1.number_input("Pertes de balle", 0, 50, 0, key=f"pertes_{jid}")
                    passes_loup = cp2.number_input("Passes loupées", 0, 50, 0, key=f"pl_{jid}")
                    ballons_rendus = cp3.number_input("Ballons rendus", 0, 50, 0, key=f"br_{jid}")
                    erreurs = cp4.number_input("Erreurs techniques", 0, 30, 0, key=f"err_{jid}")
                    cp5, cp6, cp7, cp8 = st.columns(4)
                    int_adv = cp5.number_input("Inter. subies", 0, 50, 0, key=f"iadv_{jid}")
                    recup_adv = cp6.number_input("Récup. subies", 0, 50, 0, key=f"radv_{jid}")
                    duels_perdus = cp7.number_input("Duels perdus", 0, 30, 0, key=f"dp_{jid}")
                    cp9, cp10, _, _ = st.columns(4)
                    fautes_c = cp9.number_input("Fautes commises", 0, 30, 0, key=f"fc_{jid}")
                    fautes_s = cp10.number_input("Fautes subies", 0, 30, 0, key=f"fs_{jid}")

                    st.session_state.saisie_perfs[jid] = {
                        "joueur_id": jid, "nom": nom, "role": role_sel,
                        "numero_match": numero, "poste_match": poste, "temps_jeu_min": temps,
                        "buts": buts, "passes_decisives": pd_,
                        "tirs_total": tirs_total, "tirs_cadres": tirs_cad,
                        "tirs_hors_cadre": tirs_hc, "tirs_contres": tirs_ctr, "poteau_barre": poteau,
                        "pertes_de_balles": pertes, "passes_loupees": passes_loup,
                        "ballons_rendus": ballons_rendus, "interceptions_adv": int_adv,
                        "duels_perdus": duels_perdus, "erreurs_techniques": erreurs,
                        "recuperations_adv": recup_adv,
                        "duels_off_gagnes": duels_off_g, "duels_off_tentes": duels_off_t,
                        "duels_def_gagnes": duels_def_g, "duels_def_tentes": duels_def_t,
                        "fautes_commises": fautes_c, "fautes_subies": fautes_s,
                        "interceptions": inter, "recuperations": recup,
                    }
                else:
                    # Gardien
                    st.markdown("**Gardien**")
                    cg1, cg2, cg3 = st.columns(3)
                    arrets = cg1.number_input("Arrêts", 0, 50, 0, key=f"arr_{jid}")
                    be = cg2.number_input("Buts encaissés", 0, 30, 0, key=f"be_{jid}")
                    cg4, cg5, cg6, cg7 = st.columns(4)
                    rel_fr = cg4.number_input("Relances faciles ✓", 0, 100, 0, key=f"rfr_{jid}")
                    rel_fl = cg5.number_input("Relances faciles ✗", 0, 100, 0, key=f"rfl_{jid}")
                    rel_dr = cg6.number_input("Relances diff. ✓", 0, 100, 0, key=f"rdr_{jid}")
                    rel_dl = cg7.number_input("Relances diff. ✗", 0, 100, 0, key=f"rdl_{jid}")

                    st.session_state.saisie_perfs[jid] = {
                        "joueur_id": jid, "nom": nom, "role": "Gardien",
                        "numero_match": numero, "poste_match": poste, "temps_jeu_min": temps,
                        "arrets": arrets, "buts_encaisses": be,
                        "relances_faciles_reussies": rel_fr, "relances_faciles_loupees": rel_fl,
                        "relances_difficiles_reussies": rel_dr, "relances_difficiles_loupees": rel_dl,
                    }
            else:
                # Joueur décoché : retirer de la sélection
                if jid in st.session_state.saisie_perfs:
                    del st.session_state.saisie_perfs[jid]

    st.markdown("---")
    st.markdown("### 3. Enregistrer le match")
    st.caption(f"**{len(st.session_state.saisie_perfs)} joueurs sélectionnés**")

    if st.button("💾 Enregistrer ce match dans la base", type="primary"):
        # Validations
        if not adversaire_in.strip():
            st.error("Renseigne le nom de l'adversaire.")
        elif len(st.session_state.saisie_perfs) == 0:
            st.error("Au moins un joueur doit être sélectionné.")
        else:
            # Insérer le match
            equipe_id = int(equipe["equipe_id"])
            try:
                match_id_new = executer("""
                    INSERT INTO match (equipe_id, code, adversaire, match_no, date_match,
                                       competition, lieu, score_pour, score_contre, duree_min)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (equipe_id, code_match, adversaire_norm, match_no_auto,
                      date_in.isoformat(), competition_in, lieu_in,
                      int(score_pour_in), int(score_contre_in), 40))

                # Insérer les performances
                for jid, perf in st.session_state.saisie_perfs.items():
                    # Colonnes communes
                    cols = ["match_id", "joueur_id", "numero_match", "poste_match", "role",
                            "temps_jeu_min"]
                    vals = [match_id_new, perf["joueur_id"], perf["numero_match"],
                            perf["poste_match"], perf["role"], perf["temps_jeu_min"]]

                    # Ajouter toutes les stats présentes
                    for k, v in perf.items():
                        if k in ["joueur_id", "nom", "role", "numero_match", "poste_match",
                                 "temps_jeu_min"]:
                            continue
                        cols.append(k)
                        vals.append(v)

                    placeholders = ",".join(["?"] * len(cols))
                    executer(
                        f"INSERT INTO performance ({','.join(cols)}) VALUES ({placeholders})",
                        vals
                    )

                st.success(f"✓ Match enregistré ! ({len(st.session_state.saisie_perfs)} joueurs)")
                st.balloons()
                # Reset
                st.session_state.saisie_perfs = {}
                # Vider le cache pour voir le nouveau match
                st.cache_data.clear()
                st.caption("Recharge la page (touche **R**) pour voir le match dans les autres pages.")
            except Exception as e:
                st.error(f"Erreur lors de l'enregistrement : {e}")


# ============================================================================
# PAGE — LÉGENDE
# ============================================================================

elif page == "Légende":
    st.title("Légende et explications")
    st.caption("Tout pour bien lire le tableau de bord")

    st.markdown("---")
    st.markdown("### Abréviations utilisées")

    legendes = [
        ("**B**", "Buts marqués"), ("**PD**", "Passes décisives"),
        ("**B + PD**", "Contribution offensive totale"),
        ("**Tirs**", "Tirs tentés (cadrés + hors cadre + contrés)"),
        ("**T.cad**", "Tirs cadrés"), ("**% T.cad**", "Pourcentage de tirs cadrés"),
        ("**Inter.**", "Interceptions"), ("**Récup.**", "Récupérations de balle"),
        ("**Pertes**", "Pertes de balle"),
        ("**D.OFF+**", "Duels offensifs gagnés"), ("**D.DEF+**", "Duels défensifs gagnés"),
        ("**M**", "Nombre de matchs joués"), ("**Min**", "Minutes jouées"),
    ]
    legendes_gk = [
        ("**BE**", "Buts encaissés"), ("**Arrêts**", "Arrêts effectués"),
        ("**Rel.+**", "Relances réussies (faciles + difficiles)"),
        ("**Rel.-**", "Relances loupées (faciles + difficiles)"),
        ("**% Rel.**", "Pourcentage de relances réussies"),
    ]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Joueurs de champ")
        for abrev, defi in legendes:
            st.markdown(f"{abrev} — {defi}")
    with col2:
        st.markdown("#### Gardiens")
        for abrev, defi in legendes_gk:
            st.markdown(f"{abrev} — {defi}")

    st.markdown("---")
    st.markdown("### Modes d'affichage")
    st.markdown("""
    - **Stats brutes** : valeurs telles quelles
    - **Par minute** : stat / minutes jouées
    - **Per 40 min** : extrapolation sur un match complet (40 min en futsal). Mode de référence pour comparer des joueurs.
    """)

    st.markdown("---")
    st.markdown("### Système de notation")
    st.markdown("""
    > **Brute = 10 + Δ OFF + Δ DEF + Δ NEG + Δ GK + Bonus résultat**

    La **Note /20** est la Brute bornée entre 0 et 20.

    - Les **Δ** sont la somme des actions de chaque famille pondérées par les coefficients ci-dessous
    - Le **Bonus résultat** est fixe : **+3 victoire, +1.5 nul, 0 défaite** (indépendant du temps de jeu)
    - Δ GK n'est calculé que pour les gardiens
    """)

    params = get_parametres()
    coefs_df = charger("SELECT famille, libelle, action, coef FROM coefficient ORDER BY famille, coef DESC")

    st.markdown("---")
    st.markdown("### Paramètres globaux")
    cp1, cp2, cp3, cp4 = st.columns(4)
    cp1.metric("Note de départ", f"{params['note_depart']}")
    cp2.metric("Bonus victoire", f"+{params['bonus_victoire']}")
    cp3.metric("Bonus nul", f"+{params['bonus_nul']}")
    cp4.metric("Bonus défaite", f"{params['bonus_defaite']}")

    st.markdown("---")
    st.markdown("### Grille des coefficients")

    col_off, col_def = st.columns(2)
    col_neg, col_gk = st.columns(2)

    def afficher_famille(col, famille_nom, couleur):
        with col:
            st.markdown(f"##### <span style='color:{couleur}'>{famille_nom}</span>", unsafe_allow_html=True)
            sub = coefs_df[coefs_df["famille"] == famille_nom][["libelle", "coef"]].copy()
            sub.columns = ["Action", "Coefficient"]
            sub["Coefficient"] = sub["Coefficient"].apply(
                lambda v: f"+{v}" if v > 0 else f"{v}"
            )
            st.dataframe(sub, hide_index=True, use_container_width=True)

    afficher_famille(col_off, "OFFENSIF", COULEUR_PRIMAIRE)
    afficher_famille(col_def, "DEFENSIF", COULEUR_BLEU)
    afficher_famille(col_neg, "NEGATIF", COULEUR_GRIS)
    afficher_famille(col_gk, "GARDIEN", COULEUR_VERT)
