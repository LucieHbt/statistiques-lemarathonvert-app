"""Rapport de bilan d'une édition (PDF) destiné à l'organisation des courses.

Deux usages :
- depuis l'application Streamlit (bouton « Rapport ») : `generer_rapport(df, annee, ...)`
  reçoit le DataFrame déjà nettoyé de l'appli et renvoie les octets du PDF ;
- en ligne de commande, une fois par an après la course :

      python rapport_pdf.py                 # dernière édition > rapports/rapport_2026.pdf
      python rapport_pdf.py 2025 2026       # plusieurs éditions
      python rapport_pdf.py --toutes        # toutes les éditions

Événement à course unique : pas de colonne « Course » nécessaire.
Colonnes attendues dans le DataFrame : Annee, Nom ("NOM Prénom"), Sx ("Homme"/"Femme"), Club, Cat (code court : SE, M0...),
Temps_s (secondes ; vide si pas de temps : abandon...).
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import re
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (Image, KeepInFrame, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

# --- Réglages (identiques à ceux de l'application) ---------------------------
NOM_EVENT = "Marathon Vert Rennes"
TRANCHE_DEBUT, TRANCHE_FIN, TRANCHE_PAS = 150, 330, 10
CONFIG_TRANCHES = dict(debut=TRANCHE_DEBUT, fin=TRANCHE_FIN, pas=TRANCHE_PAS)
SOURCE = "lemarathonvert.org"   # affichée en pied de page

ORDRE_CAT = ["CA", "JU", "ES", "SE"] + [f"M{i}" for i in range(10)]
CAT_MAP = {"S": "SE", "E": "ES", "J": "JU", "C": "CA"}
SEXE_MAP = {"h": "Homme", "m": "Homme", "homme": "Homme", "masculin": "Homme",
            "f": "Femme", "femme": "Femme", "feminin": "Femme"}

FOND, VERT, ROUGE = HexColor("#0F2B30"), HexColor("#0d8c39"), HexColor("#C24247")
GRIS_CLAIR, GRIS_TEXTE = HexColor("#F2F4F4"), HexColor("#666666")
COUL_SEXE = {"Homme": ROUGE, "Femme": VERT}
# Une couleur par tranche de temps (la palette cycle si besoin). Remplace-les par celles de l'appli
# (PALETTE_TRANCHES) pour avoir exactement les mêmes teintes.
PALETTE_TRANCHES = [HexColor(c) for c in (
    "#3AB5B0", "#4FC3A1", "#8AD08A", "#C9D86A", "#F2D14B",
    "#F0A94A", "#E8804A", "#D9624A", "#C24247", "#8E2F3F")]
LARGEUR = A4[0] - 4 * cm - 12   # largeur utile (marges de 2 cm moins le padding interne du cadre)
HAUT_UTILE = A4[1] - 3.8 * cm - 14  # hauteur utile d'une page

# --- Utilitaires ---------------------------------------------------------------
def _norm(t) -> str:
    t = unicodedata.normalize("NFD", str(t)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _hms(s) -> str:
    if s is None or pd.isna(s):
        return "–"
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _min_txt(m: int) -> str:
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


def _pct(a, b) -> float:
    return 100 * a / b if b else 0.0


def _tranches(cfg: dict) -> tuple[list[int], list[str]]:
    """Bornes (minutes) et libellés : '< 1h10', '1h10-1h20', ..., '+ de 2h10'."""
    bornes = list(range(cfg["debut"], cfg["fin"] + 1, cfg["pas"]))
    lib = [f"< {_min_txt(bornes[0])}"]
    lib += [f"{_min_txt(a)}-{_min_txt(b)}" for a, b in zip(bornes, bornes[1:])]
    lib.append(f"+ de {_min_txt(bornes[-1])}")
    return bornes, lib


def _p(txt, style):
    return Paragraph(txt, style)


EXT_LOGO = (".webp", ".png", ".jpg", ".jpeg")


def _logo_auto() -> bytes | None:
    """Cherche un logo dans le dossier assets/ (à côté de ce fichier, puis du dossier courant).
    Un fichier dont le nom contient « logo » est prioritaire ; sinon, la première image trouvée."""
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        dossier = base / "assets"
        if not dossier.is_dir():
            continue
        fichiers = sorted(p for p in dossier.iterdir() if p.suffix.lower() in EXT_LOGO)
        fichiers.sort(key=lambda p: "logo" not in p.stem.lower())   # tri stable : « logo » d'abord
        if fichiers:
            return fichiers[0].read_bytes()
    return None


def _logo_png(data: bytes) -> io.BytesIO:
    """Convertit le logo (webp, png, jpg...) en PNG en mémoire : reportlab ne lit pas le WebP."""
    from PIL import Image as PILImage   # Pillow est déjà requis par reportlab pour les images
    with PILImage.open(io.BytesIO(data)) as im:
        buf = io.BytesIO()
        im.convert("RGBA").save(buf, format="PNG")
    buf.seek(0)
    return buf


# --- Styles --------------------------------------------------------------------
S_TITRE = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=FOND)
S_SOUS = ParagraphStyle("sous", fontName="Helvetica", fontSize=12, leading=16, textColor=GRIS_TEXTE)
S_H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=FOND, spaceBefore=4, spaceAfter=6)
S_H2C = ParagraphStyle("h2c", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=FOND, spaceBefore=6, spaceAfter=3)
S_H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=FOND, spaceBefore=10, spaceAfter=4)
S_TXT = ParagraphStyle("txt", fontName="Helvetica", fontSize=9.5, leading=13, textColor=FOND)
S_PUCE = ParagraphStyle("puce", parent=S_TXT, leftIndent=12, bulletIndent=2, spaceAfter=2)
S_NOTE = ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=8, leading=10, textColor=GRIS_TEXTE)
S_CELL_B = ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, textColor=colors.white)
S_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=FOND)
S_KPI_V = ParagraphStyle("kpiv", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=FOND, alignment=1)
S_KPI_L = ParagraphStyle("kpil", fontName="Helvetica", fontSize=8, leading=10, textColor=GRIS_TEXTE, alignment=1)


# --- Briques graphiques ----------------------------------------------------------
def _tableau(data, col_widths, entete=True, align_droite=(), pad=3):
    t = Table(data, colWidths=col_widths, repeatRows=1 if entete else 0, hAlign="LEFT")
    st = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), FOND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLAIR]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, HexColor("#CCCCCC")),
    ]
    if entete:
        st += [("BACKGROUND", (0, 0), (-1, 0), FOND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5)]
    for c in align_droite:
        st.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(st))
    return t


def _kpis(items):
    """Bandeau de chiffres clés : [(valeur, libellé), ...]."""
    ligne_v = [_p(v, S_KPI_V) for v, _ in items]
    ligne_l = [_p(l, S_KPI_L) for _, l in items]
    t = Table([ligne_v, ligne_l], colWidths=[LARGEUR / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLAIR),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white),
        ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _barres_tranches(labels, valeurs, couleurs, hauteur=6.5 * cm):
    """Histogramme des arrivants par tranche de temps (sexes confondus), une couleur par tranche,
    effectif au-dessus de chaque barre."""
    d = Drawing(LARGEUR, hauteur)
    c = VerticalBarChart()
    c.x, c.y, c.width, c.height = 30, 40, LARGEUR - 40, hauteur - 50
    c.data = [list(valeurs)]
    c.categoryAxis.categoryNames = labels
    c.categoryAxis.labels.fontName = "Helvetica"
    c.categoryAxis.labels.fontSize = 7
    c.categoryAxis.labels.angle = 30
    c.categoryAxis.labels.dy = -10
    c.categoryAxis.strokeColor = HexColor("#999999")
    c.categoryAxis.visibleTicks = False
    c.valueAxis.valueMin = 0
    c.valueAxis.valueMax = max(max(valeurs, default=0), 1) * 1.15
    c.valueAxis.visible = False
    c.valueAxis.visibleGrid = False
    c.groupSpacing = 10
    c.barLabelFormat = lambda v: f"{int(v):,}".replace(",", " ") if v else ""
    c.barLabels.fontSize = 8
    c.barLabels.fontName = "Helvetica-Bold"
    c.barLabels.fillColor = FOND
    c.barLabels.nudge = 7
    for i in range(len(valeurs)):
        c.bars[(0, i)].fillColor = couleurs[i % len(couleurs)]
        c.bars[(0, i)].strokeColor = None
    d.add(c)
    return d


# --- Calculs par course ----------------------------------------------------------
def _cle(df: pd.DataFrame) -> pd.Series:
    return df["Nom"].map(_norm)


def _analyse(d_all: pd.DataFrame, annee: int) -> dict:
    d = d_all[d_all["Annee"] == annee].copy()
    arr = d[d["Temps_s"].notna()]
    avant = d_all[d_all["Annee"] < annee]
    annee_prec = int(avant["Annee"].max()) if len(avant) else None
    n_prec = int((d_all["Annee"] == annee_prec).sum()) if annee_prec else None

    cles = _cle(d)
    deja = set(_cle(avant)) if len(avant) else set()
    revenants = int(cles.isin(deja).sum()) if deja else None

    records = {}
    for sx in ("Femme", "Homme"):
        a = arr[arr["Sx"] == sx]
        if a.empty:
            continue
        meilleur = a.loc[a["Temps_s"].idxmin()]
        ant = avant[(avant["Sx"] == sx) & avant["Temps_s"].notna()]
        ref = ant["Temps_s"].min() if len(ant) else None
        records[sx] = dict(temps=meilleur["Temps_s"], nom=meilleur["Nom"],
                           record=ref is None or meilleur["Temps_s"] < ref,
                           egal=ref is not None and meilleur["Temps_s"] == ref)
    return dict(d=d, arr=arr, annee_prec=annee_prec, n_prec=n_prec,
                revenants=revenants, records=records)


def _points_cles(a: dict, annee: int) -> list[str]:
    d, arr = a["d"], a["arr"]
    n, nf = len(d), int((d["Sx"] == "Femme").sum())
    out = [f"<b>{n}</b> participants, dont <b>{nf}</b> femmes ({_pct(nf, n):.0f} %)."]
    if a["n_prec"]:
        v = _pct(n - a["n_prec"], a["n_prec"])
        evol = "un effectif <b>stable</b>" if abs(v) < 0.5 else f"<b>{v:+.0f} %</b>"
        out[0] = out[0][:-1] + f", soit {evol} par rapport à {a['annee_prec']} ({a['n_prec']} participants)."
    if a["revenants"] is not None and n:
        out.append(f"<b>{_pct(a['revenants'], n):.0f} %</b> des participants avaient déjà couru l'épreuve "
                   f"(<b>{n - a['revenants']}</b> nouveaux visages).")
    for sx, lib in (("Femme", "féminin"), ("Homme", "masculin")):
        r = a["records"].get(sx)
        if r and r["record"] and a["annee_prec"]:
            out.append(f"Nouveau <b>record {lib}</b> de l'épreuve : {escape(str(r['nom']))} en <b>{_hms(r['temps'])}</b>.")
        elif r and r["egal"]:
            out.append(f"Record {lib} égalé : {escape(str(r['nom']))} en <b>{_hms(r['temps'])}</b>.")
    clubs = d[d["Club"].str.strip() != ""]["Club"].str.strip().value_counts()
    if len(clubs):
        out.append(f"Club le plus représenté : <b>{escape(clubs.index[0])}</b> ({int(clubs.iloc[0])} coureurs).")
    return out


# --- Sections du rapport ------------------------------------------------------------
def _section_course(d_all, annee, cfg, a) -> list:
    """Récap de l'édition : tient sur UNE page (mise en page compacte + réduction de sécurité)."""
    d, arr = a["d"], a["arr"]
    n, nf = len(d), int((d["Sx"] == "Femme").sum())
    el = [_p(f"Récap de l'édition {annee}", S_H1)]

    moy = arr["Temps_s"].mean()
    moy_f = arr.loc[arr["Sx"] == "Femme", "Temps_s"].mean()
    moy_h = arr.loc[arr["Sx"] == "Homme", "Temps_s"].mean()
    el.append(_kpis([
        (str(n), "participants"), (f"{_pct(nf, n):.0f} %", "de femmes"),
        (_hms(moy), "temps moyen"),
        (_hms(moy_f), "temps moyen femmes"), (_hms(moy_h), "temps moyen hommes"),
    ]))

    # Podiums
    el.append(_p("Podiums", S_H2C))
    cols = []
    for sx, titre in (("Femme", "Femmes"), ("Homme", "Hommes")):
        top = arr[arr["Sx"] == sx].nsmallest(3, "Temps_s")
        lignes = [[_p(titre, S_CELL_B), "", ""]]
        for i, r in enumerate(top.itertuples(), 1):
            lignes.append([str(i), _p(escape(str(r.Nom)), S_CELL), _hms(r.Temps_s)])
        t = _tableau(lignes, [0.7 * cm, (LARGEUR / 2 - 1.2 * cm) - 3.2 * cm, 2.2 * cm], align_droite=(2,), pad=2)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), COUL_SEXE[sx]), ("SPAN", (0, 0), (-1, 0))]))
        cols.append(t)
    duo = Table([cols], colWidths=[LARGEUR / 2, LARGEUR / 2])
    duo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (0, 0), 8), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    el.append(duo)

    # Répartition des temps officiels par tranche (sexes confondus)
    bornes, lib = _tranches(cfg)
    el.append(_p("Répartition des temps officiels (sexes confondus)", S_H2C))
    cnt = pd.cut(arr["Temps_s"] / 60, bins=[-np.inf] + bornes + [np.inf], labels=lib, right=False)
    nb = [int(v) for v in cnt.value_counts().reindex(lib, fill_value=0)]
    el.append(_barres_tranches(lib, nb, PALETTE_TRANCHES, hauteur=6.5 * cm))

    # Bas de page : catégories (gauche) | clubs + fidélité (droite)
    moitie = LARGEUR / 2
    gauche, droite = [], []
    cats = [c for c in ORDRE_CAT if c in set(d["Cat"])] + sorted(c for c in set(d["Cat"]) if c and c not in ORDRE_CAT)
    if cats:
        lignes = [["Catégorie", "F", "H", "Total", "Part"]]
        for c in cats:
            f = int(((d["Cat"] == c) & (d["Sx"] == "Femme")).sum())
            h = int(((d["Cat"] == c) & (d["Sx"] == "Homme")).sum())
            lignes.append([c, f, h, f + h, f"{_pct(f + h, n):.0f} %"])
        larg = moitie - 12
        gauche = [_p("Participation par catégorie", S_H2C),
                  _tableau(lignes, [larg * 0.28] + [larg * 0.18] * 4, align_droite=(1, 2, 3, 4), pad=1.5)]

    clubs = d[d["Club"].str.strip() != ""]["Club"].str.strip().value_counts().head(6)
    if len(clubs):
        lignes = [["Club", "Coureurs"]] + [[_p(escape(c), S_CELL), int(v)] for c, v in clubs.items()]
        larg = moitie - 12
        droite += [_p("Clubs les plus représentés", S_H2C),
                   _tableau(lignes, [larg - 2 * cm, 2 * cm], align_droite=(1,), pad=1.5)]
    if gauche or droite:
        bas = Table([[gauche or "", droite or ""]], colWidths=[moitie, moitie])
        bas.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (0, 0), 12), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        el.append(bas)

    # Fidélité : sous les deux tableaux, sur toute la largeur
    if a["revenants"] is not None:
        el += [_p("Fidélité", S_H2C),
               _p(f"<b>{a['revenants']}</b> participants ({_pct(a['revenants'], n):.0f} %) avaient déjà couru "
                  f"cette course ; <b>{n - a['revenants']}</b> la découvraient.", S_TXT)]

    # Garde-fou : si malgré tout le contenu dépasse (beaucoup de catégories, noms de clubs longs...),
    # il est légèrement réduit pour rester sur une seule page.
    return [KeepInFrame(LARGEUR, HAUT_UTILE, el, mode="shrink", hAlign="LEFT")]


