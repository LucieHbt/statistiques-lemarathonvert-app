"""Transforme marathon_vert_rennes_all.xlsx (une feuille = une édition) en data/resultats.csv"""
import datetime as dt
import os
import sys

import pandas as pd

src = sys.argv[1] if len(sys.argv) > 1 else "data/marathon_vert_rennes_all.xlsx"


def to_seconds(v):
    if isinstance(v, (dt.time, dt.datetime)):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, dt.timedelta):
        return v.total_seconds()
    if isinstance(v, str):
        p = v.strip().split(":")
        if len(p) == 3 and all(q.isdigit() for q in p):
            return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])
    return float("nan")  # DNF, vide...


def clean_header(c):
    return str(c).replace("\xa0", " ").strip()


def get(d, *names):
    """Première colonne trouvée parmi `names`, sinon une série vide (NaN)."""
    for n in names:
        if n in d.columns:
            return d[n]
    return pd.Series([float("nan")] * len(d), index=d.index)


def text(s):
    return (
        s.astype("string").str.replace("\xa0", " ", regex=False).str.strip().fillna("")
    )


def num(s):
    return pd.to_numeric(s, errors="coerce").astype("Int64")


frames = []
x = pd.ExcelFile(src)
for sheet in x.sheet_names:
    d = x.parse(sheet)
    d.columns = [clean_header(c) for c in d.columns]
    out = pd.DataFrame({
        "Annee": int(sheet),
        "Statut": text(get(d, "Statut")),
        "Classement": num(get(d, "Classement")),
        "Dossard": num(get(d, "Dossard")),
        "Nom": text(get(d, "Nom")),
        "Prénom": text(get(d, "Prénom")),
        "Sexe": text(get(d, "Sexe")),
        "Club": text(get(d, "Club")),
        "Catégorie": text(get(d, "Catégorie", "Cat")),
        "Classement_Cat": num(get(d, "Classement Catégorie")),
        "Temps_s": get(d, "Temps Officiel").map(to_seconds),
        "Temps_reel_s": get(d, "Temps Réel").map(to_seconds),
        "Classement_Semi": num(get(d, "Classement SEMI")),
        "Semi_s": get(d, "SEMI").map(to_seconds),
        "Classement_30km": num(get(d, "Classement 30Km")),
        "Km30_s": get(d, "30Km").map(to_seconds),
    })
    frames.append(out)

df = pd.concat(frames, ignore_index=True)
os.makedirs("data", exist_ok=True)
df.to_csv("data/resultats.csv", index=False)
print(df.groupby("Annee").agg(coureurs=("Nom", "size"), arrivants=("Temps_s", "count")))