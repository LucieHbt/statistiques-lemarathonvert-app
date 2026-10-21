"""Données chronométriques : Le Marathon Vert Rennes (Streamlit)
Colonnes : Annee,Statut,Classement,Dossard,Nom,Prénom,Sexe,Club,Catégorie,Classement_Cat,Temps_s,Temps_reel_s
Fond : https://www.lemarathonvert.org/scripts/files/690cab002365b8.66110376/@biduleee__-part248.webp"
Logo : https://www.lemarathonvert.org/scripts/files/698eead8c70301.68707929/header_logo.webp
"""

from pathlib import Path
from carte_pdf import generer_carte
from html import escape

import base64
import urllib.request
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import re
import unicodedata
import html
import streamlit as st

DATA = Path(__file__).parent / "data" / "resultats.csv"
ASSETS = Path(__file__).parent / "assets"

# --- Identité de l'événement -------------------------------------------------
NOM_EVENT = "Marathon Vert Rennes"
# Images : on cherche d'abord dans assets/ (logo.webp|png, fond.webp|jpg).
# Optionnel : URL de base à laquelle télécharger ces fichiers s'ils sont absents du dépôt.
ASSETS_URL = ""

# Palette
FOND, VERT, ROUGE = "#0e3610", "#0d8c39", "#C24247"
OR, ARGENT, BRONZE = "#E0B400", "#9A9A9A", "#E8743B"
SEXES = {"Homme": "Hommes", "Femme": "Femmes"}

# Tranches de temps adaptées au marathon : < 3h00 | 3h00-3h20 | ... | 5h20-5h40 | ≥ 5h40
TRANCHE_DEBUT, TRANCHE_FIN, TRANCHE_PAS = 150, 330, 10   # en minutes
BW_DENSITE = 480                                          # lissage de la courbe (s)
HEADS = ".st-key-evol_head, .st-key-perf,.st-key-distrib_head, .st-key-classement_head"

# Statuts (comparés après normalisation : minuscules, sans accents)
RE_NON_PARTANT = r"\b(?:dns|non partant\w*|absent\w*|forfait\w*)\b"
RE_NON_ARRIVE = r"\b(?:dnf|abd|abandon\w*|dsq|disqualifi\w*|hors delai\w*|non classe\w*)\b"
SEXE_MAP = {"h": "Homme", "m": "Homme", "homme": "Homme", "masculin": "Homme",
            "f": "Femme", "femme": "Femme", "feminin": "Femme"}

st.set_page_config(page_title=f"Statistiques - {NOM_EVENT}", page_icon="🌿", layout="wide")