# --- Bandeaux d'en-tête (le logo, souvent blanc, se détache sur le fond sombre) --------
H_COUV = 5.2 * cm        # hauteur du bandeau de la page 1
H_BANDEAU = 1.1 * cm     # hauteur du bandeau des pages suivantes
H_FILET = 0.25 * cm      # filet de couleur sous le bandeau de couverture


def _dessiner_logo(c, lecteur, x, y_centre, hauteur, max_largeur):
    """Dessine le logo (ratio conservé, transparence respectée) ; renvoie sa largeur."""
    w0, h0 = lecteur.getSize()
    hauteur = min(hauteur, max_largeur * h0 / w0)
    w = hauteur * w0 / h0
    c.drawImage(lecteur, x, y_centre - hauteur / 2, w, hauteur, mask="auto")
    return w


def _bandeau_couv(c, nom_event, annee, lecteur):
    W, H = A4
    y0 = H - H_COUV
    c.saveState()
    clip = c.beginPath()
    clip.rect(0, y0, W, H_COUV)
    c.clipPath(clip, stroke=0, fill=0)
    c.setFillColor(FOND)
    c.rect(0, y0, W, H_COUV, stroke=0, fill=1)
    c.setFillColor(VERT)                                   # cercles décoratifs translucides
    c.setFillAlpha(0.10)
    c.circle(W - 1.2 * cm, H - 0.4 * cm, 4.3 * cm, stroke=0, fill=1)
    c.setFillColor(VERT)
    c.setFillAlpha(0.16)
    c.circle(W - 5.4 * cm, y0 + 0.3 * cm, 1.7 * cm, stroke=0, fill=1)
    c.restoreState()

    c.saveState()                                          # filet teal sous le bandeau
    c.setFillColor(VERT)
    c.rect(0, y0 - H_FILET, W, H_FILET, stroke=0, fill=1)
    c.restoreState()

    c.saveState()
    yc, x = H - H_COUV / 2, 2 * cm
    if lecteur is not None:
        w = _dessiner_logo(c, lecteur, x, yc, 2.8 * cm, max_largeur=6.5 * cm)
        x += w + 0.9 * cm
        c.setStrokeColor(colors.white)
        c.setStrokeAlpha(0.35)
        c.setLineWidth(0.8)
        c.line(x - 0.45 * cm, yc - 1.2 * cm, x - 0.45 * cm, yc + 1.2 * cm)
        c.setStrokeAlpha(1)
    dispo = W - 2 * cm - x
    t = c.beginText(x, yc + 0.95 * cm)                     # petit libellé espacé
    t.setFont("Helvetica-Bold", 8.5)
    t.setCharSpace(2)
    t.setFillColor(VERT)
    t.textOut("BILAN DE L'ÉDITION")
    t.setCharSpace(0)                                      # ne pas déborder sur les textes suivants
    c.drawText(t)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 44)
    c.drawString(x, yc - 0.55 * cm, str(annee))
    taille = 12.0
    while stringWidth(nom_event, "Helvetica", taille) > dispo and taille > 7:
        taille -= 0.5
    c.setFillAlpha(0.85)
    c.setFont("Helvetica", taille)
    c.drawString(x, yc - 1.3 * cm, nom_event)
    c.restoreState()


