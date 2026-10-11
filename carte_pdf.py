"""Carte récap (PDF) d'un coureur
Dépendance : reportlab (pur Python ; Pillow est installé avec lui)
"""
from __future__ import annotations

import io
from functools import lru_cache
from typing import Sequence

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

FOND = HexColor("#0F2B30")
GRIS = HexColor("#6B6B6B")
OR = HexColor("#E0B400")
ARGENT = HexColor("#9A9A9A")
BRONZE = HexColor("#E8743B")

# Dégradé posé sur la photo, de haut en bas (mêmes couleurs que le fond de l'application,
# mais voile plus léger : opacité .20 -> .40 au lieu de .40 -> .60, pour mieux voir la photo)
DEGRADE_HAUT = (1 / 255, 114 / 255, 132 / 255, 0.20)
DEGRADE_BAS = (13 / 255, 43 / 255, 48 / 255, 0.40)


def _hms(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _hm(s: float) -> str:
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}"


def _medaille(c: canvas.Canvas, cx: float, cy: float, r: float, couleur) -> None:
    """Petite médaille dessinée (ruban + disque) – aucun emoji, donc rien à installer."""
    c.setFillColor(couleur)
    c.setStrokeColor(couleur)
    p = c.beginPath()
    p.moveTo(cx - r * 0.75, cy + r * 1.55)
    p.lineTo(cx - r * 0.1, cy + r * 0.45)
    p.lineTo(cx + r * 0.1, cy + r * 0.45)
    p.lineTo(cx + r * 0.75, cy + r * 1.55)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.circle(cx, cy, r, stroke=0, fill=1)
    c.setFillColor(white)
    c.circle(cx, cy, r * 0.55, stroke=0, fill=1)
    c.setFillColor(couleur)
    c.circle(cx, cy, r * 0.32, stroke=0, fill=1)


@lru_cache(maxsize=4)
def _jpeg_fond(photo: bytes | None, w: float, h: float) -> bytes:
    """Fond de la carte, calculé avec Pillow : photo "cover" + dégradé translucide
    Le dégradé est fusionné dans l'image (un seul JPEG) : pas de bandes ni de transparence PDF
    """
    from PIL import Image

    px = 3                                    # pixels par point : net à l'impression
    W, H = int(w * px), int(h * px)
    base = None
    if photo:
        try:
            im = Image.open(io.BytesIO(photo)).convert("RGB")
            k = max(W / im.width, H / im.height)           # background-size: cover
            im = im.resize((max(W, round(im.width * k)), max(H, round(im.height * k))))
            gx, gy = (im.width - W) // 2, (im.height - H) // 2
            base = im.crop((gx, gy, gx + W, gy + H))
        except Exception:
            base = None
    if base is not None:
        haut, bas = DEGRADE_HAUT, DEGRADE_BAS
    else:                                      # repli sans photo : même dégradé, opaque
        base = Image.new("RGB", (W, H), (0, 0, 0))
        haut, bas = (14 / 255, 111 / 255, 126 / 255, 1.0), (13 / 255, 43 / 255, 48 / 255, 1.0)
    rampe = Image.new("RGBA", (1, H))
    rampe.putdata([
        tuple(round(255 * (haut[j] + (bas[j] - haut[j]) * y / (H - 1))) for j in range(4))
        for y in range(H)
    ])
    voile = rampe.resize((W, H))
    base = Image.alpha_composite(base.convert("RGBA"), voile).convert("RGB")
    out = io.BytesIO()
    base.save(out, "JPEG", quality=88)
    return out.getvalue()


def _image_fond(photo: bytes | None, w: float, h: float) -> ImageReader:
    return ImageReader(io.BytesIO(_jpeg_fond(photo, w, h)))

def _fond_carte(c: canvas.Canvas, x: float, y: float, w: float, h: float, r: float, photo: bytes | None) -> None:
    c.saveState()
    clip = c.beginPath()
    clip.roundRect(x, y, w, h, r)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(_image_fond(photo, w, h), x, y, w, h)
    c.restoreState()

