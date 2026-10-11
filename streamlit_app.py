"""Données chronométriques : Le Marathon Vert Rennes (Streamlit)"""
from pathlib import Path
from carte_pdf import generer_carte

import urllib.request
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import re
import unicodedata
import streamlit as st

DATA = Path(__file__).parent / "data" / "resultats.csv"
ASSETS = Path(__file__).parent / "assets"

# Palette
GREEN_clair, GREEN_sombre, RED, FOND = "#97c221", "#018a36", "#C24247", "#0F2B30" 
OR, ARGENT, BRONZE = "#E0B400", "#9A9A9A", "#E8743B"
SEXES = {"M": "Hommes", "F": "Femmes"}
TRANCHE_DEBUT, TRANCHE_FIN, TRANCHE_PAS = 70, 150, 10   # < 1h10 | 1h10-1h20 |...| 2h20-2h30 | ≥ 2h30

st.set_page_config(page_title="Statistiques - Le Marathon Vert Rennes", page_icon="🏁", layout="wide")

st.markdown(
    f"""
    <style>

    .stApp {{background:linear-gradient(rgba(1,114,132,.40),rgba(13,43,48,.60)),
    url("https://www.lemarathonvert.org/scripts/files/690cab002365b8.66110376/@biduleee__-part248.webp") center / cover fixed no-repeat;}}

    header[data-testid="stHeader"] {{background: transparent;}}

    .st-emotion-cache-lhe5w4 {{padding: 1rem 1rem 1rem;}}

    .stApp [data-testid="stCaptionContainer"],
    .stApp [data-testid="stCaptionContainer"] * {{color: rgba(255,255,255,.70);}}
    .stApp [data-testid="stWidgetLabel"] p {{color: white;font-weight: 600;}}

      /* Sélecteur d'édition : posé sur la ligne des onglets, à droite */
      .st-key-annees {{ display:flex; flex-direction:column; align-items:flex-end; position:relative; z-index:5; margin-bottom:-4.68rem; pointer-events:none; }}
      .st-key-annees * {{ pointer-events:none; }}
      .st-key-annees button, .st-key-annees [data-testid="stSelectbox"], .st-key-annees [data-testid="stSelectbox"] * {{ pointer-events:auto; }}
      .st-key-annees > [data-testid="stLayoutWrapper"] {{ width:250px; margin-left:auto; transform:translateY(14px); }}
      .st-key-annees [data-testid="stHorizontalBlock"] {{ width:100%; flex-wrap:nowrap; gap:6px; align-items:center; background:rgba(15,43,48,.55); backdrop-filter:blur(4px); border-radius:999px; padding:5px; }}

      .st-key-annees [data-testid="stColumn"] {{ min-width:0; }}
      .st-key-annees [data-testid="stButton"] button {{ width:36px; height:36px; min-height:36px; padding:0; border-radius:50% !important; background:rgba(255,255,255,.12) !important; border:0 !important; transition:all .18s ease; }}
      .st-key-annees [data-testid="stButton"] button * {{ color:#fff !important; font-size:1.3rem; font-weight:700; line-height:1; }}
      .st-key-annees [data-testid="stButton"] button:hover:not(:disabled) {{ background:#fff !important; }}
      .st-key-annees [data-testid="stButton"] button:hover:not(:disabled) * {{ color:{GREEN_clair} !important; }}
      .st-key-annees [data-testid="stButton"] button:disabled {{ opacity:.3; }}
      .st-key-annees [data-testid="stButton"] button:focus-visible {{ outline:2px solid {GREEN_sombre}; outline-offset:2px; }}

      .st-key-annees [data-testid="stSelectbox"] [data-baseweb="select"] > div,
      .st-key-annees [data-testid="stSelectbox"] .react-aria-ComboBox > div {{ background:#fff !important; border:0 !important; border-radius:999px; min-height:36px; align-items:center; }}
      .st-key-annees [data-testid="stSelectbox"] * {{ color:{GREEN_clair} !important; font-weight:800; }}
      .st-key-annees [data-testid="stSelectbox"] button {{ background:transparent !important; box-shadow:none !important; border:0 !important; border-radius:0 !important; width:32px; height:100%; min-height:0; padding:0; display:flex; align-items:center; justify-content:center; }}
      
      /* masqué sur l'onglet « Suivi individuel » (les années n'y servent pas) */
      .stApp:has(.stTabs [role="tab"][data-key="1"][aria-selected="true"]) .st-key-annees {{ display:none; }}
      
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
      .kpi-val {{ color:#0B3A4F; font-size:2.1rem; font-weight:800; line-height:1.1; }}
      .kpi-moy {{ color:#6b6b6b; font-size:.8rem; margin-top:2px; }}
      .kpi-moy b {{ color:#0B3A4F; font-weight:800; font-size:.95rem; padding-left:4px; }}
      
      .hero {{ font-family:'Poppins',sans-serif; margin:6px 0 18px 0; display:flex; align-items:center; gap:20px; }}
      .hero .hero-logo {{ height:84px; width:auto; flex:none; filter:drop-shadow(0 2px 10px rgba(0,0,0,.35)); }}

      .hero .kicker {{ color:"white"; font-size:.78rem; font-weight:600; letter-spacing:.22em;
                       text-transform:uppercase; display:flex; align-items:center; gap:10px; }}
      .hero .h {{ color:#fff; font-size:2.5rem; font-weight:800; line-height:1.1; margin-top:6px;
                  text-shadow:0 2px 14px rgba(0,0,0,.45); }}
      .hero .h span {{ color:{GREEN_sombre}; }}
      
      .st-key-evol_head {{ background:rgba(15,43,48,.92); backdrop-filter:blur(4px); border-radius:12px 12px 0 0;
                           padding:10px 16px 15px 16px; margin-bottom:-1rem; box-shadow:inset 0 -3px 0 #fff; }}
      .st-key-evol_head .titre {{ background:none; box-shadow:none; backdrop-filter:none; padding:0; border-radius:0; }}
      .st-key-evol_head [data-testid="stHorizontalBlock"] {{ align-items:center; }}
      .st-key-evol_head [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{
            width:100%; display:flex; justify-content:flex-end; }}
      .st-key-evol_head [data-testid="stButtonGroup"] {{ background:transparent; width:fit-content; }}
      .st-key-evol_head [role="radiogroup"] {{ background:rgba(255,255,255,.08); border-radius:999px; padding:4px;
            gap:4px; width:fit-content; border:1px solid rgba(255,255,255,.15); }}
      .st-key-evol_head button[role="radio"] {{ background:transparent !important; border:0 !important;
            border-radius:999px !important; padding:5px 16px; }}
      .st-key-evol_head button[role="radio"] * {{ color:rgba(255,255,255,.75) !important; font-weight:600; }}
      .st-key-evol_head button[role="radio"]:hover * {{ color:#fff !important; }}
      .st-key-evol_head button[role="radio"][aria-checked="true"] {{ background:#fff !important; }}
      .st-key-evol_head button[role="radio"][aria-checked="true"] * {{ color:{GREEN_clair} !important; font-weight:700; }}
      .st-key-distrib_head {{ background:rgba(15,43,48,.92); backdrop-filter:blur(4px); border-radius:12px 12px 0 0;
                           padding:10px 16px 15px 16px; margin-bottom:-1rem; box-shadow:inset 0 -3px 0 #fff; }}
      .st-key-distrib_head .titre {{ background:none; box-shadow:none; backdrop-filter:none; padding:0; border-radius:0; }}
      .st-key-distrib_head [data-testid="stHorizontalBlock"] {{ align-items:center; }}
      .st-key-distrib_head [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{
            width:100%; display:flex; justify-content:flex-end; }}
      .st-key-distrib_head [data-testid="stButtonGroup"] {{ background:transparent; width:fit-content; }}
      .st-key-distrib_head [role="radiogroup"] {{ background:rgba(255,255,255,.08); border-radius:999px; padding:4px;
            gap:4px; width:fit-content; border:1px solid rgba(255,255,255,.15); }}
      .st-key-distrib_head button[role="radio"] {{ background:transparent !important; border:0 !important;
            border-radius:999px !important; padding:5px 16px; }}
      .st-key-distrib_head button[role="radio"] * {{ color:rgba(255,255,255,.75) !important; font-weight:600; }}
      .st-key-distrib_head button[role="radio"]:hover * {{ color:#fff !important; }}
      .st-key-distrib_head button[role="radio"][aria-checked="true"] {{ background:#fff !important; }}
      .st-key-distrib_head button[role="radio"][aria-checked="true"] * {{ color:{GREEN_clair} !important; font-weight:700; }}
      .st-key-evol, .st-key-evol_pct, .st-key-evol_pct_an {{ background:rgba(15,43,48,.62); backdrop-filter:blur(4px);
            border-radius:0 0 12px 12px; padding:10px 14px 6px 14px; }}
      .st-key-evol div[data-testid="stPlotlyChart"],
      .st-key-evol_pct div[data-testid="stPlotlyChart"],
      .st-key-evol_pct_an div[data-testid="stPlotlyChart"] {{ background:transparent; border-radius:0; }}
 
      .st-key-distrib {{ background:rgba(15,43,48,.62); backdrop-filter:blur(4px);
            border-radius:0 0 12px 12px; padding:10px 14px 6px 14px; margin-top:0; }}
      .st-key-distrib div[data-testid="stPlotlyChart"] {{ background:transparent; border-radius:0; }}
 
      .st-key-pills_cat button[role="radio"] {{ background:rgba(15,43,48,.55) !important;
            border:1px solid rgba(255,255,255,.28) !important; border-radius:999px !important;
            backdrop-filter:blur(4px); transition:all .15s ease; }}
      .st-key-pills_cat button[role="radio"] * {{ color:rgba(255,255,255,.85) !important; }}
      .st-key-pills_cat button[role="radio"]:hover {{ border-color:rgba(255,255,255,.7) !important;
            background:rgba(255,255,255,.12) !important; }}
      .st-key-pills_cat button[role="radio"][aria-checked="true"] {{
            background:rgba(255,255,255,.22) !important; border:1px solid #fff !important; }}
      .st-key-pills_cat button[role="radio"][aria-checked="true"] * {{ color:#fff !important; font-weight:700; }}
      
      .titre {{ display:flex; align-items:center; gap:12px; background:rgba(15,43,48,.92);
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
      
      @import url('https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,400;0,600;1,800&display=swap');
      .pod-wrap {{ display:flex; align-items:flex-end; gap:14px; padding:22px 14px 16px 14px;
                   background:rgba(15,43,48,.62); backdrop-filter:blur(4px);
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
      .pod-nom {{ color:#0B3A4F; font-weight:800; font-style:italic; text-transform:uppercase;
                  font-size:.88rem; line-height:1.15; overflow-wrap:anywhere;
                  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
      .pod-card.p1 .pod-nom {{ font-size:1rem; }}
      .pod-club {{ color:#6b6b6b; font-size:.68rem; text-transform:uppercase; margin-top:6px;
                   line-height:1.2; overflow-wrap:anywhere;
                   display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
      .pod-meta {{ color:#6b6b6b; font-size:.75rem; margin-top:4px; }}
      .pod-meta i {{ color:{GREEN_sombre}; font-style:normal; font-weight:600; padding:0 2px; }}
      .pod-temps {{ color:#0B3A4F; font-weight:800; font-size:1.25rem; margin-top:10px; }}
      .pod-card.p1 .pod-temps {{ font-size:1.5rem; }}
      div[data-testid="stPlotlyChart"] {{ background:white; border-radius:0 0 10px 10px; }}
 
      .stTabs [role="tablist"] {{ gap:6px; background:rgba(15,43,48,.55); backdrop-filter:blur(4px);
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
      .stTabs [role="tab"][aria-selected="true"] p {{ color:{GREEN_clair} !important; font-weight:700; }}
 
      .st-key-suivi {{ background:rgba(15,43,48,.62); backdrop-filter:blur(4px);
                       border-radius:0 0 10px 10px; padding:6px 14px 10px 14px; }}
      .st-key-suivi div[data-testid="stPlotlyChart"] {{ background:transparent; border-radius:0; }}
      .st-key-recherche, .st-key-recherche_choix {{ background:rgba(15,43,48,.62); backdrop-filter:blur(4px);
                                                  border-radius:12px; padding:14px 18px 6px 18px; }}
      .st-key-recherche input {{ background:#fff; color:#0B3A4F; }}
 
      .fiche {{ font-family:'Poppins',sans-serif; color:#fff; margin:4px 0 2px 0; text-align:center; }}
      .fiche .n {{ font-size:1.5rem; font-weight:800; font-style:italic; text-transform:uppercase; line-height:1.1; }}
      .fiche .m {{ color:rgba(255,255,255,.7); font-size:.85rem; margin-top:2px; }}
      
      .kpi-det {{ color:#6b6b6b; font-size:.8rem; margin-top:2px; }}
      .kpi-det b {{ color:#0B3A4F; font-weight:800; }}
      
      .st-key-export_carte:has(button) {{ display:flex; flex-direction:column; align-items:flex-end; position:relative;z-index:5; margin-bottom:-4.68rem; pointer-events:none; }}
      [data-testid="stLayoutWrapper"]:has(> .st-key-export_carte) {{ margin-bottom:-1rem; }}
      .st-key-export_carte [data-testid="stElementContainer"] {{ width:fit-content; transform:translateY(3px); }}
      .st-key-export_carte button, .st-key-export_carte button * {{ pointer-events:auto; }}
      .st-key-dl_carte button {{ background:#fff; border:0; border-radius:999px; padding:9px 20px;box-shadow:0 4px 14px rgba(0,0,0,.25); }}
      .st-key-dl_carte button p {{ color:{GREEN_clair}; font-weight:700; }}
      .st-key-dl_carte button:hover {{ background:#eef3f4; }}

      /* visible uniquement sur l'onglet "Suivi individuel" */
      .stApp:has(.stTabs [role="tab"][data-key="0"][aria-selected="true"]) [data-testid="stLayoutWrapper"]:has(> .st-key-export_carte) {{ display:none; }} 
      .tbl-suivi {{ width:100%; border-collapse:collapse; background:#fff; border-radius:0 0 10px 10px;
                    overflow:hidden; font-family:'Poppins',sans-serif; font-size:.85rem; }}
      .tbl-suivi th {{ background:#eef3f4; color:#0B3A4F; text-align:left; padding:8px 12px; font-weight:700; }}
      .tbl-suivi td {{ color:#0B3A4F; padding:7px 12px; border-top:1px solid #e6ecee; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    "<div class='hero'>"
    "<img class='hero-logo' src='https://www.lemarathonvert.org/scripts/files/698eead8c70301.68707929/header_logo.webp' alt='Logo du semi-marathon'>"
    "<div class='hero-txt'>"
    "<div class='kicker'>Statistiques chronométriques</div>"
    "<div class='h'>Le Marathon Vert Rennes</div>"
    "</div></div>",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
@st.cache_data
def charger() -> pd.DataFrame:
    df = pd.read_csv(DATA).fillna(
        {"Statut": "", "Nom": "", "Prénom": "", "Club": "", "Catégorie": ""})
    # Catégorie suffixée par le sexe (M0H, SEF...) -> on retire le suffixe
    df["Catégorie"] = df["Catégorie"].str.replace(r"^(\w{2})[HF]$", r"\1", regex=True)
    return df

ORDRE_CAT = ["CA", "JU", "ES", "SE"] + [f"M{i}" for i in range(10)]

def hms(s: float) -> str:
    if pd.isna(s):
        return "–"
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"

ICO_F = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="9" r="5.5"/><path d="M12 14.5V22M8.5 18.5h7"/></svg>'
ICO_H = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="14" r="5.5"/><path d="M14 10l6-6M14.5 4H20v5.5"/></svg>'

def titre(icone: str, texte: str, sous: str = "", puce: str = "", couleur: str = GREEN_clair, graph: bool = False) -> str:
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
    """'EL OUARDI Hamza' -> ('EL OUARDI', 'Hamza')"""
    mots = nom.split()
    i = 0
    while i < len(mots) - 1 and mots[i].replace("-", "").replace("'", "").isupper():
        i += 1
    return " ".join(mots[:i]) or nom, " ".join(mots[i:])


def carte(r, place: int, couleur: str) -> str:
    nom, prenom = (r.Nom, r.Prénom) if r.Prénom else split_nom(r.Nom)
    club = f"<div class='pod-club'>{r.Club}</div>" if r.Club else ""
    cat = f"<i>/</i> {r.Catégorie}" if r.Catégorie else ""
    return (
        f"<div class='pod-card p{place}' style='--c:{couleur}'>"
        f"<div class='pod-medal'>{MEDAILLE.format(t=40 if place == 1 else 30)}</div>"
        f"<div class='pod-nom'>{prenom} {nom}</div>{club}"
        f"<div class='pod-meta'>{r.Sexe} {cat}</div>"
        f"<div class='pod-temps'>{hms(r.Temps_s)}</div></div>"
    )

def podium(d: pd.DataFrame, sexe: str) -> str:
    s = d[(d["Sexe"] == sexe) & d["Temps_s"].notna()].copy()
    s["Place"] = s["Temps_s"].rank(method="dense")
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
    """Estimation de densité gaussienne, exprimée en coureurs par minute"""
    t = t.dropna().to_numpy()
    if len(t) == 0:
        return np.zeros_like(grille)
    z = (grille[:, None] - t[None, :]) / bw
    return np.exp(-0.5 * z**2).sum(axis=1) / (bw * np.sqrt(2 * np.pi)) * 60

df = charger()
annees = sorted(df["Annee"].unique())

# Sélecteur d'édition : rendu avant les onglets pour connaître l'année, placé par CSS sur leur ligne
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
    
zone_export = st.container(key="export_carte")
tab_stats, tab_coureur = st.tabs(["📊 Statistiques", "🏃 Suivi individuel"])

with tab_stats:
 
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
 
    st.write("")
    k3, k1, k2 = st.columns(3)
    kpi(k1, "🏁", "Participants", len(d), arr["Temps_s"].mean(), FOND)
    kpi(k2, "🏃", "Hommes", int((d["Sexe"] == "Homme").sum()),
        arr.loc[arr["Sexe"] == "Homme", "Temps_s"].mean(), RED)
    kpi(k3, "🏃‍♀️", "Femmes", int((d["Sexe"] == "Femme").sum()),
        arr.loc[arr["Sexe"] == "Femme", "Temps_s"].mean(), GREEN_clair)
    st.write("")

    # ----------------------------------------------------------------------------
    # Podiums
    # ----------------------------------------------------------------------------
    zone_podiums = st.container()  # réservé AVANT les pastilles : s'affichera au-dessus
 
    cats = [c for c in ORDRE_CAT if c in set(d["Catégorie"])]
    cats += sorted(c for c in set(d["Catégorie"]) if c and c not in ORDRE_CAT)
    choix = st.pills("", ["Scratch"] + cats, default="Scratch", key="pills_cat") or "Scratch"
    dp = d if choix == "Scratch" else d[d["Catégorie"] == choix]
    dp_arr = dp[dp["Temps_s"].notna()]  # arrivants de la sélection (graphiques)
 
    with zone_podiums:  # on remplit la zone une fois le choix connu
        p1, p2 = st.columns(2)
        for col, sexe, libelle, ico, coul in (
            (p1, "Femme", "Podium Femmes", ICO_F, GREEN_clair),
            (p2, "Homme", "Podium Hommes", ICO_H, RED),
        ):
            col.markdown(
                titre(ico, libelle, f"Édition {annee}", "Toutes catégories" if choix == "Scratch" else f"Catégorie {choix}", coul),
                unsafe_allow_html=True,
            )
            col.markdown(podium(dp, sexe), unsafe_allow_html=True)

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
    sel = df if choix == "Scratch" else df[df["Catégorie"] == choix]
    sel = sel[sel["Temps_s"].notna()].copy()
    sel["Tranche"] = pd.cut(
        sel["Temps_s"] / 60, bins=[-float("inf")] + bornes + [float("inf")],
        labels=etiquettes, right=False,
    )
 
    # ----------------------------------------------------------------------------
    # Distribution des temps (courbe) / densité par tranche de performance
    # ----------------------------------------------------------------------------
    sel_an = sel[sel["Annee"] == annee]
    nb = sel_an["Tranche"].value_counts().reindex(etiquettes, fill_value=0)
    part = nb / max(nb.sum(), 1) * 100
 
    with st.container(key="distrib_head"):
        c_titre_d, c_vue_d = st.columns([3, 1], vertical_alignment="center")
        with c_vue_d:
            vue_d = st.segmented_control(
                "Distribution", ["Courbe", "Tranches"], default="Courbe",
                key="vue_distrib", label_visibility="collapsed",
            ) or "Courbe"
        if vue_d == "Courbe":
            c_titre_d.markdown(
                titre("📈", "Distribution des temps officiels",
                      f"Édition {annee} · temps pistolet" + ("" if choix == "Scratch" else f" · catégorie {choix}"),
                      f"{len(dp_arr):,} arrivants".replace(",", " "), graph=True),
                unsafe_allow_html=True,
            )
        else:
            c_titre_d.markdown(
                titre("📊", "Densité des coureurs par tranche de performance",
                      f"Édition {annee} · tranches de {TRANCHE_PAS} min · temps pistolet",
                      f"{int(nb.sum()):,} arrivants".replace(",", " ")
                      + ("" if choix == "Scratch" else f" · {choix}"), graph=True),
                unsafe_allow_html=True,
            )
    with st.container(key="distrib"):
        g_dist, g_donut_sex = st.columns([3.4, 1])
 
        pas = TRANCHE_PAS * 60  # mêmes bornes que les tranches (10 min)
        lo = int(arr["Temps_s"].min() // pas * pas)
        hi = int(-(-arr["Temps_s"].max() // pas) * pas)
        grille = np.arange(lo, hi + 1, 30, dtype=float)
 
        with g_dist:
            if vue_d == "Courbe":
                fig = go.Figure()
                for sexe, couleur, nom in (("Homme", RED, "Hommes"), ("Femme", GREEN_clair, "Femmes")):
                    y = densite(dp_arr.loc[dp_arr["Sexe"] == sexe, "Temps_s"], grille, bw=240)
                    fig.add_trace(go.Scatter(
                        x=grille, y=y, name=nom, mode="lines", fill="tozeroy",
                        line=dict(color=couleur, width=2),
                        fillcolor="rgba(194,66,91,.60)" if sexe == "Homme" else "rgba(58,181,176,.60)",
                        hovertemplate=f"{nom}<br>%{{customdata}} · ≈%{{y:.0f}} coureurs<extra></extra>",
                        customdata=[hms(v) for v in grille],
                    ))
                ticks = list(range(lo, hi + 1, pas))
                fig.update_layout(
                    height=380, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)",showlegend=False,
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
                    height=380, margin=dict(l=10, r=10, t=30, b=10), bargap=0.25,showlegend=False,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"),
                    xaxis=dict(type="category", showgrid=False, color="white"),
                    yaxis=dict(title="", showgrid=False, zeroline=False, color="white", range=[0, max(nb.max(), 1) * 1.15]),
                )
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
 
        with g_donut_sex:
            rep = dp["Sexe"].value_counts()
            ordre = [k for k in ("Homme", "Femme") if k in rep] + [k for k in rep.index if k not in SEXES]
            couleurs = {"Homme": RED, "Femme": GREEN_clair}
            fig = go.Figure(go.Pie(
                labels=ordre, values=[rep[k] for k in ordre], hole=0.72, sort=False,
                marker=dict(colors=[couleurs.get(k, "#8FA3A8") for k in ordre]),
                texttemplate="%{label}<br>%{percent:.1%}", textposition="outside",
                hovertemplate="%{label}: %{value} coureurs<extra></extra>", showlegend=False,
            ))
            fig.update_layout(height=380, margin=dict(l=60, r=60, t=20, b=20),
                              paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
 
    # ----------------------------------------------------------------------------
    # Zone à bascule : évolution du nombre de coureurs / évolution de la densité
    # ----------------------------------------------------------------------------
    st.write("")
    with st.container(key="evol_head"):
        c_titre, c_vue = st.columns([3, 1], vertical_alignment="center")
        with c_vue:
            vue = st.segmented_control(
                "Graphique", ["Nombre", "Densité"], default="Nombre",
                key="vue_evol", label_visibility="collapsed",
            ) or "Nombre"
        if vue == "Nombre":
            c_titre.markdown(
                titre("📶", "Évolution du nombre de coureurs",
                      f"Éditions {annees[0]} à {annees[-1]}", f"{len(d):,} en {annee}".replace(",", " "), graph=True),
                unsafe_allow_html=True,
            )
        else:
            c_titre.markdown(
                titre("🔎", "Évolution de la densité des coureurs",
                      f"Part des arrivants par tranche de {TRANCHE_PAS} min · temps pistolet",
                      "Toutes catégories" if choix == "Scratch" else f"Catégorie {choix}", graph=True),
                unsafe_allow_html=True,
            )
 
    if vue == "Nombre":
        with st.container(key="evol"):
            evol = (
                df.groupby(["Annee", "Sexe"]).size().unstack(fill_value=0)
                .reindex(columns=["Femme", "Homme"], fill_value=0)
            )
            evol["Total"] = df.groupby("Annee").size()  # inclut aussi le genre « X »
            x = evol.index.astype(str)
 
            fig = go.Figure()
            for sexe, couleur, nom in (("Femme", GREEN_clair, "Femmes"), ("Homme", RED, "Hommes")):
                fig.add_trace(go.Bar(
                    x=x, y=evol[sexe], name=nom,
                    marker=dict(
                        color=couleur,
                        line=dict(color="white", width=[2 if a == annee else 0 for a in evol.index]),
                    ),
                    hovertemplate=f"{nom} : %{{y}} coureurs<extra></extra>",
                ))
            # Total au-dessus de chaque barre
            fig.add_trace(go.Scatter(
                x=x, y=evol["Total"], mode="text",
                text=[f"{t:,}".replace(",", " ") for t in evol["Total"]],
                textposition="top center", textfont=dict(color="white", size=14),
                showlegend=False, hoverinfo="skip",
            ))
            fig.update_layout(
                barmode="stack", height=340, margin=dict(l=10, r=10, t=10, b=10),showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                legend=dict(orientation="h", y=1.08, x=0, font=dict(color="white")),
                xaxis=dict(type="category", showgrid=False, color="white"),
                yaxis=dict(showticklabels=False, showgrid=False, zeroline=False,
                           range=[0, evol["Total"].max() * 1.15]),
                bargap=0.35,
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
 
    st.caption(f"Édition {annee}" + ("" if choix == "Scratch" else f" · catégorie {choix}") + f" · {len(dp_arr)} arrivants sur {len(dp)} partants · "
               "temps pistolet · abandons exclus des moyennes et distributions.") 

# ----------------------------------------------------------------------------
# Onglet 2 : suivi individuel
# ----------------------------------------------------------------------------
def normaliser(t: str) -> str:
    """Minuscules, sans accents ni tirets : 'Hélène-Marie' -> 'helene marie'."""
    t = unicodedata.normalize("NFD", str(t)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
 
def _charger_asset(noms: tuple[str, ...], url_base: str = "https://semicancalestmalo.fr/assets/") -> bytes | None:
    """Fichier du dépôt en priorité (premier nom trouvé), sinon téléchargement."""
    for nom in noms:
        if (ASSETS / nom).exists():
            return (ASSETS / nom).read_bytes()
    for nom in noms:
        try:
            req = urllib.request.Request(url_base + nom, headers={"User-Agent": "Mozilla/5.0"})
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

# ----------------------------------------------------------------------------

def preparer_coureurs() -> pd.DataFrame:
    """Ajoute la place au scratch / au sexe (ex æquo = même place) et la médaille"""
    r = charger().copy()
    ok = r["Temps_s"].notna()
    r["Place"] = r[ok].groupby(["Annee", "Sexe"])["Temps_s"].rank(method="dense")   # = logique des podiums
    r["Place_gen"] = r[ok].groupby("Annee")["Temps_s"].rank(method="min")
    r["Medaille"] = r["Place"].where(r["Place"] <= 3)
    r["Cle"] = r["Nom"].str.strip() + "||" + r["Sexe"]       # même nom + même sexe = même coureur
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
    """Graduations du graphique, toutes les 5 min (10 min si l'amplitude est grande)"""
    pas = 300 if (maxi - mini) < 3600 else 600
    deb = int(mini // pas * pas)
    vals = list(range(deb, int(maxi) + pas + 1, pas))
    return vals, [f"{v // 3600}h{v % 3600 // 60:02d}" for v in vals]
 
# ----------------------------------------------------------------------------

with tab_coureur:
    rc = preparer_coureurs()
    st.write("")
    cle = None
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
                st.caption("🔎 Saisissez votre nom (2 lettres minimum) pour retrouver vos résultats depuis 2022.")
            elif sum(len(m) for m in mots) < 2:
                st.caption("Saisissez au moins 2 lettres.")
            else:
                masque = np.logical_and.reduce([rc["Recherche"].str.contains(m, regex=False) for m in mots])
                trouves = (rc[masque].groupby("Cle")
                           .agg(Nom=("Nom", "first"), Sexe=("Sexe", "first"), N=("Annee", "nunique"))
                           .reset_index().sort_values("Nom"))
                if trouves.empty:
                    st.caption("⚠️ Aucun coureur trouvé. Essayez une partie du nom, sans accents.")
                elif len(trouves) == 1:
                    cle = trouves["Cle"].iloc[0]
                    st.caption(f"✅ 1 coureur trouvé : {trouves['Nom'].iloc[0]} · {trouves['Sexe'].iloc[0]}")
                else:
                    lib = {r.Cle: f"{r.Nom} · {r.Sexe} · {r.N} édition{'s' if r.N > 1 else ''}"
                           for r in trouves.head(50).itertuples()}
                    cle = st.selectbox(
                        f"{len(trouves)} correspondances" + (" (50 premières affichées)" if len(trouves) > 50 else ""),
                        list(lib), format_func=lib.get, index=None, placeholder="Choisissez votre nom dans la liste",
                    )
 
    if cle:
        c = rc[rc["Cle"] == cle].sort_values("Annee")
        arr_c = c[c["Temps_s"].notna()]
        nom, prenom = split_nom(c["Nom"].iloc[-1])
        club = c.loc[c["Club"] != "", "Club"].iloc[-1] if (c["Club"] != "").any() else ""
        st.markdown(
            f"<div class='fiche'><div class='n'>{prenom} {nom}</div>"
            f"<div class='m'>{c['e' \
            'Sexe'].iloc[0]}" + (f" · {club}" if club else "") + "</div></div>",
            unsafe_allow_html=True,
        )
        st.write("")
 
        coul_sexe = RED if c["Sexe"].iloc[0] == "Homme" else GREEN_clair   # Homme = red, Femme = green
        nb_ed = c["Annee"].nunique()
        k1, k2, k3 = st.columns(3)
        fiche_kpi(k1, "🏁", "Éditions courues", nb_ed,
                  ", ".join(str(a) for a in c["Annee"]), FOND)
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
        
        pdf = generer_carte(
            prenom=prenom, nom=nom, sexe=c["Sexe"].iloc[0], club=club,
            annees=[int(x) for x in annees],
            resultats=[(int(r.Annee), None if pd.isna(r.Temps_s) else float(r.Temps_s)) for r in c.itertuples()],
            couleur=coul_sexe, medailles={int(k): int(v) for k, v in med.items()}, logo=logo_event(), fond=fond_event(),
        )
        slug = re.sub(r"[^a-z0-9]+", "_", normaliser(f"{prenom} {nom}")).strip("_")
        with zone_export:
            st.download_button("🃏 Télécharger ma carte récap (PDF)", pdf,
                file_name=f"carte_recap_{slug}.pdf", mime="application/pdf", key="dl_carte")
             
        col_g, col_d = st.columns([1.75, 1], gap="medium")
        with col_g:
            # --- évolution des temps ---
            st.markdown(titre("📈", "Évolution de vos performances", "Temps pistolet par édition",
                              f"{len(arr_c)} chrono{'s' if len(arr_c) > 1 else ''}", couleur=coul_sexe),
                        unsafe_allow_html=True)
            with st.container(key="suivi"):
                if arr_c.empty:
                    st.write("Aucun temps à afficher.")
                else:
                    y = arr_c["Temps_s"].to_numpy()
                    marge = max(120, (y.max() - y.min()) * 0.25)
                    vals, txt = graduations_temps(y.min() - marge, y.max() + marge)
                    ib = int(np.argmin(y))
                    biseau = len(y) > 8          # beaucoup d'éditions → texte incliné
                    fig = go.Figure(go.Scatter(
                        x=arr_c["Annee"].astype(str), y=y,
                        mode="lines+markers" if biseau else "lines+markers+text",
                        line=dict(color=coul_sexe, width=3),
                        marker=dict(size=[16 if k == ib else 10 for k in range(len(y))],
                                    color=[OR if k == ib else coul_sexe for k in range(len(y))],
                                    line=dict(color="white", width=2)),
                        text=[hms(v) for v in y], textposition="top center", textfont=dict(color="white", size=13),
                        customdata=np.c_[[hms(v) for v in y], arr_c["Place_gen"].to_numpy(), arr_c["Place"].to_numpy()],
                        hovertemplate="%{x}<br>%{customdata[0]}<br>%{customdata[1]:.0f}e au scratch"
                                      "<br>%{customdata[2]:.0f}e " + c["Sexe"].iloc[0].lower() + "<extra></extra>",
                        cliponaxis=False,
                    ))
                    if biseau:
                        fig.update_layout(annotations=[
                            dict(x=list(annees).index(a), y=v, text=hms(v), showarrow=False,
                                 textangle=-60, xanchor="left", yanchor="bottom",
                                 xshift=-2, yshift=10,
                                 font=dict(color="white", size=12))
                            for a, v in zip(arr_c["Annee"], y)
                        ])
                    fig.update_layout(
                        height=380, margin=dict(l=10, r=20, t=60 if biseau else 30, b=10),
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"),
                        xaxis=dict(type="category", categoryorder="array", categoryarray=[str(a) for a in annees],
                                   showgrid=False, color="white",
                                   tickangle=-45 if biseau else 0),
                        yaxis=dict(tickvals=vals, ticktext=txt, range=[vals[0], vals[-1]], showgrid=True,
                                   gridcolor="rgba(255,255,255,.12)", zeroline=False, color="white")
                    )
                    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            st.caption("⭐ Point doré = meilleur temps. Plus le point est bas, plus vous avez été rapide. "
                       "Les éditions sans point correspondent à une absence ou à un abandon.")
 
        with col_d:
            # --- détail par édition ---
            st.markdown(titre("📋", "Détail par édition", "Vos performances","", couleur=coul_sexe), unsafe_allow_html=True)
            lignes = "".join(
                f"<tr><td><b>{int(r.Annee)}</b></td><td>{hms(r.Temps_s) if pd.notna(r.Temps_s) else 'Abandon (DNF)'}</td>"
                f"<td>{'' if pd.isna(r.Place_gen) else f'{int(r.Place_gen)}e'}</td>"
                f"<td>{'' if pd.isna(r.Place) else f'{int(r.Place)}e'}</td>"
                f"<td>{r.Catégorie or ''}</td><td>{'🥇🥈🥉'[int(r.Medaille) - 1] if pd.notna(r.Medaille) else ''}</td></tr>"
                for r in c.itertuples()
            )
            st.markdown(
                "<table class='tbl-suivi'><tr><th>Édition</th><th>Temps</th><th>Scratch</th>"
                f"<th>Sexe</th><th>Catégorie.</th><th></th></tr>{lignes}</table>",
                unsafe_allow_html=True,
            )