def _bandeau_page(c, nom_event, annee, lecteur):
    W, H = A4
    c.saveState()
    c.setFillColor(FOND)
    c.rect(0, H - H_BANDEAU, W, H_BANDEAU, stroke=0, fill=1)
    c.setFillColor(VERT)
    c.rect(0, H - H_BANDEAU - 0.08 * cm, W * 1, 0.08 * cm, stroke=0, fill=1)
    yc = H - H_BANDEAU / 2
    if lecteur is not None:
        _dessiner_logo(c, lecteur, 2 * cm, yc, 0.7 * cm, max_largeur=3 * cm)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 2 * cm, yc - 2.8, f"{nom_event} · Bilan {annee}")
    c.restoreState()


def _pied(c, doc, nom_event, annee):
    c.saveState()
    c.setFont("Helvetica", 7.5)
    c.setFillColor(GRIS_TEXTE)
    c.drawString(2 * cm, 1.2 * cm, f"{nom_event} · Bilan {annee} · Source : résultats chronométriques ({SOURCE})")
    c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    c.restoreState()


# --- Point d'entrée -----------------------------------------------------------------
def generer_rapport(df: pd.DataFrame, annee: int, nom_event: str = NOM_EVENT, logo: bytes | None = None,
                    config: dict | None = None, *_args, **_kw) -> bytes:
    """PDF de bilan de l'édition `annee` : 1 page de synthèse + 1 page de récap détaillé.

    `config` (optionnel) : tranches de temps {"debut": 70, "fin": 150, "pas": 10} en minutes.
    Les arguments supplémentaires (ex. `courses`, hérités de l'appli multi-courses) sont ignorés.
    """
    cfg = config if config and "debut" in config else CONFIG_TRANCHES
    if not (df["Annee"] == annee).any():
        raise ValueError(f"Aucun résultat pour l'édition {annee}.")

    a = _analyse(df, annee)

    if logo is None:
        logo = _logo_auto()          # logo trouvé dans assets/ si aucun n'est fourni
    lecteur = None
    if logo:
        try:
            lecteur = ImageReader(_logo_png(logo))
        except Exception as e:
            print(f"Logo ignoré : {e}")

    # Le titre et le logo sont dessinés dans le bandeau pleine largeur (voir _bandeau_couv) :
    # on réserve juste la place sous le bandeau.
    el: list = [Spacer(1, H_COUV + H_FILET + 0.8 * cm - 1.8 * cm), _p("Points clés", S_H1)]
    for ligne in _points_cles(a, annee):
        el.append(Paragraph(ligne, S_PUCE, bulletText="•"))

    el += [Spacer(1, 14), _p(
        "Données issues des résultats publiés en ligne par le chronométreur ; les participants sont ceux "
        "figurant au classement (hors non-partants). Les temps sont les temps officiels (pistolet).", S_NOTE)]

    el.append(PageBreak())
    el += _section_course(df, annee, cfg, a)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=2 * cm, title=f"Bilan {annee} - {nom_event}", author=nom_event)
    def page_1(c, d):
        _bandeau_couv(c, nom_event, annee, lecteur)
        _pied(c, d, nom_event, annee)

    def pages_suivantes(c, d):
        _bandeau_page(c, nom_event, annee, lecteur)
        _pied(c, d, nom_event, annee)

    doc.build(el, onFirstPage=page_1, onLaterPages=pages_suivantes)
    return buf.getvalue()