# ----------------------------------------------------------------------------
# Utilitaires de base
# ----------------------------------------------------------------------------
def normaliser(t: str) -> str:
    """Minuscules, sans accents ni tirets : 'Hélène-Marie' -> 'helene marie'."""
    t = unicodedata.normalize("NFD", str(t)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _charger_asset(noms: tuple[str, ...]) -> bytes | None:
    """Fichier du dépôt en priorité (premier nom trouvé), sinon téléchargement si ASSETS_URL est défini."""
    for nom in noms:
        if (ASSETS / nom).exists():
            return (ASSETS / nom).read_bytes()
    if not ASSETS_URL:
        return None
    for nom in noms:
        try:
            req = urllib.request.Request(ASSETS_URL.rstrip("/") + "/" + nom, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.read()
        except Exception:
            continue
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def logo_event() -> bytes | None:
    return _charger_asset(("logo.webp", "logo.png"))


@st.cache_data(ttl=3600, show_spinner=False)
def fond_event() -> bytes | None:
    return _charger_asset(("fond.webp", "fond.jpg"))


def data_uri(b: bytes | None) -> str:
    if not b:
        return ""
    mime = "image/webp" if b[:4] == b"RIFF" else "image/png" if b[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


# ----------------------------------------------------------------------------
# Chargement des données
# ----------------------------------------------------------------------------
@st.cache_data
def charger() -> pd.DataFrame:
    df = pd.read_csv(DATA, dtype={"Dossard": "string"})
    df = df.rename(columns={"Prénom": "Prenom", "Sexe": "Sx", "Catégorie": "Cat"})

    for c in ("Nom", "Prenom", "Club", "Cat", "Statut", "Dossard", "Sx"):
        df[c] = df[c].fillna("").astype(str).str.strip()
    for c in ("Annee", "Classement", "Classement_Cat", "Temps_s", "Temps_reel_s"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Annee"]).copy()
    df["Annee"] = df["Annee"].astype(int)

    # Non-partants exclus ; abandons / disqualifiés conservés mais sans temps
    statut = df["Statut"].map(normaliser)
    df = df[~statut.str.contains(RE_NON_PARTANT, regex=True)].copy()
    statut = df["Statut"].map(normaliser)
    df.loc[statut.str.contains(RE_NON_ARRIVE, regex=True), ["Temps_s", "Temps_reel_s"]] = np.nan

    # Sexe normalisé en "Homme" / "Femme" (H, M, F, Masculin, Féminin... acceptés)
    df["Sx"] = df["Sx"].map(lambda s: SEXE_MAP.get(normaliser(s), s))

    # Catégorie suffixée par le sexe (M0H, SEF...) -> on retire le suffixe
    df["Cat"] = df["Cat"].str.replace(r"^(\w{2})[HFM]$", r"\1", regex=True)

    # Identité : "Nom" = "NOM Prénom" (clé d'affichage et d'agrégation), Nom_famille = nom seul
    df["Nom_famille"] = df["Nom"]
    df["Nom"] = (df["Nom_famille"] + " " + df["Prenom"]).str.strip()
    return df

ORDRE_CAT = ["CA", "JU", "ES", "SE"] + [f"M{i}" for i in range(10)]

@st.cache_data
def charger_statuts() -> pd.DataFrame:
    """Toutes les lignes du CSV, DNS compris, avec un statut simplifié FINISHER / DNF / DNS."""
    raw = pd.read_csv(DATA, dtype={"Dossard": "string"})
    raw["Annee"] = pd.to_numeric(raw["Annee"], errors="coerce")
    raw = raw.dropna(subset=["Annee"]).copy()
    raw["Annee"] = raw["Annee"].astype(int)
    s = raw["Statut"].fillna("").astype(str).map(normaliser)
    raw["Etat"] = np.select(
        [s.str.contains(RE_NON_PARTANT, regex=True), s.str.contains(RE_NON_ARRIVE, regex=True)],
        ["DNS", "DNF"], default="FINISHER",
    )
    raw["Sx"] = raw["Sexe"].fillna("").astype(str).map(lambda v: SEXE_MAP.get(normaliser(v), v.strip()))
    return raw[["Annee", "Etat", "Sx"]]

def pct_fr(v: float, d: int = 1) -> str:
    return "–" if pd.isna(v) else f"{v:.{d}f} %".replace(".", ",")

df = charger()
annees = sorted(df["Annee"].unique())
# 'NOM Prénom' -> (nom, prénom) exact, grâce aux colonnes séparées
NOMS = dict(zip(df["Nom"], zip(df["Nom_famille"], df["Prenom"])))

BG_IMG = f', url("{data_uri(fond_event())}") center / cover fixed no-repeat' if fond_event() else ""
LOGO_URI = data_uri(logo_event())

st.markdown(
    f"""
    <style>

    .stApp {{background:linear-gradient(rgba(1,114,132,.40),rgba(13,43,48,.60)){BG_IMG};
    background-attachment:fixed; background-color:{FOND};}}

    header[data-testid="stHeader"] {{background: transparent;}}
    [data-testid="stMainBlockContainer"], .stMainBlockContainer {{max-width: 100% !important;width: 90% !important;padding: 1rem 1rem 1rem !important;}}

    .stApp [data-testid="stCaptionContainer"],
    .stApp [data-testid="stCaptionContainer"] * {{color: rgba(255,255,255,.70);}}
    .stApp [data-testid="stWidgetLabel"] p {{color: white;font-weight: 600;}}

      /* Sélecteur d'édition : posé sur la ligne des onglets, à droite */
      .st-key-annees {{ display:none; flex-direction:column; align-items:flex-end; position:relative; z-index:5; margin-bottom:-4.68rem; pointer-events:none; }}
      .stApp:has(.stTabs [role="tab"][data-key="1"][aria-selected="true"]) .st-key-annees {{ display:flex; }}
      .st-key-annees * {{ pointer-events:none; }}
      .st-key-annees button, .st-key-annees [data-testid="stSelectbox"], .st-key-annees [data-testid="stSelectbox"] * {{ pointer-events:auto; }}
      .st-key-annees > [data-testid="stLayoutWrapper"] {{ width:250px; margin-left:auto; transform:translateY(14px); }}
      .st-key-annees [data-testid="stHorizontalBlock"] {{ width:100%; flex-wrap:nowrap; gap:6px; align-items:center; background:rgba(15,48,38,.55); backdrop-filter:blur(4px); border-radius:999px; padding:5px; }}

      .st-key-annees [data-testid="stColumn"] {{ min-width:0; }}
      .st-key-annees [data-testid="stButton"] button {{ width:36px; height:36px; min-height:36px; padding:0; border-radius:50% !important; background:rgba(255,255,255,.12) !important; border:0 !important; transition:all .18s ease; }}
      .st-key-annees [data-testid="stButton"] button * {{ color:#fff !important; font-size:1.3rem; font-weight:700; line-height:1; }}
      .st-key-annees [data-testid="stButton"] button:hover:not(:disabled) {{ background:#fff !important; }}
      .st-key-annees [data-testid="stButton"] button:hover:not(:disabled) * {{ color:{FOND} !important; }}
      .st-key-annees [data-testid="stButton"] button:disabled {{ opacity:.3; }}
      .st-key-annees [data-testid="stButton"] button:focus-visible {{ outline:2px solid {VERT}; outline-offset:2px; }}

      .st-key-annees [data-testid="stSelectbox"] [data-baseweb="select"] > div,
      .st-key-annees [data-testid="stSelectbox"] .react-aria-ComboBox > div {{ background:#fff !important; border:0 !important; border-radius:999px; min-height:36px; align-items:center; }}
      .st-key-annees [data-testid="stSelectbox"] * {{ color:{FOND} !important; font-weight:800; }}
      .st-key-annees [data-testid="stSelectbox"] button {{ background:transparent !important; box-shadow:none !important; border:0 !important; border-radius:0 !important; width:32px; height:100%; min-height:0; padding:0; display:flex; align-items:center; justify-content:center; }}

      @media (max-width:640px) {{
        .st-key-annees {{ margin-bottom:0; justify-content:flex-start; pointer-events:auto; }}
        .st-key-annees {{ align-items:flex-start; }}
        .st-key-annees > [data-testid="stLayoutWrapper"] {{ width:100%; transform:none; }}        .hero {{ flex-direction:column; align-items:flex-start; gap:10px; }}
        .hero .hero-logo {{ height:64px; }}
        .st-key-export_carte:has(button) {{ margin-bottom:0; align-items:flex-start; pointer-events:auto; }}
        .st-key-export_carte [data-testid="stElementContainer"] {{ transform:none; }}
        [data-testid="stLayoutWrapper"]:has(> .st-key-export_carte) {{ margin-bottom:0; }}
      }}

      .kpi-card {{ display:flex; align-items:center; gap:16px; background:#fff;
                   border:3px solid var(--c); border-radius:14px; padding:16px 20px;
                   box-shadow:0 8px 22px rgba(0,0,0,.28); font-family:'Poppins',sans-serif; }}
      .kpi-ico {{ flex:none; width:58px; height:58px; border-radius:50%; background:var(--c);
                  display:flex; align-items:center; justify-content:center; font-size:1.7rem;
                  box-shadow:0 3px 8px rgba(0,0,0,.25); }}
      .kpi-lab {{ color:#6b6b6b; font-size:.72rem; font-weight:600; letter-spacing:.06em;
                  text-transform:uppercase; }}
      .kpi-val {{ color:#0e3610; font-size:2.1rem; font-weight:800; line-height:1.1; }}
      .kpi-moy {{ color:#6b6b6b; font-size:.8rem; margin-top:2px; }}
      .kpi-moy b {{ color:#0e3610; font-weight:800; font-size:.95rem; padding-left:4px; }}

      .hero {{ font-family:'Poppins',sans-serif; margin:6px 0 18px 0; display:flex; align-items:center; gap:20px; }}
      .hero .hero-logo {{ height:84px; width:auto; flex:none; filter:drop-shadow(0 2px 10px rgba(0,0,0,.35)); }}

      .hero .kicker {{ color:#fff; font-size:.78rem; font-weight:600; letter-spacing:.22em;
                       text-transform:uppercase; display:flex; align-items:center; gap:10px; }}
      .hero .h {{ color:#fff; font-size:2.5rem; font-weight:800; line-height:1.1; margin-top:6px;
                  text-shadow:0 2px 14px rgba(0,0,0,.45); }}
      .hero .h span {{ color:{VERT}; }}

      /* ---------- Cartes d'en-tête (evol, distrib, classement) ---------- */
        :is({HEADS}) {{
            background: rgba(15,48,38,.92); backdrop-filter: blur(4px);
            border-radius: 12px 12px 0 0; padding: 10px 16px 15px 16px;
            margin-bottom: -1rem; box-shadow: inset 0 -3px 0 #fff; gap: 0;
        }}
        :is({HEADS}) .titre {{
            background: none !important; box-shadow: none !important;
            backdrop-filter: none !important; border: 0 !important;
            padding: 0; border-radius: 0; width: fit-content;
        }}
        :is({HEADS}) .titre::before,
        :is({HEADS}) .titre::after {{ display: none !important; }}

        /* ---------- Titre + icône d'aide collée ---------- */
        :is({HEADS}) [data-testid="stMarkdown"] {{
            display: flex !important; flex-direction: row;
            align-items: flex-start; justify-content: flex-start !important; gap: 0;
        }}
        :is({HEADS}) [data-testid="stMarkdownContainer"] {{
            flex: 0 1 auto !important; width: auto !important;
        }}
        :is({HEADS}) [data-testid="stTooltipIcon"] {{
            margin: 8px 0 0 10px !important; position: static !important; flex: 0 0 auto;
        }}

        /* ---------- Contrôle segmenté (colonne de droite) ---------- */
        :is({HEADS}) [data-testid="stHorizontalBlock"] {{ align-items: center; }}
        :is({HEADS}) [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{
            width: 100%; display: flex; justify-content: flex-end;
        }}
        :is({HEADS}) [data-testid="stButtonGroup"] {{ background: transparent; width: fit-content; }}
        :is({HEADS}) [role="radiogroup"] {{
            background: rgba(255,255,255,.08); border-radius: 999px; padding: 4px; gap: 4px;
            width: fit-content; border: 1px solid rgba(255,255,255,.15);
        }}
        :is({HEADS}) button[role="radio"] {{
            background: transparent !important; border: 0 !important;
            border-radius: 999px !important; padding: 5px 16px;
        }}
        :is({HEADS}) button[role="radio"] * {{ color: rgba(255,255,255,.75) !important; font-weight: 600; }}
        :is({HEADS}) button[role="radio"]:hover * {{ color: #fff !important; }}
        :is({HEADS}) button[role="radio"][aria-checked="true"] {{ background: #fff !important; }}
        :is({HEADS}) button[role="radio"][aria-checked="true"] * {{ color: {FOND} !important; font-weight: 700; }}

      /* --- carte verre --- */
      .st-key-perf {{
            background:linear-gradient(180deg, rgba(15,48,38,.62), rgba(15,43,48,.36));
            backdrop-filter:blur(4px); border-radius:14px; border:1px solid rgba(255,255,255,.14);
            box-shadow:0 10px 30px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.08);
            gap:0 !important; padding:0 0 15px 0; }}
      .st-key-perf_head {{ background:rgba(15,48,38,.92); border-radius:14px 14px 0 0;
            padding:12px 20px 16px 20px; margin:0; box-shadow:inset 0 -3px 0 #fff; }}
      .st-key-perf_head .titre {{ background:none; box-shadow:none; backdrop-filter:none; padding:0; border-radius:0; }}

      /* corps : respiration autour du graphique et du tableau */
      .st-key-perf [data-testid="stHorizontalBlock"]:not(.st-key-perf_head *) {{
            padding:1px 20px 0 20px; align-items:center; }}

      /* graphique transparent */
      .st-key-perf [data-testid="stPlotlyChart"], .st-key-perf [data-testid="stPlotlyChart"] .js-plotly-plot,
      .st-key-perf [data-testid="stPlotlyChart"] .plot-container, .st-key-perf [data-testid="stPlotlyChart"] .main-svg {{
            background:transparent !important; }}
      .st-key-perf [data-testid="stPlotlyChart"] .main-svg .bg {{ fill:transparent !important; }}

      /* tableau en verre */
      .st-key-perf .perf-wrap {{ max-height:380px; overflow-y:auto; padding-right:4px;
            scrollbar-width:thin; scrollbar-color:rgba(255,255,255,.3) transparent; }}
      .st-key-perf .perf-table {{ width:100%; border-collapse:separate !important; border-spacing:0 6px;
            font-size:.92rem; color:#fff; margin:0; }}
      .st-key-perf .perf-table th {{ border:0 !important; background:transparent !important; text-align:left;
            font-size:.68rem; letter-spacing:.09em; text-transform:uppercase; font-weight:600;
            color:rgba(255,255,255,.55); padding:0 12px 2px 12px; position:sticky; top:0; }}
      .st-key-perf .perf-table td {{ border:0 !important; background:rgba(255,255,255,.07) !important;
            padding:9px 12px; transition:background .15s; }}
      .st-key-perf .perf-table td:first-child {{ border-radius:10px 0 0 10px; font-weight:700; }}
      .st-key-perf .perf-table td:last-child  {{ border-radius:0 10px 10px 0; text-align:center; }}
      .st-key-perf .perf-table tr:hover td {{ background:rgba(255,255,255,.14) !important; }}
      .st-key-perf .perf-table .t {{ font-variant-numeric:tabular-nums; font-weight:700; }}
      .st-key-perf .perf-table tr.best td {{ background:rgba(255,193,7,.17) !important; }}
      .st-key-perf .perf-table tr.best td:first-child {{ box-shadow:inset 3px 0 0 #FFC107; }}
      .st-key-perf .perf-table tr.dnf td {{ color:rgba(255,255,255,.5); font-style:italic; }}

      .st-key-evol, .st-key-evol_pct, .st-key-evol_pct_an {{ background:rgba(15,48,38,.62); backdrop-filter:blur(4px);
            border-radius:0 0 12px 12px; padding:10px 14px 6px 14px; }}
      .st-key-evol div[data-testid="stPlotlyChart"],
      .st-key-evol_pct div[data-testid="stPlotlyChart"],
      .st-key-evol_pct_an div[data-testid="stPlotlyChart"] {{ background:transparent; border-radius:0; }}

      .st-key-distrib {{ background:rgba(15,48,38,.62); backdrop-filter:blur(4px);
            border-radius:0 0 12px 12px; padding:10px 14px 6px 14px; margin-top:0; }}
      .st-key-distrib div[data-testid="stPlotlyChart"] {{ background:transparent; border-radius:0; }}

      .st-key-pills_cat button[role="radio"] {{ background:rgba(15,48,38,.55) !important;
            border:1px solid rgba(255,255,255,.28) !important; border-radius:999px !important;
            backdrop-filter:blur(4px); transition:all .15s ease; }}
      .st-key-pills_cat button[role="radio"] * {{ color:rgba(255,255,255,.85) !important; }}
      .st-key-pills_cat button[role="radio"]:hover {{ border-color:rgba(255,255,255,.7) !important;
            background:rgba(255,255,255,.12) !important; }}
      .st-key-pills_cat button[role="radio"][aria-checked="true"] {{
            background:rgba(255,255,255,.22) !important; border:1px solid #fff !important; }}
      .st-key-pills_cat button[role="radio"][aria-checked="true"] * {{ color:#fff !important; font-weight:700; }}

        /* l'icône ? elle-même */
        [data-testid="stTooltipIcon"] svg {{fill: {VERT} !important;}}
        [data-testid="stTooltipIcon"]:hover svg {{fill: {FOND} !important;}}

        /* st.markdown(help=...) : titre + icône sur une même ligne, icône collée */
        .st-key-evol_head [data-testid="stMarkdown"],
        .st-key-classement_head [data-testid="stMarkdown"],
        .st-key-suivi ~ div [data-testid="stMarkdown"] {{
            display: flex !important;
            flex-direction: row;
            align-items: flex-start;
            justify-content: flex-start !important;
            gap: 0;
        }}
        .st-key-evol_head [data-testid="stMarkdownContainer"],
        .st-key-classement_head [data-testid="stMarkdownContainer"],
        .st-key-suivi ~ div [data-testid="stMarkdownContainer"] {{
            flex: 0 1 auto !important;
            width: auto !important;
        }}
        .st-key-evol_head [data-testid="stTooltipIcon"],
        .st-key-classement_head [data-testid="stTooltipIcon"],
        .st-key-suivi ~ div [data-testid="stTooltipIcon"] {{
            margin: 8px 0 0 10px !important;   /* 8px = alignement vertical sur la ligne du titre */
            position: static !important;
            flex: 0 0 auto;
        }}

      .titre {{ display:flex; align-items:center; gap:12px; background:rgba(15,48,38,.92);
                backdrop-filter:blur(4px); border-radius:12px 12px 0 0; padding:9px 16px;
                box-shadow:inset 0 -3px 0 var(--c); font-family:'Poppins',sans-serif; }}
      .titre .ico {{ flex:none; width:32px; height:32px; border-radius:50%; background:var(--c);
                     display:flex; align-items:center; justify-content:center; font-size:1.25rem;
                     line-height:1; color:#fff; font-weight:700; box-shadow:0 2px 6px rgba(0,0,0,.3); }}
                     .titre.graph .ico {{ background:#fff; }}
      .titre .tt {{ color:#fff; font-size:1rem; font-weight:700; letter-spacing:.02em; }}
      .titre .ss {{ color:rgba(255,255,255,.6); font-size:.72rem; font-weight:400; margin-top:-1px; }}
      .titre .chip {{ margin-left:auto; color:#fff; font-size:.72rem; font-weight:600;
                      padding:3px 12px; border-radius:999px; background:rgba(255,255,255,.1);
                      border:1px solid rgba(255,255,255,.22); white-space:nowrap; }}
      .titre.graph {{ box-shadow:inset 0 -3px 0 #fff; }}
      .st-key-evol_head .titre.graph, .st-key-distrib_head .titre.graph {{ box-shadow:none; }}

      .pod-wrap {{ display:flex; align-items:flex-end; gap:14px; padding:22px 14px 16px 14px;
                   background:rgba(15,48,38,.62); backdrop-filter:blur(4px);
                   border-radius:0 0 10px 10px; min-height:340px; box-sizing:border-box;
                   font-family:'Poppins',sans-serif; }}
      .pod-vide {{ justify-content:center; align-items:center; color:rgba(255,255,255,.8); }}
      .pod-col {{ flex:1; display:flex; flex-direction:column; gap:14px; min-width:0; }}
      .pod-card {{ background:#fff; border:3px solid var(--c); border-radius:14px;
                   padding:16px 8px 10px 8px; text-align:center; box-sizing:border-box; overflow:hidden;
                   display:flex; flex-direction:column; justify-content:flex-start;
                   box-shadow:0 8px 22px rgba(0,0,0,.28); }}
      .pod-card.p1 {{ height:300px; padding-top:22px; box-shadow:0 12px 30px rgba(0,0,0,.38); }}
      .pod-card.p2 {{ height:262px; }}
      .pod-card.p3 {{ height:224px; }}
      .pod-medal {{ flex:none; width:58px; height:58px; margin:0 auto 10px auto; border-radius:50%;
                    background:var(--c); display:flex; align-items:center; justify-content:center;
                    box-shadow:0 3px 8px rgba(0,0,0,.25); }}
      .pod-card.p1 .pod-medal {{ width:78px; height:78px; }}
      .pod-nom {{ color:#0e3610; font-weight:800; font-style:italic; text-transform:uppercase;
                  font-size:.88rem; line-height:1.15; overflow-wrap:anywhere;
                  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
      .pod-card.p1 .pod-nom {{ font-size:1rem; }}
      .pod-club {{ color:#6b6b6b; font-size:.68rem; text-transform:uppercase; margin-top:6px;
                   line-height:1.2; overflow-wrap:anywhere;
                   display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
      .pod-meta {{ color:#6b6b6b; font-size:.75rem; margin-top:4px; }}
      .pod-meta i {{ color:{VERT}; font-style:normal; font-weight:600; padding:0 2px; }}
      .pod-temps {{ color:#0e3610; font-weight:800; font-size:1.25rem; margin-top:10px; }}
      .pod-card.p1 .pod-temps {{ font-size:1.5rem; }}
      div[data-testid="stPlotlyChart"] {{ background:white; border-radius:0 0 10px 10px; }}

      .stTabs [role="tablist"] {{ gap:6px; background:rgba(15,48,38,.55); backdrop-filter:blur(4px);
                                 border-radius:999px; padding:5px; width:fit-content; border:0 !important;
                                 box-shadow:none !important; }}
      .stTabs [role="tablist"]::after, .stTabs [role="tablist"]::before,
      .stTabs .react-aria-SelectionIndicator, .stTabs [data-baseweb="tab-highlight"],
      .stTabs [data-baseweb="tab-border"] {{ display:none !important; }}
      .stTabs [role="tab"] {{ border-radius:999px; padding:6px 20px; height:auto; background:transparent;
                             border:0 !important; }}
      .stTabs [role="tab"] p {{ color:rgba(255,255,255,.75) !important; font-weight:600; font-size:.95rem; }}
      .stTabs [role="tab"]:hover p {{ color:#fff !important; }}
      .stTabs [role="tab"][aria-selected="true"] {{ background:#fff; }}
      .stTabs [role="tab"][aria-selected="true"] p {{ color:{FOND} !important; font-weight:700; }}

      .st-key-suivi {{ background:rgba(15,48,38,.62); backdrop-filter:blur(4px);
                       border-radius:0 0 10px 10px; padding:6px 14px 10px 14px; }}
      .st-key-suivi div[data-testid="stPlotlyChart"] {{ background:transparent; border-radius:0; }}
      .st-key-recherche, .st-key-recherche_choix {{ background:rgba(15,48,38,.62); backdrop-filter:blur(4px);
                                                  border-radius:12px; padding:14px 18px 6px 18px; }}
      .st-key-recherche input {{ background:#fff; color:#0e3610; }}

      .fiche {{ font-family:'Poppins',sans-serif; color:#fff; margin:4px 0 2px 0; text-align:center; }}
      .fiche .n {{ font-size:1.5rem; font-weight:800; font-style:italic; text-transform:uppercase; line-height:1.1; }}
      .fiche .m {{ color:rgba(255,255,255,.7); font-size:.85rem; margin-top:2px; }}

      .kpi-det {{ color:#6b6b6b; font-size:.8rem; margin-top:2px; }}
      .kpi-det b {{ color:#0e3610; font-weight:800; }}

      .st-key-export_carte:has(button) {{ display:flex; flex-direction:column; align-items:flex-end; position:relative;z-index:5; margin-bottom:-4.68rem; pointer-events:none; }}
      [data-testid="stLayoutWrapper"]:has(> .st-key-export_carte) {{ margin-bottom:-1rem; }}
      .st-key-export_carte [data-testid="stElementContainer"] {{ width:fit-content; transform:translateY(3px); }}
      .st-key-export_carte button, .st-key-export_carte button * {{ pointer-events:auto; }}
      .st-key-dl_carte button {{ background:#fff; border:0; border-radius:999px; padding:9px 20px;box-shadow:0 4px 14px rgba(0,0,0,.25); }}
      .st-key-dl_carte button p {{ color:{FOND}; font-weight:700; }}
      .st-key-dl_carte button:hover {{ background:#eef3f4; }}

      /* Bouton d'export : caché par défaut, visible uniquement sur "Individuel" (3e onglet, data-key="2") */
      .st-key-export_carte {{ display:none !important; }}
      .stApp:has(.stTabs [role="tab"][data-key="2"][aria-selected="true"]) .st-key-export_carte {{ display:flex !important; }}

    </style>
    """,
    unsafe_allow_html=True,
)

_logo_html = f"<img class='hero-logo' src='{LOGO_URI}' alt='Logo {escape(NOM_EVENT)}'>" if LOGO_URI else ""
st.markdown(
    "<div class='hero'>"
    + _logo_html +
    "<div class='hero-txt'>"
    "<div class='kicker'>Statistiques chronométriques</div>"
    "<div class='h'>Le Marathon Vert Rennes</div>"
    "</div></div>",
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Helpers d'affichage
# ----------------------------------------------------------------------------
def hms(s: float) -> str:
    if pd.isna(s):
        return "–"
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


ICO_F = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="9" r="5.5"/><path d="M12 14.5V22M8.5 18.5h7"/></svg>'
ICO_H = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="14" r="5.5"/><path d="M14 10l6-6M14.5 4H20v5.5"/></svg>'


def titre(icone: str, texte: str, sous: str = "", puce: str = "", couleur: str = VERT, graph: bool = False) -> str:
    """graph=True : bandeau d'un graphique (sans chip, bordure blanche)."""
    sous_html = f"<div class='ss'>{sous}</div>" if sous else ""
    puce_html = f"<span class='chip'>{puce}</span>" if puce and not graph else ""
    return (
        f"<div class='titre{' graph' if graph else ''}' style='--c:{couleur}'><div class='ico'>{icone}</div>"
        f"<div><div class='tt'>{texte}</div>{sous_html}</div>{puce_html}</div>"
    )


MEDAILLE = (
    '<svg width="{t}" height="{t}" viewBox="0 0 24 24" fill="none" stroke="white" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M7.2 3h9.6l1.4 5H5.8z"/><circle cx="12" cy="14.5" r="5.5"/>'
    '<path d="M12 11.7l.9 1.8 2 .3-1.45 1.4.35 2-1.8-.95-1.8.95.35-2L9.1 13.8l2-.3z"/></svg>'
)


def split_nom(nom: str) -> tuple[str, str]:
    """'EL OUARDI Hamza' -> ('EL OUARDI', 'Hamza') : lecture exacte via les colonnes Nom / Prénom."""
    if nom in NOMS:
        n, p = NOMS[nom]
        return n or nom, p
    # repli heuristique si le nom est inconnu du jeu de données
    mots = str(nom).split()
    i = 0
    while i < len(mots) - 1 and mots[i].replace("-", "").replace("'", "").isupper():
        i += 1
    return " ".join(mots[:i]) or nom, " ".join(mots[i:])


def carte(r, place: int, couleur: str) -> str:
    nom, prenom = split_nom(r.Nom)
    club = f"<div class='pod-club'>{escape(r.Club)}</div>" if r.Club else ""
    cat = f"<i>/</i> {r.Cat}" if r.Cat else ""
    return (
        f"<div class='pod-card p{place}' style='--c:{couleur}'>"
        f"<div class='pod-medal'>{MEDAILLE.format(t=40 if place == 1 else 30)}</div>"
        f"<div class='pod-nom'>{escape(prenom)} {escape(nom)}</div>{club}"
        f"<div class='pod-meta'>{r.Sx} {cat}</div>"
        f"<div class='pod-temps'>{hms(r.Temps_s)}</div></div>"
    )


def podium(d: pd.DataFrame, sexe: str) -> str:
    s = d[(d["Sx"] == sexe) & d["Temps_s"].notna()].copy()
    s["Place"] = s["Temps_s"].rank(method="dense")  # ex æquo = même place
    s = s[s["Place"] <= 3].sort_values(["Place", "Nom"])
    couleurs = {1: OR, 2: ARGENT, 3: BRONZE}
    if s.empty:
        return "<div class='pod-wrap pod-vide'>Aucun arrivant dans cette catégorie</div>"
    cols = {}
    for place in (1, 2, 3):
        cartes = "".join(carte(r, place, couleurs[place]) for r in s[s["Place"] == place].itertuples())
        cols[place] = f"<div class='pod-col'>{cartes}</div>"
    return f"<div class='pod-wrap'>{cols[2]}{cols[1]}{cols[3]}</div>"


def densite(t: pd.Series, grille: np.ndarray, bw: float) -> np.ndarray:
    """Estimation de densité gaussienne, exprimée en coureurs par minute."""
    t = t.dropna().to_numpy()
    if len(t) == 0:
        return np.zeros_like(grille)
    z = (grille[:, None] - t[None, :]) / bw
    return np.exp(-0.5 * z**2).sum(axis=1) / (bw * np.sqrt(2 * np.pi)) * 60


MEDAILLES_RANG = {1: "🥇", 2: "🥈", 3: "🥉"}


def nom_affiche(n: str) -> str:
    """'NOM Prénom' → 'Prénom Nom' (échappé pour le HTML)."""
    try:
        nom, prenom = split_nom(n)
        return escape(f"{prenom} {nom}".strip())
    except Exception:
        return escape(str(n))


def sx_html(s: str) -> str:
    return {"Homme": "<span class='sx-h'>♂ H</span>",
            "Femme": "<span class='sx-f'>♀ F</span>"}.get(s, escape(str(s)))


def rang_txt(v) -> str:
    return "" if pd.isna(v) else f"{int(v)}e"


# ----------------------------------------------- Sélecteur d'édition
with st.container(key="annees"):
    st.session_state.setdefault("annee_sel", annees[-1])

    def _aller(delta: int) -> None:
        i = annees.index(st.session_state["annee_sel"]) + delta
        st.session_state["annee_sel"] = annees[min(max(i, 0), len(annees) - 1)]

    c_prec, c_choix, c_suiv = st.columns([1, 3.2, 1], vertical_alignment="center")
    c_prec.button("‹", key="annee_prec", on_click=_aller, args=(-1,),
                  disabled=st.session_state["annee_sel"] == annees[0])
    annee = c_choix.selectbox("Édition", annees[::-1], key="annee_sel",
                              label_visibility="collapsed")
    c_suiv.button("›", key="annee_suiv", on_click=_aller, args=(1,),
                  disabled=st.session_state["annee_sel"] == annees[-1])
# --------------------------------------------------------------

zone_export = st.container(key="export_carte")
tab_stats, tab_edition, tab_coureur = st.tabs(["📊 Général", "👟 Edition", "🏃 Individuel"])

# --------------------------------------------------------------------------------
# Onglet 1 : vue générale
# --------------------------------------------------------------------------------
with tab_stats:

    ANNEE_RECORD_ABS = int(annees[0])   # records calculés à partir de cette édition (à modifier si besoin)

    # ----------------------------------------------------------------------------
    # KPI des participations F/H + records
    # ----------------------------------------------------------------------------

    # Sexe de référence par coureur = sexe le plus fréquent (mode) sur ses éditions
    sexe_ref = (
        df.groupby(["Nom", "Sx"]).size().reset_index(name="n")
        .sort_values(["Nom", "n"], ascending=[True, False])
        .drop_duplicates("Nom").set_index("Nom")["Sx"].rename("Sx_ref")
    )

    # Nombre d'éditions distinctes par coureur (indépendamment du sexe déclaré)
    nb_editions = df.groupby("Nom")["Annee"].nunique().rename("Nb_editions")

    # Tableau de synthèse : un coureur = une ligne
    coureurs = (
        pd.concat([nb_editions, sexe_ref], axis=1)
        .reset_index()
        .sort_values("Nb_editions", ascending=False)
    )

    # KPI : leader toutes catégories confondues
    top = coureurs.iloc[0] if len(coureurs) else None

    # Podiums par sexe
    partic_f = coureurs[coureurs["Sx_ref"] == "Femme"].nlargest(3, "Nb_editions")
    partic_h = coureurs[coureurs["Sx_ref"] == "Homme"].nlargest(3, "Nb_editions")

    # --- Records absolus ---
    arr_records = df[(df["Annee"] >= ANNEE_RECORD_ABS) & df["Temps_s"].notna()]

    best_f = arr_records[arr_records["Sx"] == "Femme"].nsmallest(1, "Temps_s")
    best_h = arr_records[arr_records["Sx"] == "Homme"].nsmallest(1, "Temps_s")

    # --- Participations : TOUTES éditions ---
    top_partic_nom = top["Nom"] if top is not None else None
    top_partic_nb = int(top["Nb_editions"]) if top is not None else 0

    # ----------------------------------------------------------------------------
    # Affichage des KPI
    # ----------------------------------------------------------------------------
    def kpi_record(col, icone, label, valeur, sous, couleur):
        """KPI 'record' : valeur principale + sous-texte (nom / contexte)."""
        col.markdown(
            f"<div class='kpi-card' style='--c:{couleur}'>"
            f"<div class='kpi-ico'>{icone}</div>"
            f"<div><div class='kpi-lab'>{label}</div>"
            f"<div class='kpi-val'>{valeur}</div>"
            f"<div class='kpi-moy'>{sous}</div></div></div>",
            unsafe_allow_html=True,
        )

    k1, k3, k2 = st.columns(3)

    # Meilleur temps féminin
    if not best_f.empty:
        r = best_f.iloc[0]
        nom, prenom = split_nom(r.Nom)
        kpi_record(k1, "🏆", "Record féminin", hms(r.Temps_s),
                   f"{escape(prenom)} {escape(nom)} · {int(r.Annee)}", VERT)
    else:
        kpi_record(k1, "🏆", "Record féminin", "–", f"Aucune donnée depuis {ANNEE_RECORD_ABS}", VERT)

    # Meilleur temps masculin
    if not best_h.empty:
        r = best_h.iloc[0]
        nom, prenom = split_nom(r.Nom)
        kpi_record(k2, "🏆", "Record masculin", hms(r.Temps_s),
                   f"{escape(prenom)} {escape(nom)} · {int(r.Annee)}", ROUGE)
    else:
        kpi_record(k2, "🏆", "Record masculin", "–", f"Aucune donnée depuis {ANNEE_RECORD_ABS}", ROUGE)

    # Plus de participations (toutes éditions)
    if top_partic_nom:
        nom, prenom = split_nom(top_partic_nom)
        kpi_record(k3, "🎖️", "Plus de participations", f"{top_partic_nb}",
                   f"{escape(prenom)} {escape(nom)}", FOND)
    else:
        kpi_record(k3, "🎖️", "Plus de participations", "–", "Aucune donnée", FOND)

    st.write("")

    # ----------------------------------------------------------------------------
    # Podiums des participations F/H
    # ----------------------------------------------------------------------------
    def carte_participation(r, place: int, couleur: str) -> str:
        """Carte podium pour un coureur classé par nombre d'éditions."""
        nom, prenom = split_nom(r.Nom)
        return (
            f"<div class='pod-card p{place}' style='--c:{couleur}'>"
            f"<div class='pod-medal'>{MEDAILLE.format(t=40 if place == 1 else 30)}</div>"
            f"<div class='pod-nom'>{escape(prenom)} {escape(nom)}</div>"
            f"<div class='pod-meta'>{r.Sx_ref}</div>"
            f"<div class='pod-temps'>{int(r.Nb_editions)} éditions</div></div>"
        )

    def podium_participations(data: pd.DataFrame) -> str:
        """Podium à partir d'un DataFrame trié décroissant sur Nb_editions."""
        couleurs = {1: OR, 2: ARGENT, 3: BRONZE}
        if data.empty:
            return "<div class='pod-wrap pod-vide'>Aucune donnée</div>"
        cols = {}
        for place in (1, 2, 3):
            if place > len(data):
                cols[place] = "<div class='pod-col'></div>"
                continue
            r = data.iloc[place - 1]
            cols[place] = f"<div class='pod-col'>{carte_participation(r, place, couleurs[place])}</div>"
        return f"<div class='pod-wrap'>{cols[2]}{cols[1]}{cols[3]}</div>"

    p1, p2 = st.columns(2)
    for col, libelle, ico, coul, data in (
        (p1, "Participations Femmes", ICO_F, VERT, partic_f),
        (p2, "Participations Hommes", ICO_H, ROUGE, partic_h),
    ):
        col.markdown(
            titre(ico, libelle, "Toutes éditions", "Nombre d'éditions", coul),
            unsafe_allow_html=True,
        )
        col.markdown(podium_participations(data), unsafe_allow_html=True)

    # ----------------------------------------------------------------------------
    # Préparation des tranches de temps (partagée par les graphiques de densité)
    # ----------------------------------------------------------------------------
    def fmt_h(m: int) -> str:
        return f"{m // 60}h{m % 60:02d}"

    bornes = list(range(TRANCHE_DEBUT, TRANCHE_FIN + 1, TRANCHE_PAS))
    etiquettes = (
        [f"< {fmt_h(bornes[0])}"]
        + [f"{fmt_h(a)} – {fmt_h(b)}" for a, b in zip(bornes[:-1], bornes[1:])]
        + [f"≥ {fmt_h(bornes[-1])}"]
    )
    PALETTE_TRANCHES = ["#2A8F9B", "#3AB5B0", "#6CC9A0", "#A8D67E", "#E6D45F", "#F2A94E",
                        "#E8743B", "#C24247", "#8E3B6B", "#5B3A7A"]  # du plus rapide (bas) au plus lent (haut)

    st.write("")
    sel = df[df["Temps_s"].notna()].copy()          # toutes éditions, toutes catégories
    sel["Tranche"] = pd.cut(
        sel["Temps_s"] / 60, bins=[-float("inf")] + bornes + [float("inf")],
        labels=etiquettes, right=False,
    )

    # ----------------------------------------------------------------------------
    # Graphiques : évolution du nombre de coureurs / densité par tranche de performance
    # ----------------------------------------------------------------------------
    with st.container(key="evol_head"):
 
        info_caption1 = (
            f"**Éditions {annees[0]} à {annees[-1]}**  \n"
            "Temps officiel  \n"
            "Abandons exclus des moyennes et distributions  \n"
            "Non-partants exclus des effectifs"
        )
        info_caption_nb = (
            f"**Éditions {annees[0]} à {annees[-1]}**  \n"
            "**FINISHER** : a rallié l'arrivée  \n"
            "**DNF** : parti mais pas classé (abandon, disqualification, hors délai)  \n"
            "**DNS** : inscrit mais non-partant  \n"
            "Courbe dorée : temps moyen des arrivants (temps officiel)"
        )
        c_titre, c_vue = st.columns([3, 1], vertical_alignment="center")
        with c_vue:
            vue = st.segmented_control(
                "Graphique", ["Nombre", "Densité"], default="Nombre",
                key="vue_evol", label_visibility="collapsed",
            ) or "Nombre"
 
        if vue == "Nombre":
            n_inscrits = len(charger_statuts())
            c_titre.markdown(
                titre("🚦", "Évolution du nombre de coureurs",
                      f"Éditions {annees[0]} à {annees[-1]} · par statut",
                      f"{n_inscrits:,} inscrits".replace(",", " "), graph=True),
                unsafe_allow_html=True, help=info_caption_nb,
            )
        else:
            c_titre.markdown(
                titre("🔎", "Évolution de la densité des coureurs",
                      f"Part des arrivants par tranche de {TRANCHE_PAS} min",
                      "Toutes catégories", graph=True),
                unsafe_allow_html=True, help=info_caption1,
            )
 
    if vue == "Nombre":
        with st.container(key="evol"):
            stt_ev = charger_statuts()
            ETATS_E = ["FINISHER", "DNF", "DNS"]
            LIB_E = {"FINISHER": "Finishers", "DNF": "Abandons (DNF)", "DNS": "Non-partants (DNS)"}
            COUL_E = {"FINISHER": OR, "DNF": BRONZE, "DNS": ARGENT}

            c_ev = (stt_ev.groupby(["Annee", "Etat"]).size().unstack(fill_value=0)
                    .reindex(columns=ETATS_E, fill_value=0))
            c_ev["Inscrits"] = c_ev[ETATS_E].sum(axis=1)
            x = [str(a) for a in c_ev.index]
            nf = lambda n: f"{int(n):,}".replace(",", " ")

            fig = go.Figure()
            seuil = c_ev["Inscrits"].max() * 0.045
            for e in ETATS_E:
                if c_ev[e].sum() == 0:
                    continue
                part_e = (c_ev[e] / c_ev["Inscrits"].replace(0, np.nan) * 100).fillna(0)
                fig.add_trace(go.Bar(
                    x=x, y=c_ev[e].values, name=LIB_E[e],
                    marker=dict(color=COUL_E[e], line=dict(color="rgba(15,43,48,.9)", width=1)),
                    text=[nf(v) if v >= seuil else "" for v in c_ev[e].values],
                    textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="white" if e == "DNF" else "#0F2B30", size=12),
                    customdata=part_e.values,
                    # une ligne par statut dans la bulle unifiée
                    hovertemplate=f"<b>{LIB_E[e]}</b> : %{{y:,.0f}} · %{{customdata:.1f}} %<extra></extra>",
                ))
            # Total au-dessus de chaque barre (aussi affiché dans la bulle de survol)
            fig.add_trace(go.Scatter(
                x=x, y=c_ev["Inscrits"].values, mode="text", name="Inscrits", showlegend=False,
                text=[nf(v) for v in c_ev["Inscrits"]],
                textposition="top center", textfont=dict(color="white", size=14),
                hovertemplate="<b>Inscrits</b> : %{y:,.0f}<extra></extra>",
            ))

            # Temps moyen par édition (arrivants avec temps), superposé sur un axe de droite masqué
            moy = (df[df["Temps_s"].notna()].groupby("Annee")["Temps_s"].mean()
                   .reindex(c_ev.index))
            moy_ok = moy.dropna()
            y_max = c_ev["Inscrits"].max() * 1.15
            y2 = None
            if not moy_ok.empty:
                fig.add_trace(go.Scatter(
                    x=[str(a) for a in moy_ok.index], y=moy_ok.values, yaxis="y2",
                    mode="lines+markers+text", name="Temps moyen",
                    line=dict(color=OR, width=3),
                    marker=dict(size=10, color=OR, line=dict(color="white", width=2)),
                    text=[hms(v) for v in moy_ok.values], textposition="top center",
                    textfont=dict(color=OR, size=12), cliponaxis=False,
                    customdata=[hms(v) for v in moy_ok.values],
                    hovertemplate="<b>Temps moyen</b> : %{customdata}<extra></extra>",
                    showlegend=False,
                ))
                pas_m = 600
                m_lo = int(moy_ok.min() // pas_m * pas_m) - pas_m
                m_hi = int(-(-moy_ok.max() // pas_m) * pas_m) + pas_m
                # barres dans la moitié basse, courbe dans le tiers haut du graphique
                m_lo -= 2 * (m_hi - m_lo)
                y_max = c_ev["Inscrits"].max() / 0.62
                y2 = dict(overlaying="y", side="right", showgrid=False, zeroline=False,
                          showticklabels=False, range=[m_lo, m_hi])

            fig.update_layout(
                barmode="stack", height=400, margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                legend=dict(orientation="h", y=-0.06, x=0.5, xanchor="center", yanchor="top",
                            font=dict(color="white")),
                xaxis=dict(type="category", showgrid=False, color="white"),
                yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0, y_max]),
                bargap=0.35,
                hovermode="x unified",   # <- les 3 statuts + total + temps moyen d'un coup d'œil
                hoverlabel=dict(bgcolor="rgba(15,43,48,.95)", bordercolor="rgba(255,255,255,.25)",
                                font=dict(color="white", size=13)),
                **({"yaxis2": y2} if y2 else {}),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        with st.container(key="evol_pct"):
            comptes = sel.groupby(["Annee", "Tranche"], observed=False).size().unstack(fill_value=0)
            totaux = comptes.sum(axis=1).replace(0, 1)
            pct = comptes.div(totaux, axis=0) * 100
            x = [str(a) for a in comptes.index]

            fig = go.Figure()
            for k, lab in enumerate(etiquettes):
                fig.add_trace(go.Bar(
                    x=x, y=pct[lab], name=lab,
                    marker=dict(color=PALETTE_TRANCHES[k % len(PALETTE_TRANCHES)],
                                line=dict(color="rgba(15,43,48,.9)", width=1)),
                    text=[f"{v:.0f}%" if v >= 5 else "" for v in pct[lab]],
                    textposition="inside", insidetextanchor="middle", textangle=0,
                    textfont=dict(color="#0F2B30" if 2 <= k <= 5 else "white", size=12),
                    customdata=comptes[lab],
                    hovertemplate=f"{lab}<br>%{{y:.1f}} % · %{{customdata}} coureurs<extra></extra>",
                ))
            fig.update_layout(
                barmode="stack", height=460, margin=dict(l=10, r=10, t=10, b=10), bargap=0.25,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"),
                legend=dict(traceorder="reversed", font=dict(color="white")),
                xaxis=dict(type="category", showgrid=False, color="white"),
                yaxis=dict(range=[0, 100], ticksuffix=" %", showgrid=False, zeroline=False, color="white"),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ----------------------------------------------------------------------------
    # Classement des individus par participations (toutes éditions)
    # ----------------------------------------------------------------------------
    # Meilleur temps par coureur + année associée (parmi les arrivants avec temps)
    best_temps = (
        df[df["Temps_s"].notna()].sort_values("Temps_s")
        .groupby("Nom")[["Temps_s", "Annee"]].first()
    )
    classement = (
        pd.concat([nb_editions, best_temps, sexe_ref], axis=1).reset_index()
        .sort_values(["Nb_editions", "Temps_s"], ascending=[False, True])
        .reset_index(drop=True)
    )
    classement["Rang"] = (
        classement["Nb_editions"].rank(method="min", ascending=False).astype(int)
    )

    vue = pd.DataFrame({
        "#":              classement["Rang"],
        "Coureur":        classement["Nom"].map(nom_affiche),
        "Sexe":           classement["Sx_ref"]
                              .map({"Homme": "♂ H", "Femme": "♀ F"})
                              .fillna(""),
        "Éditions":       classement["Nb_editions"].astype(int),
        "Meilleur temps": classement["Temps_s"]
                              .map(lambda t: hms(t) if pd.notna(t) else "–"),
        "Année":          classement["Annee"]
                              .map(lambda a: int(a) if pd.notna(a) else "–"),
    })

    nb = f"{len(classement):,}".replace(",", " ")
    info_caption4 = f"**{nb} coureurs** · les ex æquo partagent le même rang"

    with st.container(key="classement_head"):
        st.markdown(
            titre("🎽", "Classement par participations", "Toutes éditions",
                  "Nombre d'éditions", FOND, graph=True),
            unsafe_allow_html=True, help=info_caption4,
        )

    st.dataframe(
        vue,
        hide_index=True,
        width="stretch",
        height=520,
        column_config={
            "#":              st.column_config.NumberColumn(width="small"),
            "Coureur":        st.column_config.TextColumn(width="medium"),
            "Sexe":           st.column_config.TextColumn(width="small"),
            "Éditions":       st.column_config.NumberColumn(width="small"),
            "Meilleur temps": st.column_config.TextColumn(width="small"),
            "Année":          st.column_config.NumberColumn(width="small"),
        },
    )
# ---------------------------------------------------------------------------
# Onglet 2 : par édition
# ---------------------------------------------------------------------------
with tab_edition:

    d = df[df["Annee"] == annee]
    arr = d[d["Temps_s"].notna()]

    def kpi(col, icone, label, n, temps, couleur):
        col.markdown(
            f"<div class='kpi-card' style='--c:{couleur}'>"
            f"<div class='kpi-ico'>{icone}</div>"
            f"<div><div class='kpi-lab'>{label}</div>"
            f"<div class='kpi-val'>{n:,}</div>".replace(",", " ")
            + f"<div class='kpi-moy'>Temps moyen<b>{hms(temps)}</b></div></div></div>",
            unsafe_allow_html=True,
        )

    k3, k1, k2 = st.columns(3)
    kpi(k1, "🏁", "Participants", len(d), arr["Temps_s"].mean(), FOND)
    kpi(k2, "🏃", "Hommes", int((d["Sx"] == "Homme").sum()),
        arr.loc[arr["Sx"] == "Homme", "Temps_s"].mean(), ROUGE)
    kpi(k3, "🏃‍♀️", "Femmes", int((d["Sx"] == "Femme").sum()),
        arr.loc[arr["Sx"] == "Femme", "Temps_s"].mean(), VERT)
    st.write("")

    # ---- Catégories (propres à l'édition choisie)
    cats = [c for c in ORDRE_CAT if c in set(d["Cat"])]
    cats += sorted(c for c in set(d["Cat"]) if c and c not in ORDRE_CAT)

    with st.container(key="pills_cat"):
        choix = st.pills("Catégorie", ["Scratch"] + cats, default="Scratch",
                         key=f"pills_cat_{annee}", label_visibility="collapsed") or "Scratch"

    dp = d if choix == "Scratch" else d[d["Cat"] == choix]
    dp_arr = dp[dp["Temps_s"].notna()]               # arrivants de la sélection

    nb = (pd.cut(dp_arr["Temps_s"] / 60, bins=[-float("inf")] + bornes + [float("inf")],
                 labels=etiquettes, right=False)
          .value_counts().reindex(etiquettes, fill_value=0))
    part = nb / max(nb.sum(), 1) * 100

    # ----------------------------------------------------------------------------
    # Podiums pour l'édition
    # ----------------------------------------------------------------------------
    zone_podiums = st.container()

    with zone_podiums:
        p1, p2 = st.columns(2)
        for col, sexe, libelle, ico, coul in (
            (p1, "Femme", "Podium Femmes", ICO_F, VERT),
            (p2, "Homme", "Podium Hommes", ICO_H, ROUGE),
        ):
            col.markdown(
                titre(ico, libelle, f"Édition {annee}",
                      "Toutes catégories" if choix == "Scratch" else f"Catégorie {choix}", coul),
                unsafe_allow_html=True,
            )
            col.markdown(podium(dp, sexe), unsafe_allow_html=True)
    st.write("")

    # ----------------------------------------------------------------------------
    # Graphiques distributions des temps Courbe/tranches
    # ----------------------------------------------------------------------------
    with st.container(key="distrib_head"):
        c_titre_d, c_vue_d = st.columns([3, 1], vertical_alignment="center")
        info_caption2 = (
            f"**Édition {annee}**"
            + ("" if choix == "Scratch" else f" · catégorie **{choix}**")
            + f"  \n{len(dp_arr)} arrivants sur {len(dp)} partants  \n"
            "Temps officiel  \n"
            "Abandons exclus des moyennes et distributions."
        )
        with c_vue_d:
            vue_d = st.segmented_control(
                "Distribution", ["Courbe", "Tranches"], default="Courbe",
                key="vue_distrib", label_visibility="collapsed",
            ) or "Courbe"

        if vue_d == "Courbe":
            c_titre_d.markdown(
                titre("📈", "Distribution des temps officiels",
                      f"Édition {annee}" + ("" if choix == "Scratch" else f" · catégorie {choix}"),
                      f"{len(dp_arr):,} arrivants".replace(",", " "), graph=True),
                unsafe_allow_html=True,
                help=info_caption2,
            )
        else:
            c_titre_d.markdown(
                titre("📊", "Densité des coureurs par tranche de performance",
                      f"Édition {annee} · tranches de {TRANCHE_PAS} min",
                      f"{int(nb.sum()):,} arrivants".replace(",", " ")
                      + ("" if choix == "Scratch" else f" · {choix}"), graph=True),
                unsafe_allow_html=True,
                help=info_caption2,
            )

    with st.container(key="distrib"):
        g_dist, g_donut = st.columns([3.4, 1])

        pas = TRANCHE_PAS * 60  # mêmes bornes que les tranches
        if arr.empty:
            lo, hi = TRANCHE_DEBUT * 60, TRANCHE_FIN * 60
        else:
            lo = int(arr["Temps_s"].min() // pas * pas)
            hi = int(-(-arr["Temps_s"].max() // pas) * pas)
        grille = np.arange(lo, hi + 1, 30, dtype=float)

        with g_dist:
            if vue_d == "Courbe":
                fig = go.Figure()
                for sexe, couleur, nom in (("Homme", ROUGE, "Hommes"), ("Femme", VERT, "Femmes")):
                    y = densite(dp_arr.loc[dp_arr["Sx"] == sexe, "Temps_s"], grille, bw=BW_DENSITE)
                    fig.add_trace(go.Scatter(
                        x=grille, y=y, name=nom, mode="lines", fill="tozeroy",
                        line=dict(color=couleur, width=2),
                        fillcolor="rgba(194,66,91,.60)" if sexe == "Homme" else "rgba(13,140,57,.60)",
                        hovertemplate=f"{nom}<br>%{{customdata}} · ≈%{{y:.0f}} coureurs<extra></extra>",
                        customdata=[hms(v) for v in grille],
                    ))
                ticks = list(range(lo, hi + 1, pas))
                fig.update_layout(
                    height=380, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.05, x=0, font=dict(color="white")),
                    xaxis=dict(tickvals=ticks, ticktext=[fmt_h(t // 60) for t in ticks], tickangle=0,
                               range=[lo, hi], showgrid=False, zeroline=False, color="white"),
                    yaxis=dict(showticklabels=True, showgrid=False, zeroline=False),
                    hovermode="x unified",
                )
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            else:
                fig = go.Figure(go.Bar(
                    x=list(nb.index), y=nb.values,
                    marker=dict(color=[PALETTE_TRANCHES[k % len(PALETTE_TRANCHES)] for k in range(len(nb))]),
                    text=[f"{v:,}".replace(",", " ") for v in nb.values], textposition="outside",
                    textfont=dict(color="white", size=13), cliponaxis=False,
                    customdata=part.values,
                    hovertemplate="%{x}<br>%{y} coureurs · %{customdata:.1f} %<extra></extra>",
                ))
                fig.update_layout(
                    height=380, margin=dict(l=10, r=10, t=30, b=10), bargap=0.25, showlegend=False,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"),
                    xaxis=dict(type="category", showgrid=False, color="white"),
                    yaxis=dict(title="", showgrid=False, zeroline=False, color="white", range=[0, max(nb.max(), 1) * 1.15]),
                )
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        with g_donut:
            if vue_d == "Courbe":
                # camembert par sexe
                rep = dp["Sx"].value_counts()
                ordre = [k for k in ("Homme", "Femme") if k in rep] + [k for k in rep.index if k not in SEXES]
                couleurs = {"Homme": ROUGE, "Femme": VERT}
                fig = go.Figure(go.Pie(
                    labels=ordre, values=[rep[k] for k in ordre], hole=0.72, sort=False,
                    marker=dict(colors=[couleurs.get(k, "#8FA3A8") for k in ordre]),
                    texttemplate="%{label}<br>%{percent:.1%}", textposition="outside",
                    hovertemplate="%{label}: %{value} coureurs<extra></extra>", showlegend=False,
                ))
                fig.update_layout(height=380, margin=dict(l=60, r=60, t=20, b=20),
                                  paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
            else:
                # camembert par tranche de performance (mêmes couleurs que les barres)
                tr = nb[nb > 0]                                   # tranches vides masquées
                coul_tr = {lab: PALETTE_TRANCHES[k % len(PALETTE_TRANCHES)]
                           for k, lab in enumerate(nb.index)}
                pct_tr = tr / max(tr.sum(), 1) * 100
                fig = go.Figure(go.Pie(
                    labels=list(tr.index), values=tr.values, hole=0.62, sort=False,
                    direction="clockwise", rotation=0,
                    marker=dict(colors=[coul_tr[l] for l in tr.index]),
                    # étiquette seulement si la part est lisible (> 10 %)
                    text=[f"{l}<br>{p:.1f} %".replace(".", ",") if p >= 10 else ""
                          for l, p in zip(tr.index, pct_tr)],
                    textinfo="text", textposition="outside", textfont=dict(size=12),
                    hovertemplate="%{label}<br>%{value} coureurs · %{percent:.1%}<extra></extra>",
                    showlegend=False,
                ))
                fig.add_annotation(
                    text=f"<b>{int(tr.sum()):,}</b><br><span style='font-size:12px'>finishers</span>".replace(",", " "),
                    x=0.5, y=0.5, showarrow=False, font=dict(color="white", size=22),
                )
                fig.update_layout(height=380, margin=dict(l=50, r=50, t=20, b=20),
                                  paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            
    # ----------------------------------------------------------------------------
    # Classement des individus de l'édition sélectionnée
    # ----------------------------------------------------------------------------
    ed = dp_arr.sort_values("Temps_s").reset_index(drop=True)
    rangs = ed["Temps_s"].rank(method="min").astype(int)

    vue = pd.DataFrame({
        "#":          [MEDAILLES_RANG.get(rg, rg) for rg in rangs],
        "Dossard":    ed["Dossard"].astype(str),
        "Coureur":    ed["Nom"].map(nom_affiche),
        "Sexe":       ed["Sx"].map({"Homme": "♂ H", "Femme": "♀ F"}).fillna(""),
        "Catégorie":  ed["Cat"].fillna("").astype(str),
        "Rang cat.":  ed["Classement_Cat"].map(rang_txt),
        "Temps":      ed["Temps_s"].map(lambda t: hms(t) if pd.notna(t) else "–"),
        "Temps réel": ed["Temps_reel_s"].map(lambda t: hms(t) if pd.notna(t) else "–"),
    })

    st.markdown(
        titre("📋", f"Classement {choix}", f"Édition {annee}",
              f"{len(ed):,} arrivants".replace(",", " "), FOND, graph=True),
        unsafe_allow_html=True,
    )
    st.dataframe(
        vue,
        hide_index=True,
        width="stretch",
        height=520,
        column_config={
            "#":          st.column_config.TextColumn(width="small"),
            "Dossard":    st.column_config.TextColumn(width="small"),
            "Coureur":    st.column_config.TextColumn(width="medium"),
            "Sexe":       st.column_config.TextColumn(width="small"),
            "Catégorie":  st.column_config.TextColumn(width="small"),
            "Rang cat.":  st.column_config.TextColumn(width="small"),
            "Temps":      st.column_config.TextColumn(width="small"),
            "Temps réel": st.column_config.TextColumn(width="small"),
        },
    )

# ----------------------------------------------------------------------------
# Onglet 3 : suivi individuel
# ----------------------------------------------------------------------------
def preparer_coureurs() -> pd.DataFrame:
    """Ajoute la place au scratch / au sexe (ex æquo = même place) et la médaille"""
    r = charger().copy()
    ok = r["Temps_s"].notna()
    r["Place"] = r[ok].groupby(["Annee", "Sx"])["Temps_s"].rank(method="dense")   # = logique des podiums
    # Place au scratch : classement officiel du CSV, sinon calculée sur le temps
    calc = r[ok].groupby("Annee")["Temps_s"].rank(method="min")
    r["Place_gen"] = r["Classement"].where(ok).fillna(calc)
    r["Medaille"] = r["Place"].where(r["Place"] <= 3)
    r["Cle"] = r["Nom"] + "||" + r["Sx"]       # même nom + même sexe = même coureur
    r["Recherche"] = r["Nom"].map(normaliser)
    return r


def fiche_kpi(col, icone, label, valeur, detail, couleur):
    col.markdown(
        f"<div class='kpi-card' style='--c:{couleur}'><div class='kpi-ico'>{icone}</div>"
        f"<div><div class='kpi-lab'>{label}</div><div class='kpi-val'>{valeur}</div>"
        f"<div class='kpi-det'>{detail}</div></div></div>",
        unsafe_allow_html=True,
    )


def graduations_temps(mini: float, maxi: float) -> tuple[list[float], list[str]]:
    """Graduations du graphique : toutes les 5 min (10 min si amplitude > 1h, 30 min si > 3h)"""
    ampl = maxi - mini
    pas = 300 if ampl < 3600 else 600 if ampl < 10800 else 1800
    deb = int(mini // pas * pas)
    vals = list(range(deb, int(maxi) + pas + 1, pas))
    return vals, [f"{v // 3600}h{v % 3600 // 60:02d}" for v in vals]


# ----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def carte_pdf(**kw):
    return generer_carte(**kw)

with tab_coureur:
    rc = preparer_coureurs()
    cle = None

    # --- recherche ---
    with st.container(key="recherche"):
        c_saisie, c_choix = st.columns(2, gap="medium", vertical_alignment="bottom")
        with c_saisie:
            saisie = st.text_input(
                "Rechercher un coureur", placeholder="Nom ou prénom (ex. DUPONT Marie)",
                key="saisie_coureur",
            )
        mots = normaliser(saisie).split()
        with c_choix:
            if len(mots) == 0:
                st.caption(f"🔎 Saisissez votre nom (2 lettres minimum) pour retrouver vos résultats depuis {int(rc['Annee'].min())}.")
            elif sum(len(m) for m in mots) < 2:
                st.caption("Saisissez au moins 2 lettres")
            else:
                masque = np.logical_and.reduce([rc["Recherche"].str.contains(m, regex=False) for m in mots])
                trouves = (rc[masque].groupby("Cle")
                           .agg(Nom=("Nom", "first"), Sx=("Sx", "first"), N=("Annee", "nunique"))
                           .reset_index().sort_values("Nom"))
                if trouves.empty:
                    st.caption("⚠️ Aucun coureur trouvé. Essayez une partie du nom, sans accents")
                elif len(trouves) == 1:
                    cle = trouves["Cle"].iloc[0]
                    st.caption(f"✅ 1 coureur trouvé : {trouves['Nom'].iloc[0]} · {trouves['Sx'].iloc[0]}")
                else:
                    lib = {r.Cle: f"{r.Nom} · {r.Sx} · {r.N} édition{'s' if r.N > 1 else ''}"
                           for r in trouves.head(50).itertuples()}
                    cle = st.selectbox(
                        f"{len(trouves)} correspondances" + (" (50 premières affichées)" if len(trouves) > 50 else ""),
                        list(lib), format_func=lib.get, index=None,
                        placeholder="Choisissez votre nom dans la liste", key="choix_coureur",
                    )

    # --- fiche coureur ---
    if cle:
        c = rc[rc["Cle"] == cle].sort_values("Annee")
        arr_c = c[c["Temps_s"].notna()]
        nom, prenom = split_nom(c["Nom"].iloc[-1])
        clubs = c["Club"].fillna("").astype(str)
        club = clubs[clubs != ""].iloc[-1] if (clubs != "").any() else ""
        sexe = c["Sx"].iloc[0]
        coul_sexe = ROUGE if sexe == "Homme" else VERT   # Homme = rouge, Femme = VERT

        st.markdown(
            f"<div class='fiche'><div class='n'>{html.escape(str(prenom))} {html.escape(str(nom))}</div>"
            f"<div class='m'>{html.escape(str(sexe))}" + (f" · {html.escape(club)}" if club else "") + "</div></div>",
            unsafe_allow_html=True,
        )
        st.write("")

        # --- KPI ---
        nb_ed = c["Annee"].nunique()
        k1, k2, k3 = st.columns(3)
        fiche_kpi(k1, "🏁", "Éditions courues", nb_ed,
                  ", ".join(str(int(a)) for a in c["Annee"]), FOND)
        if arr_c.empty:
            fiche_kpi(k2, "⏱️", "Meilleur temps", "-", "aucun temps enregistré", coul_sexe)
        else:
            b = arr_c.loc[arr_c["Temps_s"].idxmin()]
            fiche_kpi(k2, "⏱️", "Meilleur temps", hms(b.Temps_s), f"réalisé en <b>{int(b.Annee)}</b>", coul_sexe)
        med = c["Medaille"].dropna().astype(int).value_counts()
        n_med = int(med.sum())
        detail = (" · ".join(f"{'🥇🥈🥉'[p - 1]} {med[p]}" for p in (1, 2, 3) if p in med.index)
                  if n_med else "pas encore de podium")
        fiche_kpi(k3, "🏅", "Médailles", n_med, detail, OR)

        st.write("")

        # --- carte récap PDF (mise en cache) ---
        pdf = carte_pdf(
            prenom=prenom, nom=nom, sexe=sexe, club=club,
            annees=[int(x) for x in annees],
            resultats=[(int(r.Annee), None if pd.isna(r.Temps_s) else float(r.Temps_s)) for r in c.itertuples()],
            couleur=coul_sexe, medailles={int(k): int(v) for k, v in med.items()},
            logo=logo_event(), fond=fond_event(),
        )
        slug = re.sub(r"[^a-z0-9]+", "_", normaliser(f"{prenom} {nom}")).strip("_")
        with zone_export:
            st.download_button("🃏 Télécharger ma carte récap (PDF)", pdf,
                               file_name=f"carte_recap_{slug}.pdf", mime="application/pdf", key="dl_carte")

        # --- évolution des performances ---
        with st.container(key="perf"):
            with st.container(key="perf_head"):
                c_titre_p, _ = st.columns([3, 1], vertical_alignment="center")
                info_caption3 = (
                    "⭐**Point doré = meilleur temps**  \n"
                    "Plus le point est bas, plus vous avez été rapide  \n"
                    "Les éditions sans point correspondent à une absence ou à un abandon"
                )
                c_titre_p.markdown(
                    titre("📈", "Évolution de vos performances", "Temps officiel par édition",
                          f"{len(arr_c)} chrono{'s' if len(arr_c) > 1 else ''}",
                          couleur=coul_sexe, graph=True),
                    unsafe_allow_html=True, help=info_caption3,
                )

            g_perf, g_detail = st.columns([1.75, 1], gap="medium", vertical_alignment="center")

            with g_perf:
                if arr_c.empty:
                    st.write("Aucun temps à afficher.")
                else:
                    arr_c = arr_c.sort_values("Annee")
                    x = arr_c["Annee"].astype(int).to_numpy()
                    y = arr_c["Temps_s"].to_numpy()
                    marge = max(120, (y.max() - y.min()) * 0.25)
                    vals, txt = graduations_temps(y.min() - marge, y.max() + marge)
                    ib = int(np.argmin(y))
                    labels_t = [hms(v) for v in y]

                    fig = go.Figure(go.Scatter(
                        x=x, y=y,
                        mode="lines+markers+text",
                        line=dict(color=coul_sexe, width=3),
                        marker=dict(size=[16 if k == ib else 10 for k in range(len(y))],
                                    color=[OR if k == ib else coul_sexe for k in range(len(y))],
                                    line=dict(color="white", width=2)),
                        text=labels_t, textposition="top center",
                        textfont=dict(color="white", size=12),
                        customdata=np.c_[labels_t,
                                         arr_c["Place_gen"].to_numpy(),
                                         arr_c["Place"].to_numpy()],
                        hovertemplate="%{x}<br>%{customdata[0]}<br>%{customdata[1]:.0f}e au scratch"
                                      "<br>%{customdata[2]:.0f}e " + sexe.lower()
                                      + "<extra></extra>",
                        cliponaxis=False,
                    ))
                    fig.update_layout(
                        height=380, margin=dict(l=10, r=20, t=40, b=10),
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="white"),
                        xaxis=dict(type="linear", tickmode="array",
                                   tickvals=list(x), ticktext=[str(a) for a in x],
                                   range=[x.min() - 0.8, x.max() + 0.8],
                                   showgrid=False, zeroline=False, color="white",
                                   tickangle=-45 if len(x) > 10 else 0, automargin=True),
                        yaxis=dict(tickvals=vals, ticktext=txt,
                                   range=[vals[0], vals[-1]],
                                   showgrid=True, gridcolor="rgba(255,255,255,.12)",
                                   zeroline=False, color="#fff", automargin=True),
                    )
                    st.plotly_chart(fig, width="stretch", theme=None,
                                    config={"displayModeBar": False})

            with g_detail:
                temps_col = [hms(t) if pd.notna(t) else (s or "Abandon (DNF)")
                             for t, s in zip(c["Temps_s"], c["Statut"])]
                vue = pd.DataFrame({
                    "Édition":    c["Annee"].astype(int).astype(str),
                    "Temps":      temps_col,
                    "Scratch":    c["Place_gen"].map(rang_txt),
                    "Cat.":       c["Cat"].fillna("").astype(str),
                    "Rang cat.":  c["Classement_Cat"].map(rang_txt),
                    "🏅":         c["Medaille"].map(lambda m: "🥇🥈🥉"[int(m) - 1] if pd.notna(m) else ""),
                })
                st.dataframe(
                    vue, hide_index=True, width="stretch",
                    column_config={k: st.column_config.TextColumn(width="small")
                                   for k in vue.columns},
                )