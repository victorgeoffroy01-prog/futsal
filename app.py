"""
================================================================================
TABLEAU DE BORD FUTSAL — EDF U19   (v6)
================================================================================
Nouveautés v6 :
- Suppression de la page Saisie
- Fiche joueur : "Tirs cadrés" -> "Tirs cadrés (%)" avec format "1 (25%)"
- Heatmap équipe (page Vue équipe) avec sélecteur d'indicateurs
- Page Match dédiée (compo + score + top 3 par critère)
- Page Tendance forme (indicateur au choix + fenêtre 3/5/tous)
- Page Calendrier (liste verticale, onglets À venir/Joués)
- Fiche joueur : section comparaison entre 2 matchs du même joueur
================================================================================
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
from pathlib import Path
from datetime import date, datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ============================================================================
# CONFIG
# ============================================================================

DB_PATH = "futsal.db"
PHOTOS_DIR = Path("photos")
LOGO_PATH = Path("logo_fff.webp")

COULEUR_PRIMAIRE = "#FF4B4B"
COULEUR_BLEU     = "#185FA5"
COULEUR_VERT     = "#1D9E75"
COULEUR_AMBRE    = "#EF9F27"
COULEUR_GRIS     = "#888888"
COULEUR_MOY      = "#EF9F27"

st.set_page_config(
    page_title="EDF U19 Futsal", page_icon="⚽",
    layout="wide", initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; }
    h1 { font-size: 2rem !important; }
</style>
""", unsafe_allow_html=True)


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