# --- Ligne de commande ----------------------------------------------------------------
def _normaliser_cat(c) -> str:
    c = str(c).split(" - ")[0].strip().upper()
    m = re.fullmatch(r"([SEJC])[HF]", c)
    if m:
        return CAT_MAP[m.group(1)]
    return re.sub(r"^(\w{2})[HFM]$", r"\1", c)


RE_NON_PARTANT = r"\b(?:dns|non partant\w*|absent\w*|forfait\w*)\b"
RE_NON_ARRIVE = r"\b(?:dnf|abd|abandon\w*|dsq|disqualifi\w*|hors delai\w*|non classe\w*)\b"


def charger_csv(chemin: Path) -> pd.DataFrame:
    """Charge data/resultats.csv avec les mêmes normalisations que l'application."""
    df = pd.read_csv(chemin).rename(columns={"Sexe": "Sx", "Catégorie": "Cat"})
    for c in ("Nom", "Prénom", "Club", "Cat", "Sx", "Statut"):
        df[c] = df[c].fillna("").astype(str).str.strip() if c in df.columns else ""
    if (df["Prénom"] != "").any():                      # fichier avec Nom et Prénom séparés
        df["Nom"] = (df["Nom"] + " " + df["Prénom"]).str.strip()
    for c in ("Annee", "Temps_s"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Annee"]).copy()
    df["Annee"] = df["Annee"].astype(int)

    statut = df["Statut"].map(_norm)                    # non-partants exclus, abandons sans temps
    df = df[~statut.str.contains(RE_NON_PARTANT, regex=True)].copy()
    statut = df["Statut"].map(_norm)
    df.loc[statut.str.contains(RE_NON_ARRIVE, regex=True), "Temps_s"] = np.nan

    df["Sx"] = df["Sx"].map(lambda s: SEXE_MAP.get(_norm(s), s))
    df["Cat"] = df["Cat"].map(_normaliser_cat)
    cle = df["Nom"].map(_norm)
    forme = lambda s: max(s.value_counts().index, key=lambda n: (s.value_counts()[n], sum(ch.islower() for ch in n)))
    df["Nom"] = cle.map(df.groupby(cle)["Nom"].agg(forme))
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Génère le PDF de bilan d'une ou plusieurs éditions.")
    ap.add_argument("annees", nargs="*", type=int, help="éditions à produire (défaut : la dernière)")
    ap.add_argument("--toutes", action="store_true", help="produire toutes les éditions")
    ap.add_argument("--csv", default="data/resultats.csv")
    ap.add_argument("--out", default="rapports", help="dossier de sortie")
    ap.add_argument("--nom", default=NOM_EVENT, help="nom de l'événement")
    ap.add_argument("--logo", default=None, help="chemin d'un logo (png/jpg/webp) ; par défaut, celui du dossier assets/")
    args = ap.parse_args()

    df = charger_csv(Path(args.csv))
    dispo = sorted(df["Annee"].unique())
    annees = dispo if args.toutes else (args.annees or [dispo[-1]])
    logo = Path(args.logo).read_bytes() if args.logo else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for y in annees:
        chemin = out / f"rapport_{y}.pdf"
        chemin.write_bytes(generer_rapport(df, int(y), args.nom, logo))
        print("Rapport créé :", chemin)


if __name__ == "__main__":
    main()