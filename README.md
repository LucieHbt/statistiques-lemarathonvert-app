# ⏱️ Le Marathon Vert Rennes · Statistiques

Tableau de bord interactif des résultats chronométriques du Marathon Vert (éditions 2019 à 2026), réalisé avec [Streamlit](https://streamlit.io).

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://statistiques-lemarathonvert-app.streamlit.app/)

## Fonctionnalités

L'application comporte trois onglets : **Général** (vue d'ensemble de toutes les éditions), **Édition** (détail d'une édition au choix) et **Individuel** (suivi d'un coureur).

### 📊 Général

Vue d'ensemble sur toutes les éditions et toutes les catégories confondues.

- **Records** féminin et masculin (depuis 1994) avec le nom du détenteur et l'année, et **plus grand nombre de participations**.
- **Podiums des participations** : les 3 coureuses et les 3 coureurs les plus fidèles, classés par nombre d'éditions.
- **Évolution entre les éditions**, au choix :
  - *Nombre* : nombre de coureurs par édition, hommes et femmes ;
  - *Densité* : part des arrivants par tranche de 10 minutes, année après année (barres empilées à 100 %).

### 👟 Édition

Détail d'une édition, à choisir parmi toutes les éditions disponibles.

- **Sélecteur d'édition**, à droite des onglets : liste déroulante avec recherche (taper une année pour la retrouver) et flèches ‹ › pour passer à l'édition précédente ou suivante.
- **Indicateurs clés** : nombre de participants, d'hommes et de femmes, avec le temps moyen de chacun.
- **Filtre par catégorie** (Scratch, CA, JU, ES, SE, M0 à M9), propre à l'édition choisie, appliqué aux podiums et aux graphiques de distribution.
- **Podiums** hommes et femmes, avec gestion des ex æquo.
- **Distribution des temps officiels**, au choix :
  - *Courbe* : densité de coureurs par sexe, sur les temps pistolet, avec un axe gradué toutes les 10 minutes ;
  - *Tranches* : nombre de coureurs par tranche de performance de 10 minutes (de "< 1h10" à "> 2h30").
- **Répartition hommes / femmes** sous forme d'anneau.

### 🏃 Individuel

- **Recherche d'un coureur** par nom ou prénom, dans n'importe quel ordre, sans tenir compte des accents ni des majuscules. En cas d'homonymes, une liste permet de choisir le bon coureur.
- **Indicateurs personnels** : nombre d'éditions courues, meilleur temps (avec son année) et nombre de médailles (or, argent, bronze) obtenues sur les podiums au scratch.
- **Évolution des performances** : graphique du temps de chaque édition, avec le meilleur temps mis en évidence. Les libellés s'inclinent quand le coureur a beaucoup de participations.
- **Détail par édition** : temps, place au scratch, place chez les hommes ou les femmes, catégorie et médaille éventuelle.
- **Carte récap en PDF** : chaque coureur peut télécharger une carte (format A5) avec son nom, le logo de la course, ses chiffres clés et l'évolution de ses temps sur les éditions courues.

Les couleurs suivent partout la même règle : **rouge pour les hommes, vert pour les femmes**.

## Structure du dépôt

```
.
├── streamlit_app.py     # application Streamlit
├── carte_pdf.py         # génération de la carte récap (PDF, reportlab)
├── rapport_pdf.py       # génération du rapport de l'édition sélectionnée (PDF, reportlab)
├── assets/              # images utiles (fond et logo)
├── data/                # résultats chronométriques (une ligne par coureur)
├── pyproject.toml       # dépendances (uv)
└── README.md
```

### Format des données

`data/resultats.csv` contient une ligne par coureur, avec les colonnes :

| Colonne       | Description                                                        |
|---------------|--------------------------------------------------------------------|
| `Annee`       | Édition de la course                                               |
| `Statut`      | FINISHER, DNF, DNS                                                 |
| `Classement`  | FINISHER, DNF, DNS                                                 |
| `Nom`         | Nom                                                                |
| `Prénom`      | Prénom                                                             |
| `Sexe`        | Sexe : `M`, `F` ou `X`                                             |
| `Club`        | Club ou association (peut être vide)                               |
| `Cat`         | Catégorie (`SE`, `M0`…)                                            |
| `Temps_s`     | Temps officiel en secondes > vide pour les DNF et DNS              |

Les abandons sont comptés parmi les participants mais exclus des moyennes, des courbes, des tranches et des podiums.

## Crédits

- Résultats chronométriques : [résultats du Marathon Vert](https://www.lemarathonvert.org/resultats.php)
- Construit avec [Streamlit](https://streamlit.io), [pandas](https://pandas.pydata.org), [Plotly](https://plotly.com/python/) et [ReportLab](https://docs.reportlab.com/) pour la carte PDF.