@st.cache_data(ttl=30)
def charger(query, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    if "joueur" in df.columns:
        df["joueur"] = df["joueur"].apply(normaliser_nom)
    return df


def get_equipe():
    return charger("SELECT * FROM equipe LIMIT 1").iloc[0]


def get_matchs():
    return charger("""
        SELECT match_id, code, adversaire, match_no, lieu, date_match, competition,
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
    if mode == "Par minute":
        return f"{v:.3f}"
    return f"{v:.2f}"


def fmt_pct(v):
    if v is None or pd.isna(v):
        return "-"
    return f"{v*100:.0f}%"


def calculer_note_match(perf_row, match_row, coefs, params):
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


def calculer_toutes_notes():
    """Calcule la note de toutes les perfs et retourne un DataFrame."""
    coefs = get_coefficients()
    params = get_parametres()
    perfs = get_perfs()
    matchs_idx = get_matchs().set_index("match_id")
    notes = []
    for _, p in perfs.iterrows():
        m_row = matchs_idx.loc[p["match_id"]]
        n = calculer_note_match(p, m_row, coefs, params)
        notes.append({
            "match_id": p["match_id"], "match": m_row["libelle"],
            "joueur_id": p["joueur_id"], "joueur": p["joueur"],
            "poste": p["poste"], "role": p["role"],
            "min": round(p["temps_jeu_min"], 1), **n
        })
    return pd.DataFrame(notes)


# ============================================================================
# COMPOSANTS VISUELS (existants + nouveaux)
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
                                     nom_joueur="Joueur", nom_ref="Moy. Équipe",
                                     couleur_joueur=COULEUR_BLEU, couleur_ref=COULEUR_MOY,
                                     decimales=1):
    """Barres horizontales doubles. Affiche TOUJOURS la valeur (y compris 0)."""
    def fmt_val(v):
        if v is None or pd.isna(v):
            return "-"
        # Toujours retourner une string, même pour 0
        if isinstance(v, (int, float)):
            if v == int(v):
                return f"{int(v)}"
            return f"{v:.{decimales}f}"
        return str(v)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=val_moyenne, orientation='h', name=nom_ref,
        marker=dict(color=couleur_ref),
        text=[fmt_val(v) for v in val_moyenne],
        textposition="outside", textfont=dict(size=11),
        cliponaxis=False
    ))
    fig.add_trace(go.Bar(
        y=labels, x=val_joueur, orientation='h', name=nom_joueur,
        marker=dict(color=couleur_joueur),
        text=[fmt_val(v) for v in val_joueur],
        textposition="outside", textfont=dict(size=11),
        cliponaxis=False
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
                    nom_ref="Moy. équipe",
                    couleur_joueur=COULEUR_BLEU, couleur_ref=COULEUR_MOY):
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
        r=v_r_norm + [v_r_norm[0]], theta=labels_enrichis + [labels_enrichis[0]],
        fill='toself', name=nom_ref,
        line=dict(color=couleur_ref, width=2.5),
        fillcolor=couleur_ref, opacity=0.35, marker=dict(size=7)
    ))
    fig.add_trace(go.Scatterpolar(
        r=v_j_norm + [v_j_norm[0]], theta=labels_enrichis + [labels_enrichis[0]],
        fill='toself', name=nom_joueur,
        line=dict(color=couleur_joueur, width=2.5),
        fillcolor=couleur_joueur, opacity=0.45, marker=dict(size=7)
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


def radar_comparaison_2joueurs(stats1, stats2, nom1, nom2,
                                couleur1=COULEUR_PRIMAIRE, couleur2=COULEUR_BLEU):
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
        name=nom1, line=dict(color=couleur1, width=2.5),
        fillcolor=couleur1, opacity=0.4, marker=dict(size=7)
    ))
    fig.add_trace(go.Scatterpolar(
        r=v2n + [v2n[0]], theta=labels_enrichis + [labels_enrichis[0]], fill='toself',
        name=nom2, line=dict(color=couleur2, width=2.5),
        fillcolor=couleur2, opacity=0.4, marker=dict(size=7)
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


def heatmap_equipe(df, indicateurs_cols, labels_lignes_col="joueur"):
    """Heatmap : joueurs en lignes, indicateurs en colonnes, dégradé de couleur par colonne."""
    if df.empty or not indicateurs_cols:
        st.info("Aucune donnée à afficher.")
        return

    libelles_cols = list(indicateurs_cols.values())
    cols = list(indicateurs_cols.keys())

    df_h = df.copy()
    z = df_h[cols].fillna(0).values
    y = df_h[labels_lignes_col].tolist()

    # Normalisation par colonne (chaque indicateur sur son échelle, sinon les grandes valeurs écrasent)
    z_norm = z.copy().astype(float)
    for j in range(z_norm.shape[1]):
        col = z_norm[:, j]
        m, M = col.min(), col.max()
        if M - m > 1e-9:
            z_norm[:, j] = (col - m) / (M - m)
        else:
            z_norm[:, j] = 0.5

    # Texte affiché : valeur réelle
    text = [[f"{int(v)}" if v == int(v) else f"{v:.2f}" for v in row] for row in z]

    fig = go.Figure(data=go.Heatmap(
        z=z_norm, x=libelles_cols, y=y,
        text=text, texttemplate="%{text}",
        colorscale=[[0, "#1F2A3A"], [0.5, "#3D6299"], [1, "#FF4B4B"]],
        showscale=False,
        hovertemplate="<b>%{y}</b><br>%{x}: %{text}<extra></extra>"
    ))
    fig.update_layout(
        height=max(400, 30 * len(y) + 100),
        margin=dict(l=10, r=10, t=10, b=20),
        xaxis=dict(side="top", tickfont=dict(size=11)),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# EXPORT PDF
# ============================================================================

def pdf_fiche_joueur(joueur, agg_brut, agg_min, agg_40, perfs_joueur, notes_joueur, equipe_nom, photo_path=None):
    """PDF fiche joueur avec photo en haut à droite + 3 modes : brut, par minute, per 40 min."""
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

    # En-tête : titre à gauche + photo en haut à droite (table à 2 colonnes)
    from reportlab.platypus import Image as RLImage
    titre_para = []
    titre_para.append(Paragraph(f"<b>{equipe_nom}</b> — Fiche joueur", h1))
    titre_para.append(Paragraph(joueur, ParagraphStyle('j', parent=styles['Heading2'],
                                                       fontSize=22, alignment=TA_LEFT)))
    titre_para.append(Paragraph(
        f"{agg_brut.get('poste','-')} · N°{int(agg_brut['numero']) if pd.notna(agg_brut.get('numero')) else '-'} · "
        f"{int(agg_brut['matchs'])} matchs · {agg_brut['temps_jeu_min']:.1f} min jouées", small))
    titre_para.append(Paragraph(f"<i>Document généré le {date.today().strftime('%d/%m/%Y')}</i>", small))

    # Cellule photo (ou placeholder texte)
    if photo_path:
        try:
            photo_cell = RLImage(photo_path, width=3.2*cm, height=3.2*cm)
        except Exception:
            photo_cell = Paragraph("", small)
    else:
        photo_cell = Paragraph("", small)

    header_table = Table(
        [[titre_para, photo_cell]],
        colWidths=[13*cm, 4*cm]
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.4*cm))

    # Tableau stats : 4 colonnes (Indicateur, Total brut, Par minute, Per 40 min)
    story.append(Paragraph("Statistiques", h2))
    data = [["Indicateur", "Total brut", "Par minute", "Per 40 min"]]
    rows = [
        ("Buts", "buts"), ("Passes décisives", "passes_decisives"),
        ("Tirs total", "tirs_total"), ("Tirs cadrés", "tirs_cadres"),
        ("Interceptions", "interceptions"), ("Récupérations", "recuperations"),
        ("Duels OFF gagnés", "duels_off_gagnes"), ("Duels DEF gagnés", "duels_def_gagnes"),
        ("Pertes de balle", "pertes_de_balles"), ("Fautes commises", "fautes_commises"),
        ("Fautes subies", "fautes_subies"),
    ]
    for lbl, col in rows:
        v_brut = agg_brut.get(col, 0)
        v_min = agg_min.get(col, 0) if agg_min is not None else None
        v_40 = agg_40.get(col, 0)
        data.append([
            lbl,
            f"{int(v_brut)}" if pd.notna(v_brut) else "-",
            f"{v_min:.3f}" if v_min is not None and pd.notna(v_min) else "-",
            f"{v_40:.2f}" if pd.notna(v_40) else "-"
        ])
    t = Table(data, colWidths=[5.5*cm, 3.5*cm, 3.5*cm, 3.5*cm])
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
    if not perfs_joueur.empty and len(perfs_joueur) > 1:
        story.append(Paragraph("Détail match par match", h2))
        det = [["Match", "Min", "B", "PD", "Tirs", "T.cad", "Inter.", "Récup.", "Pertes"]]
        for _, p in perfs_joueur.iterrows():
            det.append([
                p["match_code"], f"{p['temps_jeu_min']:.1f}",
                str(int(p["buts"] or 0)), str(int(p["passes_decisives"] or 0)),
                str(int(p["tirs_total"] or 0)), str(int(p["tirs_cadres"] or 0)),
                str(int(p["interceptions"] or 0)), str(int(p["recuperations"] or 0)),
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
    if notes_joueur:
        story.append(Paragraph("Notation", h2))
        note_data = [["Match", "Δ OFF", "Δ DEF", "Δ NEG", "Bonus", "Brute", "Note /20"]]
        for n in notes_joueur:
            note_data.append([
                n["match"], f"{n['delta_off']:+.2f}", f"{n['delta_def']:+.2f}",
                f"{n['delta_neg']:+.2f}", f"{n['bonus']:+.1f}",
                f"{n['brute']:.2f}", f"{n['note']:.2f}"
            ])
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
    story.append(Paragraph(match_libelle, ParagraphStyle('m', parent=styles['Heading2'], fontSize=18)))
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


def pdf_generique(titre_page, equipe_nom, sections, paysage=False):
    """
    PDF générique pour les pages du site.
    sections : liste de dicts, chacun de type :
      - {"type": "kpi", "label": "Buts", "value": "15"}    -> bloc KPI
      - {"type": "table", "title": "...", "data": [[hdr], [r1], ...], "widths": [...]}
      - {"type": "texte", "title": "...", "content": "..."}
      - {"type": "spacer"}
    """
    buf = BytesIO()
    pagesize = landscape(A4) if paysage else A4
    doc = SimpleDocTemplate(buf, pagesize=pagesize,
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
    normal = styles['Normal']

    story.append(Paragraph(f"<b>{equipe_nom}</b> — {titre_page}", h1))
    story.append(Paragraph(f"<i>Document généré le {date.today().strftime('%d/%m/%Y')}</i>", small))
    story.append(Spacer(1, 0.5*cm))

    # Bloc KPI : regrouper les sections kpi consécutives en une seule ligne
    i = 0
    while i < len(sections):
        s = sections[i]
        if s["type"] == "kpi":
            # Collecter les KPI consécutifs
            kpis = []
            while i < len(sections) and sections[i]["type"] == "kpi":
                kpis.append(sections[i])
                i += 1
            # Construire une table KPI
            data_kpi = [[k["label"] for k in kpis], [str(k["value"]) for k in kpis]]
            w = (pagesize[0] - 3*cm) / len(kpis)
            tk = Table(data_kpi, colWidths=[w] * len(kpis))
            tk.setStyle(TableStyle([
                ('FONTSIZE', (0,0), (-1,0), 9),
                ('FONTSIZE', (0,1), (-1,1), 16),
                ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
                ('TEXTCOLOR', (0,0), (-1,0), colors.grey),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('BOTTOMPADDING', (0,0), (-1,0), 2),
                ('TOPPADDING', (0,1), (-1,1), 2),
            ]))
            story.append(tk)
            story.append(Spacer(1, 0.4*cm))
        elif s["type"] == "table":
            if s.get("title"):
                story.append(Paragraph(s["title"], h2))
            data = s["data"]
            widths = s.get("widths")
            t = Table(data, colWidths=widths)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#185FA5")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
                ('ALIGN', (1,0), (-1,-1), 'CENTER'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
                ('PADDING', (0,0), (-1,-1), 4)
            ]))
            story.append(t)
            story.append(Spacer(1, 0.4*cm))
            i += 1
        elif s["type"] == "texte":
            if s.get("title"):
                story.append(Paragraph(s["title"], h2))
            story.append(Paragraph(s["content"], normal))
            story.append(Spacer(1, 0.3*cm))
            i += 1
        elif s["type"] == "spacer":
            story.append(Spacer(1, 0.5*cm))
            i += 1
        else:
            i += 1

    doc.build(story)
    buf.seek(0)
    return buf


def bouton_pdf(label_bouton, generer_pdf_func, nom_fichier_base, type_btn="secondary"):
    """Helper : crée un bouton 'Générer PDF' qui appelle la fonction de génération
    et affiche le bouton de téléchargement."""
    if st.button(label_bouton, type=type_btn, key=f"pdf_btn_{nom_fichier_base}"):
        pdf_buf = generer_pdf_func()
        nom_fichier = f"{nom_fichier_base}_{date.today().strftime('%Y%m%d')}.pdf"
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=nom_fichier,
            mime="application/pdf",
            key=f"dl_{nom_fichier_base}"
        )




INDICATEURS_LIBELLE = {
    "buts": "Buts",
    "passes_decisives": "Passes décisives",
    "tirs_total": "Tirs total",
    "tirs_cadres": "Tirs cadrés",
    "interceptions": "Interceptions",
    "recuperations": "Récupérations",
    "pertes_de_balles": "Pertes de balles",
    "duels_off_gagnes": "Duels OFF gagnés",
    "duels_def_gagnes": "Duels DEF gagnés",
    "fautes_commises": "Fautes commises",
    "fautes_subies": "Fautes subies",
    "passes_loupees": "Passes loupées",
    "ballons_rendus": "Ballons rendus",
    "arrets": "Arrêts (gardien)",
    "buts_encaisses": "Buts encaissés (gardien)",
}

# Pour la heatmap : on liste les indicateurs pertinents pour joueurs de champ
HEATMAP_DEFAUT = ["buts", "passes_decisives", "tirs_cadres", "interceptions",
                  "recuperations", "pertes_de_balles"]
# ============================================================================
# SIDEBAR
# ============================================================================

equipe = get_equipe()
matchs = get_matchs()

with st.sidebar:
    if LOGO_PATH.exists():
        col_logo1, col_logo2, col_logo3 = st.columns([1, 2, 1])
        with col_logo2:
            st.image(str(LOGO_PATH), width=110)
    st.markdown("### ⚽ EDF U19 Futsal")
    st.caption(f"{equipe['categorie']} · Saison {equipe['saison']}")

    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["Accueil", "Vue équipe", "Match", "Fiche joueur", "Comparaison",
         "Gardiens", "Évolution", "Tendance forme", "Notation",
         "Calendrier", "Légende"],
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

    # ===== EXPORT PDF =====
    st.markdown("---")
    st.subheader("Exporter")
    if st.button("📄 Générer un PDF du bilan saison", type="primary", key="pdf_accueil"):
        bilan = charger("SELECT * FROM v_equipe_bilan").iloc[0]
        agg_all = agreger_joueur(get_perfs(), "Stats brutes")
        agg_all = agg_all[agg_all["role"] != "Gardien"].copy()
        top_buteurs = agg_all.sort_values("buts", ascending=False).head(5)
        top_passeurs = agg_all.sort_values("passes_decisives", ascending=False).head(5)

        sections = [
            {"type": "kpi", "label": "Matchs", "value": int(bilan["matchs"])},
            {"type": "kpi", "label": "Victoires", "value": int(bilan["victoires"])},
            {"type": "kpi", "label": "Nuls", "value": int(bilan["nuls"])},
            {"type": "kpi", "label": "Défaites", "value": int(bilan["defaites"])},
            {"type": "kpi", "label": "Buts pour", "value": int(bilan["buts_pour"])},
            {"type": "kpi", "label": "Buts contre", "value": int(bilan["buts_contre"])},
            {"type": "table", "title": "Résultats",
             "data": [["Match", "Lieu", "Buts pour", "Buts contre", "Résultat"]] +
                     [[m["libelle"], m["lieu"] or "-", str(m["score_pour"]),
                       str(m["score_contre"]), m["resultat"]]
                      for _, m in matchs.iterrows()],
             "widths": [3*cm, 3*cm, 2.5*cm, 2.5*cm, 3*cm]},
            {"type": "table", "title": "Top 5 buteurs",
             "data": [["Joueur", "Poste", "Buts"]] +
                     [[b["joueur"], b["poste"] or "-", str(int(b["buts"]))]
                      for _, b in top_buteurs.iterrows() if b["buts"] > 0],
             "widths": [6*cm, 4*cm, 3*cm]},
            {"type": "table", "title": "Top 5 passeurs",
             "data": [["Joueur", "Poste", "Passes déc."]] +
                     [[p["joueur"], p["poste"] or "-", str(int(p["passes_decisives"]))]
                      for _, p in top_passeurs.iterrows() if p["passes_decisives"] > 0],
             "widths": [6*cm, 4*cm, 3*cm]},
        ]
        pdf_buf = pdf_generique("Bilan de la saison", equipe["nom"], sections)
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=f"bilan_saison_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="dl_accueil"
        )


# ============================================================================
# PAGE — VUE ÉQUIPE (avec heatmap intégrée)
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
                elif mode == "Par minute":
                    df_aff[c] = df_aff[c].apply(lambda v: round(v, 3) if pd.notna(v) else None)
                else:
                    df_aff[c] = df_aff[c].apply(lambda v: round(v, 2) if pd.notna(v) else None)
        st.dataframe(df_aff.sort_values("B", ascending=False), hide_index=True, use_container_width=True)

    # ===== HEATMAP =====
    st.markdown("---")
    st.subheader("🔥 Heatmap équipe")
    st.caption("Vue colorée des stats par joueur. Le dégradé est calculé colonne par colonne (chaque indicateur sur sa propre échelle).")

    # Sélecteur d'indicateurs
    options_heatmap = {INDICATEURS_LIBELLE[c]: c for c in INDICATEURS_LIBELLE
                       if c not in ("arrets", "buts_encaisses")}
    libelles_defaut = [INDICATEURS_LIBELLE[c] for c in HEATMAP_DEFAUT]
    libelles_choisis = st.multiselect(
        "Indicateurs à afficher",
        options=list(options_heatmap.keys()),
        default=libelles_defaut
    )

    if libelles_choisis:
        # Construire le df agrégé sans les gardiens
        df_hmap = agreger_joueur(get_perfs(), mode)
        df_hmap = df_hmap[df_hmap["role"] != "Gardien"].copy()
        # Reverse mapping libelle → col
        indicateurs_cols = {options_heatmap[lib]: lib for lib in libelles_choisis}
        # Garder seulement joueurs ayant joué
        df_hmap = df_hmap[df_hmap["temps_jeu_min"] > 0]
        if not df_hmap.empty:
            heatmap_equipe(df_hmap, indicateurs_cols)
        else:
            st.info("Aucune donnée à afficher pour ces indicateurs.")
    else:
        st.info("Sélectionne au moins un indicateur.")

    # ===== EXPORT PDF =====
    st.markdown("---")
    if st.button("📄 Générer un PDF de la Vue équipe", type="primary", key="pdf_vue_eq"):
        # Tableau résultats
        tab_res = [["Match", "Lieu", "Buts pour", "Buts contre", "Résultat", "Diff"]]
        for _, m in matchs.iterrows():
            tab_res.append([m["libelle"], m["lieu"] or "-",
                            str(m["score_pour"]), str(m["score_contre"]),
                            m["resultat"], f"{m['diff_buts']:+d}"])
        # Top contributeurs
        agg_pdf = agreger_joueur(get_perfs(), "Stats brutes")
        agg_pdf = agg_pdf[agg_pdf["role"] != "Gardien"].copy()
        agg_pdf["b_plus_pd"] = agg_pdf["buts"] + agg_pdf["passes_decisives"]
        top_pdf = agg_pdf[agg_pdf["b_plus_pd"] > 0].sort_values("b_plus_pd", ascending=False).head(10)
        tab_top = [["Joueur", "Poste", "Buts", "PD", "B+PD"]]
        for _, t in top_pdf.iterrows():
            tab_top.append([t["joueur"], t["poste"] or "-",
                            str(int(t["buts"])), str(int(t["passes_decisives"])),
                            str(int(t["b_plus_pd"]))])
        # Tableau stats joueurs (en brut, top 15 par buts)
        df_stats = agg_pdf.sort_values("buts", ascending=False).head(15)
        tab_stats = [["Joueur", "Poste", "M", "Min", "B", "PD", "T.cad", "Inter.", "Récup."]]
        for _, j in df_stats.iterrows():
            tab_stats.append([j["joueur"], j["poste"] or "-",
                              str(int(j["matchs"])), f"{j['temps_jeu_min']:.0f}",
                              str(int(j["buts"])), str(int(j["passes_decisives"])),
                              str(int(j["tirs_cadres"])), str(int(j["interceptions"])),
                              str(int(j["recuperations"]))])

        sections = [
            {"type": "table", "title": "Résultats", "data": tab_res,
             "widths": [3*cm, 3*cm, 2.5*cm, 2.5*cm, 2.5*cm, 1.8*cm]},
            {"type": "table", "title": "Top 10 contributeurs (B + PD)", "data": tab_top,
             "widths": [5*cm, 4*cm, 2*cm, 2*cm, 2*cm]},
            {"type": "table", "title": "Top 15 joueurs (cumul saison)", "data": tab_stats,
             "widths": [4*cm, 3*cm, 1.2*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm]},
        ]
        pdf_buf = pdf_generique("Vue équipe", equipe["nom"], sections, paysage=True)
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=f"vue_equipe_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="dl_vue_eq"
        )


# ============================================================================
# PAGE — MATCH DÉDIÉE
# ============================================================================

elif page == "Match":
    st.title("Fiche match")
    st.caption("Vue détaillée d'un match")

    match_choisi = st.selectbox("Choisir un match", matchs["libelle"].tolist())
    m_id = int(matchs.loc[matchs["libelle"] == match_choisi, "match_id"].iloc[0])
    m_row = matchs.loc[matchs["libelle"] == match_choisi].iloc[0]

    # ===== Score + métadonnées =====
    couleur_res = COULEUR_VERT if m_row["resultat"] == "Victoire" else (COULEUR_AMBRE if m_row["resultat"] == "Nul" else COULEUR_PRIMAIRE)

    st.markdown(f"""
    <div style="background:rgba(128,128,128,0.08);padding:24px;border-radius:10px;
                border-left:6px solid {couleur_res};margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="font-size:14px;color:#888;text-transform:uppercase;">Adversaire</div>
                <div style="font-size:28px;font-weight:600;">{m_row['adversaire']} (M{m_row['match_no']})</div>
                <div style="font-size:13px;color:#888;margin-top:4px;">
                    {m_row['competition'] or 'Compétition non renseignée'} · {m_row['lieu'] or 'Lieu non renseigné'}
                </div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:48px;font-weight:700;">{m_row['score_pour']} - {m_row['score_contre']}</div>
                <div style="color:{couleur_res};font-size:20px;font-weight:600;">{m_row['resultat']}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ===== Stats globales équipe pour ce match =====
    perfs_match = get_perfs(m_id)
    perfs_match_jc = perfs_match[perfs_match["role"] != "Gardien"]

    st.markdown("### Stats d'équipe du match")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Tirs total", int(perfs_match_jc["tirs_total"].sum()))
    c2.metric("Tirs cadrés", int(perfs_match_jc["tirs_cadres"].sum()))
    c3.metric("Interceptions", int(perfs_match_jc["interceptions"].sum()))
    c4.metric("Récupérations", int(perfs_match_jc["recuperations"].sum()))
    c5.metric("Pertes", int(perfs_match_jc["pertes_de_balles"].sum()))
    c6.metric("Fautes commises", int(perfs_match_jc["fautes_commises"].sum()))

    st.markdown("---")

    # ===== Top 3 par critère =====
    st.subheader("🏆 Top 3 du match")

    criteres_top3 = {
        "Buts": "buts", "Passes décisives": "passes_decisives",
        "Buts + Passes décisives": "b_plus_pd",
        "Tirs cadrés": "tirs_cadres", "Interceptions": "interceptions",
        "Récupérations": "recuperations", "Duels OFF gagnés": "duels_off_gagnes",
        "Duels DEF gagnés": "duels_def_gagnes",
        "Minutes jouées": "temps_jeu_min", "Note (Brute)": "note"
    }
    critere_choisi = st.selectbox("Critère", list(criteres_top3.keys()))
    col_crit = criteres_top3[critere_choisi]

    # Préparer les données
    df_top = perfs_match_jc.copy()
    if col_crit == "b_plus_pd":
        df_top["b_plus_pd"] = df_top["buts"] + df_top["passes_decisives"]
    if col_crit == "note":
        # Calculer les notes du match
        all_notes = calculer_toutes_notes()
        notes_match = all_notes[all_notes["match_id"] == m_id]
        df_top = df_top.merge(
            notes_match[["joueur_id", "note"]], on="joueur_id", how="left"
        )

    top3 = df_top.sort_values(col_crit, ascending=False).head(3)

    medailles = ["🥇", "🥈", "🥉"]
    couleurs_med = ["#FFD700", "#C0C0C0", "#CD7F32"]
    cols_top = st.columns(3)
    for i, (_, j) in enumerate(top3.iterrows()):
        with cols_top[i]:
            valeur = j[col_crit] if pd.notna(j[col_crit]) else 0
            val_str = f"{int(valeur)}" if valeur == int(valeur) else f"{valeur:.1f}"
            st.markdown(f"""
            <div style="background:rgba(128,128,128,0.08);padding:20px;border-radius:8px;
                        border:2px solid {couleurs_med[i]};text-align:center;">
                <div style="font-size:38px;">{medailles[i]}</div>
                <div style="font-size:20px;font-weight:600;margin-top:8px;">{j['joueur']}</div>
                <div style="font-size:13px;color:#888;">{j['poste'] or ''}</div>
                <div style="font-size:34px;font-weight:700;color:{couleurs_med[i]};margin-top:10px;">
                    {val_str}
                </div>
                <div style="font-size:12px;color:#888;">{critere_choisi}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ===== Composition / tableau complet =====
    st.subheader("👥 Composition")
    compo = perfs_match[["joueur", "poste", "numero_match", "role", "temps_jeu_min",
                         "buts", "passes_decisives", "tirs_cadres",
                         "interceptions", "recuperations", "pertes_de_balles"]].copy()
    compo["temps_jeu_min"] = compo["temps_jeu_min"].round(1)
    compo.columns = ["Joueur", "Poste", "N°", "Rôle", "Min", "B", "PD", "T.cad",
                     "Inter.", "Récup.", "Pertes"]
    st.dataframe(
        compo.sort_values("Min", ascending=False),
        hide_index=True, use_container_width=True
    )

    # ===== Faits marquants =====
    st.markdown("---")
    st.subheader("⚡ Faits marquants")

    buteurs = perfs_match_jc[perfs_match_jc["buts"] > 0].sort_values("buts", ascending=False)
    passeurs = perfs_match_jc[perfs_match_jc["passes_decisives"] > 0].sort_values("passes_decisives", ascending=False)

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.markdown("**Buteurs**")
        if buteurs.empty:
            st.caption("_Aucun but marqué_")
        else:
            for _, b in buteurs.iterrows():
                st.markdown(f"⚽ **{b['joueur']}** — {int(b['buts'])} but(s)")

    with col_f2:
        st.markdown("**Passeurs**")
        if passeurs.empty:
            st.caption("_Aucune passe décisive_")
        else:
            for _, p in passeurs.iterrows():
                st.markdown(f"🎯 **{p['joueur']}** — {int(p['passes_decisives'])} passe(s) déc.")

    # Gardiens du match
    gks_match = perfs_match[perfs_match["role"] == "Gardien"]
    if not gks_match.empty:
        st.markdown("**Gardiens**")
        for _, g in gks_match.iterrows():
            st.markdown(f"🧤 **{g['joueur']}** — {int(g['arrets'] or 0)} arrêt(s), "
                        f"{int(g['buts_encaisses'] or 0)} but(s) encaissé(s) sur {g['temps_jeu_min']:.0f} min")

    # ===== EXPORT PDF =====
    st.markdown("---")
    if st.button("📄 Générer un PDF de ce match", type="primary", key="pdf_match"):
        # Stats équipe
        tab_kpi = [
            {"type": "kpi", "label": "Score", "value": f"{m_row['score_pour']} - {m_row['score_contre']}"},
            {"type": "kpi", "label": "Résultat", "value": m_row["resultat"]},
            {"type": "kpi", "label": "Lieu", "value": m_row["lieu"] or "-"},
            {"type": "kpi", "label": "Tirs", "value": int(perfs_match_jc["tirs_total"].sum())},
            {"type": "kpi", "label": "Tirs cadrés", "value": int(perfs_match_jc["tirs_cadres"].sum())},
            {"type": "kpi", "label": "Pertes", "value": int(perfs_match_jc["pertes_de_balles"].sum())},
        ]
        # Compo
        tab_compo = [["Joueur", "Poste", "Rôle", "Min", "B", "PD", "T.cad", "Inter.", "Récup.", "Pertes"]]
        for _, p in perfs_match.sort_values("temps_jeu_min", ascending=False).iterrows():
            tab_compo.append([p["joueur"], p["poste"] or "-", p["role"],
                              f"{p['temps_jeu_min']:.1f}",
                              str(int(p["buts"] or 0)), str(int(p["passes_decisives"] or 0)),
                              str(int(p["tirs_cadres"] or 0)),
                              str(int(p["interceptions"] or 0)),
                              str(int(p["recuperations"] or 0)),
                              str(int(p["pertes_de_balles"] or 0))])
        # Faits marquants
        faits_lignes = []
        for _, b in buteurs.iterrows():
            faits_lignes.append(f"⚽ {b['joueur']} — {int(b['buts'])} but(s)")
        for _, p in passeurs.iterrows():
            faits_lignes.append(f"🎯 {p['joueur']} — {int(p['passes_decisives'])} passe(s) déc.")
        for _, g in gks_match.iterrows():
            faits_lignes.append(f"🧤 {g['joueur']} — {int(g['arrets'] or 0)} arrêts, {int(g['buts_encaisses'] or 0)} BE")
        faits_html = "<br/>".join(faits_lignes) if faits_lignes else "Aucun fait marquant."

        sections = tab_kpi + [
            {"type": "table", "title": "Composition", "data": tab_compo,
             "widths": [3.5*cm, 2.5*cm, 2*cm, 1.5*cm, 1*cm, 1*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.4*cm]},
            {"type": "texte", "title": "Faits marquants", "content": faits_html},
        ]
        titre_pdf = f"Match {m_row['libelle']}"
        pdf_buf = pdf_generique(titre_pdf, equipe["nom"], sections, paysage=True)
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=f"match_{m_row['libelle'].replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="dl_match"
        )


# ============================================================================
# PAGE — FICHE JOUEUR (avec correction tirs cadrés % + comparaison entre matchs)
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

    # Format spécial pour Tirs cadrés (%)
    if agg_brut["tirs_total"] > 0:
        pct_str = f"{(agg_brut['tirs_cadres'] / agg_brut['tirs_total'])*100:.0f}%"
    else:
        pct_str = "-"
    tirs_cad_val = fmt(agg["tirs_cadres"], mode)
    tirs_cad_label = "Tirs cadrés (%)"
    tirs_cad_display = f"{tirs_cad_val} ({pct_str})" if pct_str != "-" else tirs_cad_val

    with c_off:
        st.markdown("##### Contribution offensive")
        st.metric("Buts", fmt(agg["buts"], mode))
        st.metric("Passes décisives", fmt(agg["passes_decisives"], mode))
        st.metric("Tirs", fmt(agg["tirs_total"], mode))
        st.metric(tirs_cad_label, tirs_cad_display)

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
        ("Buts", "buts"), ("Passes D.", "passes_decisives"),
        ("Tirs", "tirs_total"), ("Tirs cadrés", "tirs_cadres"),
        ("Interceptions", "interceptions"), ("Récupérations", "recuperations"),
        ("D.OFF gagnés", "duels_off_gagnes"), ("D.DEF gagnés", "duels_def_gagnes"),
        ("Pertes", "pertes_de_balles"),
    ]
    labels_c = [lbl for lbl, _ in indicateurs_comp]
    val_j = [agg_j_mode[col] if pd.notna(agg_j_mode[col]) else 0 for _, col in indicateurs_comp]
    val_m = [moy_equipe[col] if pd.notna(moy_equipe.get(col)) else 0 for _, col in indicateurs_comp]

    col_bar, col_rad = st.columns([1.1, 1])
    with col_bar:
        fig_bar = barres_horizontales_comparaison(
            labels_c, val_j, val_m, nom_joueur=joueur_sel, nom_ref="Moy. Équipe"
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    with col_rad:
        st.markdown("**Radar profil (échelle normalisée par axe)**")
        fig_rad = radar_normalise(val_j, val_m, labels_c,
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

        # ===== COMPARAISON ENTRE 2 MATCHS DU MEME JOUEUR =====
        st.markdown("---")
        st.subheader("🔍 Comparer 2 matchs de ce joueur")

        matchs_dispo = df_j_brut["match_code"].tolist()
        labels_match = {}
        for _, p in df_j_brut.iterrows():
            labels_match[p["match_code"]] = f"{p['adversaire']} M{matchs.loc[matchs['match_id']==p['match_id'],'match_no'].iloc[0]}"

        if len(matchs_dispo) >= 2:
            col_m1, col_m2 = st.columns(2)
            m1_choice = col_m1.selectbox("Match A",
                                          options=matchs_dispo,
                                          format_func=lambda x: labels_match[x],
                                          index=0, key="cmp_m1")
            m2_choice = col_m2.selectbox("Match B",
                                          options=matchs_dispo,
                                          format_func=lambda x: labels_match[x],
                                          index=1, key="cmp_m2")

            if m1_choice != m2_choice:
                p1 = df_j_brut[df_j_brut["match_code"] == m1_choice].iloc[0]
                p2 = df_j_brut[df_j_brut["match_code"] == m2_choice].iloc[0]

                indicateurs_match = [
                    ("Min", "temps_jeu_min"), ("Buts", "buts"),
                    ("Passes décisives", "passes_decisives"),
                    ("Tirs total", "tirs_total"), ("Tirs cadrés", "tirs_cadres"),
                    ("Interceptions", "interceptions"),
                    ("Récupérations", "recuperations"),
                    ("Duels OFF gagnés", "duels_off_gagnes"),
                    ("Duels DEF gagnés", "duels_def_gagnes"),
                    ("Pertes", "pertes_de_balles"),
                    ("Fautes commises", "fautes_commises"),
                ]

                comp_data = []
                for lbl, col in indicateurs_match:
                    v1 = p1[col] if pd.notna(p1[col]) else 0
                    v2 = p2[col] if pd.notna(p2[col]) else 0
                    diff = v2 - v1
                    diff_str = f"{diff:+.1f}" if not isinstance(v1, int) and not float(v1).is_integer() else f"{int(diff):+d}"
                    if col == "temps_jeu_min":
                        v1_s = f"{v1:.1f}"
                        v2_s = f"{v2:.1f}"
                        diff_str = f"{diff:+.1f}"
                    else:
                        v1_s = str(int(v1))
                        v2_s = str(int(v2))
                        diff_str = f"{int(diff):+d}"
                    comp_data.append([lbl, v1_s, v2_s, diff_str])

                df_cmp = pd.DataFrame(comp_data,
                                       columns=["Indicateur", labels_match[m1_choice],
                                                labels_match[m2_choice], "Évolution"])
                st.dataframe(df_cmp, hide_index=True, use_container_width=True)
                st.caption("L'**Évolution** est calculée comme B − A. Vert (positif) = progression sur cet indicateur, sauf pour les indicateurs négatifs (Pertes, Fautes commises) où une baisse est positive.")
            else:
                st.info("Sélectionne deux matchs différents.")
        else:
            st.caption("_Pas assez de matchs pour comparer._")

    # ===== EXPORT PDF =====
    st.markdown("---")
    st.subheader("Exporter")
    if st.button("📄 Générer un PDF de cette fiche", type="primary"):
        coefs = get_coefficients()
        params = get_parametres()
        matchs_idx = matchs.set_index("match_id")
        notes_j = []
        for _, p in df_j_brut.iterrows():
            m_row = matchs_idx.loc[p["match_id"]]
            n = calculer_note_match(p, m_row, coefs, params)
            notes_j.append({"match": m_row["libelle"], **n})

        # Préparer les 3 versions des stats : brut, par minute, per 40
        df_j_min = appliquer_mode(df_j_brut, "Par minute")
        df_j_40 = appliquer_mode(df_j_brut, "Per 40 min")
        if match_id_filtre is None:
            agg_b = agreger_joueur(df_j_brut, "Stats brutes").iloc[0]
            agg_min_pdf = agreger_joueur(df_j_min, "Par minute").iloc[0]
            agg_40_pdf = agreger_joueur(df_j_40, "Per 40 min").iloc[0]
        else:
            agg_b = df_j_brut.iloc[0]
            agg_min_pdf = df_j_min.iloc[0]
            agg_40_pdf = df_j_40.iloc[0]
        if "matchs" not in agg_b:
            agg_b = pd.concat([agg_b, pd.Series({"matchs": 1})])
        if "matchs" not in agg_min_pdf:
            agg_min_pdf = pd.concat([agg_min_pdf, pd.Series({"matchs": 1})])
        if "matchs" not in agg_40_pdf:
            agg_40_pdf = pd.concat([agg_40_pdf, pd.Series({"matchs": 1})])

        # Récupérer la photo si elle existe
        photo_pdf = photo_joueur(joueur_sel)

        pdf_buf = pdf_fiche_joueur(joueur_sel, agg_b, agg_min_pdf, agg_40_pdf,
                                    df_j_brut, notes_j, equipe["nom"],
                                    photo_path=photo_pdf)
        nom_fichier = f"fiche_{joueur_sel.replace(' ', '_').replace('.', '')}_{date.today().strftime('%Y%m%d')}.pdf"
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf, file_name=nom_fichier, mime="application/pdf"
        )
        st.success("PDF prêt, clique sur 'Télécharger'.")


# ============================================================================
# PAGE — COMPARAISON
# ============================================================================

elif page == "Comparaison":
    st.title("Comparaison de joueurs")

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

    # Sélecteur de mode (Per 40 par défaut = mode recommandé)
    mode_cmp = st.radio(
        "Mode de comparaison",
        ["Stats brutes", "Par minute", "Per 40 min"],
        horizontal=True, key="mode_cmp", index=2,
        help="Brutes = totaux. Par minute = stat / min jouées. Per 40 = extrapolation sur un match complet (recommandé pour comparer des joueurs avec des temps de jeu différents)."
    )
    st.caption(f"Portée : {portee} · Mode : {mode_cmp}")

    df_cmp = appliquer_mode(perfs_raw, mode_cmp)

    def stats_joueur(nom):
        sub = df_cmp[df_cmp["joueur"] == nom]
        if match_id_filtre is None:
            return agreger_joueur(sub, mode_cmp).iloc[0]
        return sub.iloc[0]

    s1 = stats_joueur(j1)
    s2 = stats_joueur(j2)

    # Suffixe d'affichage selon le mode
    suffixe = {"Stats brutes": "", "Par minute": "/min", "Per 40 min": "/40"}[mode_cmp]

    indicateurs = [
        (f"Buts{suffixe}", "buts"), (f"PD{suffixe}", "passes_decisives"),
        (f"Tirs{suffixe}", "tirs_total"), (f"Tirs cadrés{suffixe}", "tirs_cadres"),
        (f"Interceptions{suffixe}", "interceptions"), (f"Récupérations{suffixe}", "recuperations"),
        (f"D.OFF gagnés{suffixe}", "duels_off_gagnes"), (f"D.DEF gagnés{suffixe}", "duels_def_gagnes"),
        (f"Pertes{suffixe}", "pertes_de_balles"), (f"Fautes commises{suffixe}", "fautes_commises"),
    ]

    # Formatage : entier en brutes, 3 décimales en par minute (valeurs petites), 2 sinon
    # Format string forcé pour que Streamlit affiche correctement les décimales
    if mode_cmp == "Stats brutes":
        decimales = 0
    elif mode_cmp == "Par minute":
        decimales = 3
    else:  # Per 40 min
        decimales = 2

    def _fmt_cmp(v):
        if pd.isna(v):
            return "-"
        if decimales == 0:
            return f"{int(round(v))}"
        return f"{v:.{decimales}f}"

    tab_comp = pd.DataFrame({
        "Indicateur": [lbl for lbl, _ in indicateurs],
        j1: [_fmt_cmp(s1[c]) for _, c in indicateurs],
        j2: [_fmt_cmp(s2[c]) for _, c in indicateurs],
    })

    # Rappel temps de jeu (utile pour interpréter le mode brut)
    tj1 = s1.get("temps_jeu_min", 0) or 0
    tj2 = s2.get("temps_jeu_min", 0) or 0
    st.caption(f"⏱ {j1} : {tj1:.1f} min jouées · {j2} : {tj2:.1f} min jouées")
    col_t, col_b = st.columns([1, 1.3])
    with col_t:
        st.subheader("Tableau comparatif")
        st.dataframe(tab_comp, hide_index=True, use_container_width=True)
    with col_b:
        st.subheader("Comparaison par indicateur")
        labels_i = [lbl for lbl, _ in indicateurs]
        v1 = [s1[c] if pd.notna(s1[c]) else 0 for _, c in indicateurs]
        v2 = [s2[c] if pd.notna(s2[c]) else 0 for _, c in indicateurs]
        # Mêmes couleurs que le radar : j1=ROUGE, j2=BLEU
        fig = barres_horizontales_comparaison(
            labels_i, v1, v2, nom_joueur=j1, nom_ref=j2,
            couleur_joueur=COULEUR_PRIMAIRE, couleur_ref=COULEUR_BLEU,
            decimales=decimales if decimales > 0 else 1
        )
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
    st.plotly_chart(
        radar_comparaison_2joueurs(radar_s1, radar_s2, j1, j2,
                                    couleur1=COULEUR_PRIMAIRE, couleur2=COULEUR_BLEU),
        use_container_width=True
    )

    # ===== EXPORT PDF =====
    st.markdown("---")
    if st.button("📄 Générer un PDF de la comparaison", type="primary", key="pdf_cmp"):
        tab_data = [[f"Indicateur ({mode_cmp})", j1, j2]]
        for lbl, col in indicateurs:
            v1_str = _fmt_cmp(s1[col])
            v2_str = _fmt_cmp(s2[col])
            tab_data.append([lbl, v1_str, v2_str])
        sections = [
            {"type": "table", "title": f"{j1} vs {j2} ({mode_cmp})",
             "data": tab_data,
             "widths": [6*cm, 5*cm, 5*cm]},
        ]
        pdf_buf = pdf_generique("Comparaison de joueurs", equipe["nom"], sections)
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=f"compare_{j1.replace(' ','_').replace('.','')}_vs_{j2.replace(' ','_').replace('.','')}_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="dl_cmp"
        )


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
            elif mode == "Par minute":
                agg_disp[c] = agg_disp[c].apply(lambda v: round(v, 3) if pd.notna(v) else "-")
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

    # ===== EXPORT PDF =====
    st.markdown("---")
    if st.button("📄 Générer un PDF de la page Gardiens", type="primary", key="pdf_gk"):
        tab_synth = [["Gardien", "M", "Min", "BE", "Arrêts", "Rel.+", "Rel.-"]]
        for _, row in agg_disp.iterrows():
            tab_synth.append([str(row[c]) for c in agg_disp.columns])
        sections = [
            {"type": "table", "title": "Synthèse gardiens", "data": tab_synth,
             "widths": [4*cm, 1.5*cm, 2*cm, 1.8*cm, 2*cm, 1.8*cm, 1.8*cm]},
        ]
        pdf_buf = pdf_generique("Gardiens", equipe["nom"], sections)
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=f"gardiens_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="dl_gk"
        )


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
            valeur=(col_choisie, "sum")).reset_index()
        stats_par_match = stats_par_match.merge(
            matchs[["match_id", "libelle"]], on="match_id").sort_values("match_id")
        fig = go.Figure(go.Bar(
            x=stats_par_match["libelle"], y=stats_par_match["valeur"],
            marker=dict(color=COULEUR_BLEU),
            text=stats_par_match["valeur"].astype(int),
            textposition="outside", textfont=dict(size=12)))
        fig.update_layout(
            title=f"{ind_choisi} — match par match",
            height=350, margin=dict(l=10, r=10, t=50, b=20),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Évolution d'un joueur")
        joueurs_dispo_e = sorted(get_perfs()["joueur"].unique())
        joueur_sel_e = st.selectbox("Joueur", joueurs_dispo_e, key="evol_joueur")
        df_joueur = get_perfs()
        df_joueur = df_joueur[df_joueur["joueur"] == joueur_sel_e].sort_values("match_id")
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

    # ===== EXPORT PDF (équipe par défaut) =====
    st.markdown("---")
    if st.button("📄 Générer un PDF de l'évolution équipe", type="primary", key="pdf_evol"):
        # Tableau évolution équipe : buts pour/contre par match
        tab_evol = [["Match", "Buts pour", "Buts contre", "Résultat", "Diff"]]
        for _, m in matchs.iterrows():
            tab_evol.append([m["libelle"], str(m["score_pour"]), str(m["score_contre"]),
                             m["resultat"], f"{m['diff_buts']:+d}"])
        sections = [
            {"type": "table", "title": "Évolution des scores match par match",
             "data": tab_evol,
             "widths": [4*cm, 3*cm, 3*cm, 3*cm, 2.5*cm]},
        ]
        pdf_buf = pdf_generique("Évolution sur la saison", equipe["nom"], sections)
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=f"evolution_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="dl_evol"
        )


# ============================================================================
# PAGE — TENDANCE FORME (nouvelle)
# ============================================================================

elif page == "Tendance forme":
    st.title("Tendance de forme")
    st.caption("On compare les N derniers matchs d'un joueur aux N matchs précédents")

    # Sélecteurs
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        fenetre = st.selectbox("Fenêtre de comparaison",
                                [2, 3, 5],
                                index=1,
                                format_func=lambda n: f"{n} derniers vs {n} précédents")
    with col_s2:
        indicateurs_tf = {
            "Note Brute": "note",
            "Buts": "buts",
            "Passes décisives": "passes_decisives",
            "Buts + Passes décisives": "b_plus_pd",
            "Tirs cadrés": "tirs_cadres",
            "Interceptions": "interceptions",
            "Récupérations": "recuperations",
            "Duels OFF gagnés": "duels_off_gagnes",
            "Duels DEF gagnés": "duels_def_gagnes",
        }
        ind_tf_label = st.selectbox("Indicateur", list(indicateurs_tf.keys()))

    col_ind = indicateurs_tf[ind_tf_label]
    min_matchs_requis = 2 * fenetre  # N + N

    # Construire les données
    notes_df = calculer_toutes_notes() if col_ind == "note" else None
    perfs_all = get_perfs()
    perfs_jc = perfs_all[perfs_all["role"] != "Gardien"].copy()

    joueurs_uniques = sorted(perfs_jc["joueur"].unique())
    rows = []
    for j in joueurs_uniques:
        df_jp = perfs_jc[perfs_jc["joueur"] == j].sort_values("match_id")
        if df_jp.empty:
            continue
        if col_ind == "note":
            df_jp_notes = notes_df[notes_df["joueur"] == j].sort_values("match_id")
            if df_jp_notes.empty:
                continue
            valeurs_all = df_jp_notes["note"].tolist()
        elif col_ind == "b_plus_pd":
            df_jp["b_plus_pd"] = df_jp["buts"] + df_jp["passes_decisives"]
            valeurs_all = df_jp["b_plus_pd"].tolist()
        else:
            valeurs_all = df_jp[col_ind].tolist()

        n_total = len(valeurs_all)
        # On ne peut comparer que si on a au moins 2N matchs
        if n_total < min_matchs_requis:
            rows.append({
                "joueur": j, "n_matchs": n_total,
                "moy_recent": None, "moy_precedent": None,
                "diff": None, "tendance": "—",
                "couleur": COULEUR_GRIS, "statut": "Pas assez de matchs"
            })
            continue

        # N derniers vs N précédents
        recent = valeurs_all[-fenetre:]
        precedent = valeurs_all[-2*fenetre:-fenetre]
        moy_recent = sum(recent) / len(recent)
        moy_precedent = sum(precedent) / len(precedent)
        diff = moy_recent - moy_precedent

        # Tendance : seuil 5% de la moyenne précédente, minimum 0.1
        seuil = max(0.05 * abs(moy_precedent), 0.1)
        if abs(diff) < seuil:
            tendance = "→ Stable"
            couleur_t = COULEUR_GRIS
        elif diff > 0:
            tendance = "↑ En progression"
            couleur_t = COULEUR_VERT
        else:
            tendance = "↓ En régression"
            couleur_t = COULEUR_PRIMAIRE

        rows.append({
            "joueur": j, "n_matchs": n_total,
            "moy_recent": round(moy_recent, 2),
            "moy_precedent": round(moy_precedent, 2),
            "diff": round(diff, 2),
            "tendance": tendance,
            "couleur": couleur_t,
            "statut": "OK"
        })

    df_t = pd.DataFrame(rows)

    # Séparer les joueurs comparables des autres
    df_ok = df_t[df_t["statut"] == "OK"].sort_values("diff", ascending=False)
    df_pas_assez = df_t[df_t["statut"] != "OK"]

    st.markdown("---")
    st.subheader(f"Forme actuelle — {ind_tf_label}")
    st.caption(f"_Moyenne sur les {fenetre} derniers matchs vs les {fenetre} précédents (il faut au moins {min_matchs_requis} matchs)_")

    if df_ok.empty:
        st.warning(f"⚠️ Aucun joueur n'a encore joué assez de matchs pour comparer "
                   f"sur cette fenêtre ({min_matchs_requis} matchs requis). "
                   f"Essaie une fenêtre plus petite, ou attends d'avoir plus de matchs.")
    else:
        col_tab, col_chart = st.columns([1, 1.2])

        with col_tab:
            affichage_rows = []
            for _, r in df_ok.iterrows():
                affichage_rows.append({
                    "Joueur": r["joueur"],
                    f"{fenetre} derniers": r["moy_recent"],
                    f"{fenetre} précédents": r["moy_precedent"],
                    "Δ": f"{r['diff']:+.2f}",
                    "Tendance": r["tendance"]
                })
            st.dataframe(pd.DataFrame(affichage_rows), hide_index=True, use_container_width=True,
                         height=min(600, 35 * len(affichage_rows) + 50))

        with col_chart:
            df_sorted = df_ok.sort_values("diff", ascending=True)
            couleurs_bars = []
            for d in df_sorted["diff"]:
                if d > 0.1:
                    couleurs_bars.append(COULEUR_VERT)
                elif d < -0.1:
                    couleurs_bars.append(COULEUR_PRIMAIRE)
                else:
                    couleurs_bars.append(COULEUR_GRIS)
            fig = go.Figure(go.Bar(
                y=df_sorted["joueur"], x=df_sorted["diff"], orientation='h',
                marker=dict(color=couleurs_bars),
                text=df_sorted["diff"].apply(lambda v: f"{v:+.2f}"),
                textposition="outside", textfont=dict(size=11),
                cliponaxis=False
            ))
            fig.update_layout(
                title=f"Δ {ind_tf_label} ({fenetre} derniers − {fenetre} précédents)",
                height=max(400, 28 * len(df_sorted) + 80),
                margin=dict(l=10, r=40, t=50, b=20),
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)",
                           zeroline=True, zerolinecolor="#888", zerolinewidth=2),
                yaxis=dict(showgrid=False, automargin=True),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "**↑ vert** = progression nette · **↓ rouge** = régression nette · "
            "**→ gris** = stable (Δ < 10% ou < 0.1). "
            "La forme se base sur l'écart entre les 2 dernières périodes de jeu."
        )

    # Joueurs sans assez de matchs
    if not df_pas_assez.empty:
        st.markdown("---")
        st.markdown("##### Joueurs sans données suffisantes")
        st.caption(f"Ces joueurs ont moins de {min_matchs_requis} matchs.")
        not_enough = df_pas_assez[["joueur", "n_matchs"]].copy()
        not_enough.columns = ["Joueur", "Matchs joués"]
        st.dataframe(not_enough, hide_index=True, use_container_width=True)

    # ===== EXPORT PDF =====
    if not df_ok.empty:
        st.markdown("---")
        if st.button("📄 Générer un PDF de la tendance", type="primary", key="pdf_tf"):
            tab_tf = [["Joueur", f"{fenetre} derniers", f"{fenetre} précédents", "Δ", "Tendance"]]
            for _, r in df_ok.iterrows():
                tab_tf.append([r["joueur"], f"{r['moy_recent']}",
                               f"{r['moy_precedent']}", f"{r['diff']:+.2f}",
                               r["tendance"]])
            sections = [
                {"type": "table",
                 "title": f"Tendance de forme — {ind_tf_label}",
                 "data": tab_tf,
                 "widths": [5*cm, 3*cm, 3*cm, 2*cm, 4*cm]},
            ]
            pdf_buf = pdf_generique("Tendance de forme", equipe["nom"], sections)
            st.download_button(
                label="⬇ Télécharger le PDF",
                data=pdf_buf,
                file_name=f"tendance_forme_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                key="dl_tf"
            )


# ============================================================================
# PAGE — NOTATION
# ============================================================================

elif page == "Notation":
    st.title("Notation des joueurs")
    st.caption("Note Brute calculée pour chaque joueur dans chaque match")

    df_notes = calculer_toutes_notes()

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
        if match_sel != "Tous":
            st.markdown("---")
            if st.button("📄 Exporter ce match en PDF", type="primary"):
                notes_match = df_notes[df_notes["match"] == match_sel].to_dict("records")
                pdf_buf = pdf_notation_match(match_sel, notes_match, equipe["nom"])
                nom_fichier = f"notation_{match_sel.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf"
                st.download_button(label="⬇ Télécharger le PDF",
                                    data=pdf_buf, file_name=nom_fichier, mime="application/pdf")

    with tab2:
        st.subheader("Classement cumulé (moyenne des notes)")
        classement = df_notes.groupby("joueur").agg(
            matchs=("match_id", "nunique"), note_moy=("note", "mean"),
            note_min=("note", "min"), note_max=("note", "max"),
            min_total=("min", "sum")
        ).reset_index().sort_values("note_moy", ascending=False)
        classement_disp = classement.copy()
        for col in ["note_moy", "note_min", "note_max"]:
            classement_disp[col] = classement_disp[col].round(2)
        classement_disp["min_total"] = classement_disp["min_total"].round(1)
        classement_disp.columns = ["Joueur", "Matchs", "Note moy.", "Note min", "Note max", "Min joués"]
        st.dataframe(classement_disp, hide_index=True, use_container_width=True)
        top10 = classement.head(10)
        fig = go.Figure(go.Bar(
            x=top10["note_moy"], y=top10["joueur"], orientation='h',
            marker=dict(color=COULEUR_PRIMAIRE),
            text=top10["note_moy"].round(2), textposition="outside"))
        fig.update_layout(
            title="Top 10 — note moyenne",
            height=400, margin=dict(l=10, r=40, t=50, b=20),
            xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)", range=[0, 22]),
            yaxis=dict(autorange="reversed", automargin=True),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# PAGE — CALENDRIER
# ============================================================================

elif page == "Calendrier":
    st.title("Calendrier de la saison")
    st.caption("Vue de tous les matchs de la saison — joués et à venir")

    tab_joues, tab_avenir = st.tabs(["📅 Matchs joués", "🔜 À venir"])

    with tab_joues:
        if matchs.empty:
            st.info("Aucun match joué pour l'instant.")
        else:
            for _, m in matchs.iterrows():
                couleur = COULEUR_VERT if m["resultat"] == "Victoire" else (COULEUR_AMBRE if m["resultat"] == "Nul" else COULEUR_PRIMAIRE)
                date_str = m["date_match"] if pd.notna(m["date_match"]) and m["date_match"] else "Date non renseignée"
                compet = m["competition"] or "—"
                lieu = m["lieu"] or "—"

                st.markdown(f"""
                <div style="background:rgba(128,128,128,0.08);padding:18px;border-radius:8px;
                            border-left:5px solid {couleur};margin-bottom:14px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div style="flex:1;">
                            <div style="font-size:13px;color:#888;text-transform:uppercase;">{date_str} · {compet}</div>
                            <div style="font-size:22px;font-weight:600;margin-top:6px;">{m['libelle']}</div>
                            <div style="font-size:13px;color:#888;margin-top:4px;">📍 {lieu}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:32px;font-weight:700;">{m['score_pour']} - {m['score_contre']}</div>
                            <div style="color:{couleur};font-weight:600;font-size:15px;">{m['resultat']}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with tab_avenir:
        st.info("Aucun match à venir n'est encore programmé. Tu pourras ajouter les futurs matchs (date, adversaire, lieu) dans la base de données quand tu auras le programme.")
        # Placeholders gris pour visualiser le futur
        st.markdown("**Aperçu visuel (placeholders)** :")
        for i in range(1, 4):
            st.markdown(f"""
            <div style="background:rgba(128,128,128,0.04);padding:18px;border-radius:8px;
                        border:1px dashed rgba(128,128,128,0.3);margin-bottom:10px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <div style="font-size:13px;color:#888;text-transform:uppercase;">À venir · Match {len(matchs)+i}</div>
                        <div style="font-size:20px;color:#666;margin-top:6px;">Adversaire à définir</div>
                        <div style="font-size:13px;color:#888;margin-top:4px;">📍 Lieu à définir</div>
                    </div>
                    <div style="font-size:32px;color:#666;">- - -</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ===== EXPORT PDF =====
    st.markdown("---")
    if st.button("📄 Générer un PDF du calendrier", type="primary", key="pdf_cal"):
        tab_cal = [["Date", "Match", "Lieu", "Compétition", "Score", "Résultat"]]
        for _, m in matchs.iterrows():
            tab_cal.append([
                str(m["date_match"]) if pd.notna(m["date_match"]) and m["date_match"] else "-",
                m["libelle"], m["lieu"] or "-", m["competition"] or "-",
                f"{m['score_pour']} - {m['score_contre']}", m["resultat"]
            ])
        sections = [
            {"type": "table", "title": "Matchs joués", "data": tab_cal,
             "widths": [2.5*cm, 3*cm, 2.5*cm, 3*cm, 2*cm, 2.5*cm]},
        ]
        pdf_buf = pdf_generique("Calendrier de la saison", equipe["nom"], sections)
        st.download_button(
            label="⬇ Télécharger le PDF",
            data=pdf_buf,
            file_name=f"calendrier_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="dl_cal"
        )


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
        ("**Rel.-**", "Relances loupées"),
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
    - **Per 40 min** : extrapolation sur un match complet (40 min). Mode de référence pour comparer.
    """)
    st.markdown("---")
    st.markdown("### Système de notation")
    st.markdown("""
    > **Brute = 10 + Δ OFF + Δ DEF + Δ NEG + Δ GK + Bonus résultat**

    La **Note /20** est la Brute bornée entre 0 et 20.
    Le **Bonus résultat** est fixe : **+3 victoire, +1.5 nul, 0 défaite**.
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
                lambda v: f"+{v}" if v > 0 else f"{v}")
            st.dataframe(sub, hide_index=True, use_container_width=True)

    afficher_famille(col_off, "OFFENSIF", COULEUR_PRIMAIRE)
    afficher_famille(col_def, "DEFENSIF", COULEUR_BLEU)
    afficher_famille(col_neg, "NEGATIF", COULEUR_GRIS)
    afficher_famille(col_gk, "GARDIEN", COULEUR_VERT)