def generer_carte(
    *,
    prenom: str,
    nom: str,
    sexe: str,
    club: str,
    annees: Sequence[int],
    resultats: Sequence[tuple[int, float | None]],
    couleur: str,
    medailles: dict[int, int],
    logo: bytes | None = None,
    fond: bytes | None = None,
    titre_event: str = "Semi-Marathon de Cancale Saint-Malo",
) -> bytes:
    """Retourne le PDF (format A5 portrait) sous forme de bytes.

    resultats : [(année, temps en secondes ou None si abandon)] pour les éditions courues.
    medailles : {1: nb d'or, 2: nb d'argent, 3: nb de bronze}.
    couleur   : contour de la carte (rouge si homme, teal si femme).
    logo      : image du logo (affiché au-dessus du nom, sans cadre) – facultatif.
    fond      : photo de fond (celle de l'application) – facultative.
    """
    col = HexColor(couleur)
    buf = io.BytesIO()
    W, H = A5
    c = canvas.Canvas(buf, pagesize=A5)
    c.setTitle(f"Carte récap – {prenom} {nom}")
    c.setAuthor(titre_event)

    # ---- cadre + fond -------------------------------------------------
    m = 16
    _fond_carte(c, m, m, W - 2 * m, H - 2 * m, 30, fond)
    c.setStrokeColor(col)
    c.setLineWidth(5)
    c.roundRect(m, m, W - 2 * m, H - 2 * m, 30, stroke=1, fill=0)
    cx = W / 2

    # ---- logo (au-dessus du nom, sans cercle) -------------------------
    bw, bh = 190, 84                    # boîte dans laquelle le logo est ajusté
    haut_logo = H - m - 22
    y_nom = haut_logo - bh - 24
    if logo:
        try:
            img = ImageReader(io.BytesIO(logo))
            iw, ih = img.getSize()
            k = min(bw / iw, bh / ih)
            c.drawImage(img, cx - iw * k / 2, haut_logo - bh / 2 - ih * k / 2, iw * k, ih * k, mask="auto")
        except Exception:
            logo = None
    if not logo:  # repli : texte à la place du logo
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(cx, haut_logo - bh / 2 + 6, "SEMI-MARATHON")
        c.setFont("Helvetica", 10)
        c.drawCentredString(cx, haut_logo - bh / 2 - 10, "CANCALE – SAINT-MALO")

    # ---- nom ----------------------------------------------------------
    c.setFillColor(white)
    taille = 22
    texte = f"{prenom} {nom.upper()}".strip()
    while c.stringWidth(texte, "Helvetica-BoldOblique", taille) > W - 2 * m - 30 and taille > 11:
        taille -= 1
    c.setFont("Helvetica-BoldOblique", taille)
    c.drawCentredString(cx, y_nom, texte)
    c.setFont("Helvetica", 9.5)
    sous = sexe + (f" · {club}" if club else "")
    while c.stringWidth(sous, "Helvetica", 9.5) > W - 2 * m - 30 and len(sous) > 8:
        sous = sous[:-2]
    c.drawCentredString(cx, y_nom - 16, sous)

    # ---- KPI ----------------------------------------------------------
    n_ed = len(resultats)
    temps = [(t, a) for a, t in resultats if t is not None]
    best = min(temps) if temps else None
    n_med = sum(medailles.values())
    kpis = [("ÉDITIONS", str(n_ed), "")]
    if n_med:
        kpis.append(("MÉDAILLES", str(n_med), ""))
    kpis.append(("MEILLEUR TEMPS", _hms(best[0]) if best else "–", f"en {best[1]}" if best else ""))

    kh = 72
    ky_top = y_nom - 16 - 18
    kx, kw = m + 18, W - 2 * m - 36
    c.setStrokeColor(col)
    c.setLineWidth(2.2)
    c.setFillColor(white)
    c.roundRect(kx, ky_top - kh, kw, kh, 12, stroke=1, fill=1)
    poids = [1.0] * (len(kpis) - 1) + [1.55]
    tot = sum(poids)
    x0 = kx
    for i, (lab, val, det) in enumerate(kpis):
        w = kw * poids[i] / tot
        mid = x0 + w / 2
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawCentredString(mid, ky_top - 20, lab)
        c.setFillColor(FOND)
        c.setFont("Helvetica-Bold", 22 if i < len(kpis) - 1 or len(val) < 6 else 20)
        c.drawCentredString(mid, ky_top - 46, val)
        if lab == "MÉDAILLES":
            sym = [(1, OR), (2, ARGENT), (3, BRONZE)]
            presents = [(p, col_m) for p, col_m in sym if medailles.get(p)]
            txt_w = 22
            total_w = len(presents) * txt_w
            xs = mid - total_w / 2 + 6
            for p, col_m in presents:
                _medaille(c, xs, ky_top - 60, 4, col_m)
                c.setFillColor(GRIS)
                c.setFont("Helvetica-Bold", 7.5)
                c.drawString(xs + 7, ky_top - 62, f"x{medailles[p]}")
                xs += txt_w
        elif det:
            c.setFillColor(GRIS)
            c.setFont("Helvetica", 8)
            c.drawCentredString(mid, ky_top - 60, det)
        if i:
            c.setStrokeColor(Color(col.red, col.green, col.blue, alpha=0.35))
            c.setLineWidth(0.8)
            c.line(x0, ky_top - 12, x0, ky_top - kh + 12)
        x0 += w

    # ---- graphique d'évolution ---------------------------------------
    gy_top = ky_top - kh - 16
    gy_bot = m + 44
    gx, gw = kx, kw
    gh = gy_top - gy_bot
    c.setStrokeColor(col)
    c.setLineWidth(2.2)
    c.setFillColor(white)
    c.roundRect(gx, gy_bot, gw, gh, 12, stroke=1, fill=1)
    c.setFillColor(FOND)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(gx + gw / 2, gy_top - 17, "Évolution des temps")

    px0, px1 = gx + 46, gx + gw - 22          # zone de tracé
    py0, py1 = gy_bot + 28, gy_top - 40
    pts = [(a, t) for a, t in resultats if t is not None]
    toutes = sorted(annees)                                   # toutes les éditions (pied de carte)
    ordre = sorted({a for a, _ in resultats}) or toutes      # axe : seulement les éditions courues
    xpos = {a: px0 + (px1 - px0) * (i + 0.5) / len(ordre) for i, a in enumerate(ordre)}
    biseau = len(ordre) > 6 
    if pts:
        vals = [t for _, t in pts]
        marge = max(120, (max(vals) - min(vals)) * 0.3)
        pas = 300 if (max(vals) - min(vals) + 2 * marge) < 3600 else 600
        lo = int((min(vals) - marge) // pas * pas)
        hi = int(-(-(max(vals) + marge) // pas) * pas)
        fy = lambda t: py0 + (t - lo) / (hi - lo) * (py1 - py0)
        # grille + graduations
        c.setFont("Helvetica", 7)
        for v in range(lo, hi + 1, pas):
            c.setStrokeColor(HexColor("#E3E8EA"))
            c.setLineWidth(0.6)
            c.line(px0 - 4, fy(v), px1, fy(v))
            c.setFillColor(GRIS)
            c.drawRightString(px0 - 8, fy(v) - 2.4, _hm(v))
        # courbe
        c.setStrokeColor(col)
        c.setLineWidth(2.2)
        pts_xy = [(xpos[a], fy(t)) for a, t in sorted(pts)]
        for (xa, ya), (xb, yb) in zip(pts_xy, pts_xy[1:]):
            c.line(xa, ya, xb, yb)
        ibest = min(range(len(pts)), key=lambda k: sorted(pts)[k][1])
        for k, ((a, t), (xx, yy)) in enumerate(zip(sorted(pts), pts_xy)):
            c.setFillColor(OR if k == ibest else col)
            c.setStrokeColor(white)
            c.setLineWidth(1.2)
            c.circle(xx, yy, 4.6 if k == ibest else 3.6, stroke=1, fill=1)
            c.setFillColor(FOND)
            c.setFont("Helvetica-Bold", 7)
            if biseau:
                c.saveState()
                c.translate(xx - 1, yy + 6)
                c.rotate(45)
                c.drawString(0, 0, _hms(t))
                c.restoreState()
            else:
                c.drawCentredString(xx, yy + 8, _hms(t))
                
    for a in ordre:
        if biseau:
            c.saveState()
            c.translate(xpos[a] + 3, gy_bot + 24)
            c.rotate(45)
            c.drawRightString(0, 0, str(a))
            c.restoreState()
        else:
            c.drawCentredString(xpos[a], gy_bot + 12, str(a))

    # ---- pied de carte -----------------------------------------------
    c.setFillColor(white)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(cx, m + 22, titre_event)
    c.showPage()
    c.save()
    return buf.getvalue()