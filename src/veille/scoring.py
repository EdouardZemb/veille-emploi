"""Moteur de score.

Principe : chaque regle produit une `Contribution` (libelle, points, detail).
Le score est leur somme. L'explication affichee dans la console EST la liste
des contributions - il n'y a pas de calcul cache derriere.

Une regle eliminatoire ne met pas le score a zero : elle marque l'offre
`rejete_auto` avec un motif, et le score reste calcule pour que tu puisses
verifier, en la depliant, que le rejet est justifie.
"""

from __future__ import annotations

import logging
import re

from .config import Criteres, charger_criteres, contient, normaliser
from .models import Contribution, Offre

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Detection du pays (choisit le bareme salarial applique)
# --------------------------------------------------------------------------

# Pays pour lesquels il a un bareme salarial et des pieces de candidature.
PAYS_SERVIS = ("france", "suisse")

# Les lieux de chaque pays vivent dans `geographie.pays` de `criteres.yaml`,
# que `veille config verifier` exige.


def detecter_pays(offre: Offre, criteres: "Criteres | None" = None) -> str:
    """'suisse' | 'france' | 'allemagne' | 'autre' — ou '' si on ne sait pas.

    LA CHAINE VIDE EST UN RESULTAT. L'ancienne version rendait deux valeurs,
    « suisse » ou « france », avec France par defaut.
    Une offre a Hambourg, a Londres ou a Varsovie etait donc francaise.

    Mesure du 02/10/2026 sur la base, verite terrain etablie
    independamment : une part notable des offres hors France et hors Suisse
    etaient classees « france », et des annonces dont le lieu ne dit rien —
    « Remote », une ville absente des listes — l'etaient aussi, en silence.
    Moins de la moitie etaient justes.

    C'est le meme defaut que pour la langue, et la meme correction : une
    absence d'indice ne doit pas etre presentee comme une certitude.

    LE LIEU D'ABORD, l'employeur ensuite. Un employeur bale-ois peut recruter
    a Berlin ; c'est le lieu qui dit ou le poste se tient.
    """
    c = criteres or charger_criteres()
    listes = (c.brut.get("geographie", {}) or {}).get("pays") or {}

    if offre.salaire_devise and offre.salaire_devise.upper() == "CHF":
        return "suisse"

    for champ in (offre.lieu, offre.employeur):
        cible = normaliser(champ or "")
        if not cible.strip():
            continue
        for pays, motifs in listes.items():
            if any(contient(cible, m) for m in motifs):
                return pays
    return ""


def bareme_applicable(pays: str) -> str:
    """Le bareme salarial a appliquer pour ce pays.

    Il n'a de planchers que pour la France et la Suisse. Pour un poste
    ailleurs, ou dont le pays est indetermine, on applique le bareme francais
    — mais `scorer` ECRIT qu'il l'a fait. C'est la difference avec l'ancien
    comportement : le repli existe toujours, il ne se cache plus.
    """
    return pays if pays in PAYS_SERVIS else "france"




# --------------------------------------------------------------------------
# Duree de mission (pour la regle d'interim suisse)
# --------------------------------------------------------------------------

_RE_DUREE = [
    (re.compile(r"(\d{1,2})\s*(?:a|-|to|bis)\s*(\d{1,2})\s*mois"), "mois_plage"),
    (re.compile(r"(\d{1,2})\s*mois"), "mois"),
    (re.compile(r"(\d{1,2})\s*monate?"), "mois"),
    (re.compile(r"(\d{1,2})\s*months?"), "mois"),
    (re.compile(r"(\d{1,2})\s*(?:ans?|annees?|years?|jahre?)"), "annees"),
    (re.compile(r"(\d{1,3})\s*(?:semaines?|weeks?|wochen)"), "semaines"),
]


def detecter_duree_mois(offre: Offre) -> int | None:
    """Duree de mission en mois, si l'annonce la donne."""
    if offre.duree_mois is not None:
        return offre.duree_mois
    texte = normaliser(offre.texte_complet)
    for regex, genre in _RE_DUREE:
        m = regex.search(texte)
        if not m:
            continue
        if genre == "mois_plage":
            # On retient la borne basse : c'est l'engagement reellement garanti.
            return int(m.group(1))
        valeur = int(m.group(1))
        if genre == "mois":
            return valeur
        if genre == "annees":
            return valeur * 12
        if genre == "semaines":
            return max(1, round(valeur / 4.33))
    return None


def est_interim(offre: Offre, criteres: Criteres) -> bool:
    texte = normaliser(f"{offre.type_contrat} {offre.titre} {offre.description}")
    return any(contient(texte, m) for m in criteres.contrat.get("interim_motifs", []))


# --------------------------------------------------------------------------
# Recherche de motifs ponderee intitule / description
# --------------------------------------------------------------------------


def _meilleur_groupe(
    offre: Offre, groupes: dict, poids_description: float
) -> tuple[str, float, str]:
    """Retourne (cle_du_groupe, points, motif_trouve) pour le meilleur match.

    Un motif dans l'intitule vaut le poids plein ; dans la description il vaut
    `poids_description` fois moins. On garde le groupe qui rapporte le plus.
    """
    titre = normaliser(offre.titre)
    reste = normaliser(f"{offre.description} {offre.lieu} {offre.employeur}")

    meilleur: tuple[str, float, str] = ("", 0.0, "")
    for cle, groupe in groupes.items():
        poids = float(groupe.get("poids", 0))
        for motif in groupe.get("motifs", []):
            if contient(titre, motif):
                points, ou = poids, "intitule"
            elif contient(reste, motif):
                points, ou = poids * poids_description, "description"
            else:
                continue
            if abs(points) > abs(meilleur[1]):
                meilleur = (cle, points, f'"{motif}" dans l\'{ou}')
    return meilleur


# --------------------------------------------------------------------------
# Regles
# --------------------------------------------------------------------------


def _regle_famille(offre: Offre, c: Criteres, pd: float, contribs: list[Contribution]) -> str:
    # Une famille qu'il a validee prime sur la detection : c'est sa decision,
    # et elle existe justement parce qu'aucun motif ne collait. Les points
    # restent ceux du groupe dans criteres.yaml — rien n'est invente ici.
    validee = getattr(offre, "famille_validee", "") or ""
    if validee and validee in c.familles:
        groupe = c.familles[validee]
        libelle = groupe.get("libelle", validee)
        contribs.append(Contribution(f"Famille : {libelle}",
                                     float(groupe.get("poids", 0)),
                                     "famille que tu as validée toi-même"))
        return validee

    cle, points, detail = _meilleur_groupe(offre, c.familles, pd)
    if not cle:
        contribs.append(
            Contribution("Aucune famille de métier reconnue", 0, "l'intitule ne correspond a aucun de tes metiers cibles")
        )
        return ""
    libelle = c.familles[cle].get("libelle", cle)
    contribs.append(Contribution(f"Famille : {libelle}", points, detail))
    return cle


def _texte_sans_bruit(offre: Offre, geo: dict) -> str:
    """Description debarrassee du texte ajoute par l'agregateur.

    Arbeitnow colle en fin de description « Find Jobs in Switzerland on
    Arbeitnow Full remote possible. » — une phrase qui parle de son site, pas
    du poste. Sans ce nettoyage, plusieurs offres presentielles passaient pour
    du teletravail complet.
    """
    texte = offre.description or ""
    for motif in geo.get("bruit_agregateur", []):
        try:
            texte = re.sub(motif, " ", texte, flags=re.IGNORECASE)
        except re.error:
            log.warning("bruit_agregateur : expression invalide, ignoree : %s", motif)
    return texte


# Correspondance entre une exigence validee et le niveau de teletravail du
# scoring. Table explicite : une exigence ne doit jamais pouvoir produire un
# niveau que le scoring ne connait pas.
_NIVEAU_PAR_TELETRAVAIL = {"complet": "complet", "hybride": "partiel",
                           "aucun": "presentiel"}


def _teletravail_force(offre: Offre) -> tuple[str, str] | None:
    """Le niveau impose par une exigence validee, ou None.

    `jours_sur_site` est plus precis que `teletravail` : s'il a valide les
    deux, c'est le nombre de jours qui tranche.
    """
    exig = getattr(offre, "exigences", None) or {}

    jours = exig.get("jours_sur_site")
    if jours and str(jours.get("valeur", "")).isdigit():
        n = int(jours["valeur"])
        niveau = "complet" if n == 0 else ("presentiel" if n >= 5 else "partiel")
        return niveau, (f'exigence que tu as validée : {n} jour(s) sur site — '
                        f'« {jours.get("citation", "")} »')

    mode = exig.get("teletravail")
    if mode and mode.get("valeur") in _NIVEAU_PAR_TELETRAVAIL:
        return (_NIVEAU_PAR_TELETRAVAIL[mode["valeur"]],
                f'exigence que tu as validée : télétravail {mode["valeur"]} — '
                f'« {mode.get("citation", "")} »')
    return None


def detecter_teletravail(offre: Offre, c: Criteres) -> tuple[str, str]:
    """('complet' | 'partiel' | 'presentiel' | 'inconnu', preuve).

    Quatre niveaux, et le quatrieme compte autant que les autres :

    - `complet`    : engagement ferme, et aucune exigence de presence.
    - `partiel`    : hybride, N jours sur site.
    - `presentiel` : presence a temps plein exigee explicitement.
    - `inconnu`    : l'annonce ne dit rien. **On ne suppose pas du presentiel** :
      la plupart des annonces sont muettes sur le sujet, et assimiler le
      silence a une exigence ecarterait la moitie du Grand Est.

    Un engagement de teletravail complet ne se deduit pas d'un mot isole : il
    faut une formulation ferme ET aucune exigence de presence. C'est la seconde
    condition qui manquait — « remote-first culture with hybrid options (office
    in Zurich) » etait compte comme du 100% distant, et l'offre est arrivee en
    tete de liste.
    """
    # Une exigence qu'il a VALIDEE prime sur la detection par motifs. C'est
    # tout l'interet du releve : « zwei Tage pro Woche vor Ort » ne ressemble
    # a aucun motif de la liste, et l'offre passait pour muette.
    forcee = _teletravail_force(offre)
    if forcee:
        return forcee

    geo = c.brut.get("geographie", {})
    # Le champ LIEU porte souvent le mode de travail : « France (A distance) »,
    # « Bale (Hybride) », « Mulhouse (Sur site) ». Ne pas le lire faisait
    # ecarter des offres en teletravail complet, un mode de travail que les
    # criteres peuvent valoriser.
    texte = normaliser(
        f"{_texte_sans_bruit(offre, geo)} {offre.titre} {offre.type_contrat} {offre.lieu}"
    )
    lieu = normaliser(offre.lieu)

    # Ordre d'examen : du motif le plus SPECIFIQUE au plus general.
    # L'hybride d'abord : « 2 jours sur site par semaine » contient « sur site »,
    # qui signale par ailleurs une presence a temps plein. Tester le general en
    # premier faisait passer un poste hybride pour du presentiel integral, et
    # ecartait Strasbourg a tort.
    partielle = next((m for m in geo.get("presence_partielle_motifs", []) if contient(texte, m)), "")
    if partielle:
        return "partiel", f'"{partielle}" : presence reguliere sur site'

    totale = next((m for m in geo.get("presence_totale_motifs", []) if contient(texte, m)), "")
    if totale:
        return "presentiel", f'"{totale}" : presence a temps plein exigee'

    ferme = next((m for m in geo.get("teletravail_complet_motifs", []) if contient(texte, m)), "")
    if ferme:
        return "complet", f'"{ferme}"'

    # Un champ "lieu" qui ne dit que « Remote » vaut engagement.
    if lieu.strip() and all(
        mot in ("remote", "anywhere", "teletravail", "distance", "a", "-", "home")
        for mot in lieu.split()
    ):
        return "complet", f"lieu annonce : {offre.lieu}"

    return "inconnu", ""


def _zone_du_lieu(offre: Offre, c: Criteres) -> tuple[str, float, str, str]:
    """(cle, points, detail, acces) de la zone geographique, d'apres le LIEU.

    On ignore `teletravail_total`, qui n'est pas un lieu mais un mode de
    travail : il est decide par `detecter_teletravail`.
    """
    cible = normaliser(f"{offre.lieu} {offre.titre}")
    for cle, groupe in c.zones.items():
        if not groupe.get("acces"):
            continue
        for motif in groupe.get("motifs", []):
            if contient(cible, motif):
                return (
                    cle,
                    float(groupe.get("poids", 0)),
                    f'"{motif}" dans le lieu annonce',
                    groupe.get("acces", ""),
                )
    return "", 0.0, "", ""


def lieu_imprecis(offre: Offre, c: Criteres) -> tuple[str, float, str]:
    """Le lieu designe-t-il une region entiere, sans ville ?

    « Grand Est, France (Sur site) » couvre aussi bien une ville voisine qu'une
    ville a l'autre bout de la region. On ne peut ni l'ecarter sur la distance,
    ni lui donner les points d'une zone atteignable.

    Deux grains, qui n'ont pas la meme valeur : sa region reste une information
    positive meme imprecise ; « France entiere » ne dit rien du tout.

    Rend (motif, poids, groupe). Motif vide si le lieu est exploitable : un lieu
    n'est imprecis que s'il ne reste RIEN apres avoir retire le bruit et le
    motif, donc « Mulhouse, Grand Est » reste precis.
    """
    geo = c.brut.get("geographie", {})
    groupes = geo.get("lieux_imprecis", {})
    if not groupes:
        return "", 0.0, ""
    # ORDRE : les motifs D'ABORD, le bruit ensuite. « France entiere » est un
    # motif qui contient le mot de bruit « france » : retirer le bruit en
    # premier le couperait en deux et il ne serait jamais reconnu. Meme piege
    # que pour la detection du teletravail — du plus specifique au plus general.
    reste = normaliser(offre.lieu)

    # LE PLUS LONG D'ABORD. « bourgogne franche comte » contient « franche
    # comte » : examiner le court en premier le consomme, laisse « bourgogne »
    # en residu, et le lieu n'est plus reconnu du tout. C'est exactement le
    # piege qui a coute « 2 jours sur site » et « France entiere ».
    candidats = sorted(
        ((nom, motif, normaliser(motif).strip(), float(bloc.get("poids", 0)))
         for nom, bloc in groupes.items()
         for motif in bloc.get("motifs", [])),
        key=lambda t: len(t[2]),
        reverse=True,
    )

    trouve, poids, groupe = "", 0.0, ""
    for nom, motif, m, poids_motif in candidats:
        if f" {m} " in reste:
            reste = reste.replace(f" {m} ", " ")
            # A egalite, sa region l'emporte : « Alsace, France entiere » vaut
            # mieux que « France entiere » seul.
            if not trouve or nom == "proches":
                trouve, poids, groupe = motif, poids_motif, nom
    if not trouve:
        return "", 0.0, ""
    for bruit in geo.get("lieu_imprecis_bruit", []):
        reste = reste.replace(f" {normaliser(bruit).strip()} ", " ")
    if reste.strip():
        return "", 0.0, ""
    return trouve, poids, groupe


def _regle_geographie(offre: Offre, c: Criteres, contribs: list[Contribution]) -> tuple[str, str | None]:
    """Decide si l'offre est geographiquement recevable.

    Trois cas, un seul passe :
      1. teletravail complet          -> recevable ou que soit l'employeur
      2. presence exigee, zone OK     -> recevable si le rayon le permet
      3. presence exigee, hors zone   -> ELIMINATOIRE

    Rend (cle_zone, motif_de_rejet_ou_None).
    """
    geo = c.brut.get("geographie", {})
    niveau, preuve = detecter_teletravail(offre, c)
    cle_zone, points_zone, detail_zone, acces = _zone_du_lieu(offre, c)

    # --- Cas 1 : teletravail complet ------------------------------------
    if niveau == "complet":
        poids = float(c.zones.get("teletravail_total", {}).get("poids", 30))
        contribs.append(
            Contribution(
                f"Zone : {c.zones.get('teletravail_total', {}).get('libelle', 'Télétravail complet')}",
                poids,
                preuve,
            )
        )
        # « Fully remote » chez un employeur lointain signifie presque toujours
        # « fully remote dans ce pays-la ». On le dit, sans ecarter.
        cible = normaliser(f"{offre.lieu} {offre.employeur}")
        lointain = next(
            (m for m in geo.get("employeur_lointain_motifs", []) if contient(cible, m)), ""
        )
        if lointain:
            contribs.append(
                Contribution(
                    "A VÉRIFIER - employeur hors de France",
                    0,
                    f'"{lointain}" : un télétravail complet annoncé là-bas suppose souvent '
                    "d'y resider. Verifie qu'il existe une entite pouvant t'employer depuis la France.",
                )
            )

        if detecter_pays(offre, c) == "suisse":
            politique = geo.get("suisse_teletravail_complet", "signaler")
            if politique == "ecarter":
                return "teletravail_total", (
                    "Employeur suisse en télétravail complet : statut de frontalier remis en cause"
                )
            if politique == "signaler":
                contribs.append(
                    Contribution(
                        "A VÉRIFIER - employeur suisse en télétravail complet",
                        0,
                        "au-delà de 40% de télétravail depuis la France, ton statut fiscal et "
                        "social de frontalier est remis en cause : a negocier des le premier contact",
                    )
                )
        return "teletravail_total", None

    # --- Lieu absent : on ne peut rien conclure --------------------------
    if not (offre.lieu or "").strip():
        contribs.append(
            Contribution(
                "Lieu non précisé",
                float(geo.get("lieu_inconnu_poids", -15)),
                "l'annonce ne dit pas où est le poste, et n'annonce pas de télétravail complet "
                "- à vérifier avant d'y passer du temps",
            )
        )
        return "", None

    # --- Lieu trop large : on ne peut pas trancher, donc on n'ecarte pas --
    imprecis, poids_imprecis, groupe = lieu_imprecis(offre, c)
    if imprecis:
        if groupe == "proches":
            detail = (
                f"l'annonce dit seulement « {offre.lieu.strip()} » : c'est ta région, "
                "donc peut-être tout près, peut-être très loin. Demande la ville "
                "au premier contact - ne l'écarte pas sans avoir demandé"
            )
        else:
            detail = (
                f"l'annonce dit seulement « {offre.lieu.strip()} », ce qui ne dit rien "
                "de la ville. À vérifier avant d'y passer du temps"
            )
        contribs.append(Contribution("Lieu imprécis - à vérifier", poids_imprecis, detail))
        return "", None

    # --- Cas 2 : presence attendue, dans une zone atteignable ------------
    if cle_zone:
        libelle = c.zones[cle_zone].get("libelle", cle_zone)
        # Seule une presence a temps plein EXIGEE interdit une zone hybride.
        # Le silence de l'annonce ne suffit pas a l'interdire.
        if niveau == "presentiel" and acces == "hybride":
            return cle_zone, (
                f"Présence à temps plein exigée à {offre.lieu.strip()} : trop loin pour "
                f"s'y rendre chaque jour ({libelle})"
            )
        contribs.append(Contribution(f"Zone : {libelle}", points_zone, detail_zone))
        if niveau == "partiel":
            contribs.append(Contribution("Poste hybride", 0, preuve))
        elif niveau == "inconnu":
            contribs.append(
                Contribution(
                    "Télétravail non précisé",
                    0,
                    "l'annonce n'en dit rien - à demander au premier contact",
                )
            )
        return cle_zone, None

    # --- Cas 3 : presence attendue, hors de toute zone -------------------
    mode = {
        "presentiel": "présentiel à temps plein",
        "partiel": "hybride",
        "inconnu": "sans télétravail annoncé",
    }[niveau]
    contribs.append(
        Contribution(
            "ÉLIMINATOIRE - hors de ta zone géographique",
            0,
            f"{offre.lieu.strip()} - {mode}, ni télétravail complet ni zone atteignable",
        )
    )
    return "", f"Poste {mode} à {offre.lieu.strip()}, hors de ta zone géographique"


_FIN_DE_PHRASE = re.compile(r"(?<=[.!?;])\s+|\n")


def _texte_hors_contextes(offre: Offre, c: Criteres, ignores: list[str]) -> str:
    """Le texte de l'annonce, PHRASE PAR PHRASE, sans celles d'un contexte ignore.

    DEFAUT MESURE LE 02/10/2026. Une part notable des annonces portait une
    mention sur le RECRUTEMENT lui-meme — « We may use [...] tools to support
    parts of the hiring process » — et cette phrase creditait un atout dont
    elle citait les mots. La plus belle : une annonce qui ecrit qu'un outil
    n'est PAS utilise pour trier les candidats recevait le bonus de l'atout qui
    le cherche.

    Plusieurs offres etaient concernees. C'est la meme classe de faux positif
    que les transports en commun cites dans la description d'un poste,
    corrige en restreignant les champs ; ici on ne peut
    pas restreindre les champs — la mention est dans la description, comme le
    reste — donc on retire les PHRASES, une par une.

    Les motifs de contexte sont volontairement SPECIFIQUES (« hiring
    process », « AI notice ») et non du vocabulaire general (« candidat »,
    « diversity ») : un vocabulaire large ferait tomber des phrases qui
    parlent reellement du poste.
    """
    blocs = c.brut.get("contextes_ignores") or {}
    motifs: list[str] = []
    for nom in ignores:
        motifs += (blocs.get(nom) or {}).get("motifs", [])
    if not motifs:
        return normaliser(offre.texte_complet)

    gardees = []
    for phrase in _FIN_DE_PHRASE.split(offre.texte_complet or ""):
        net = normaliser(phrase)
        if net.strip() and not any(contient(net, m) for m in motifs):
            gardees.append(net)
    return " ".join(gardees)


def _regle_atouts(offre: Offre, c: Criteres, contribs: list[Contribution]) -> list[str]:
    """Bonus cumulatifs, plafonnes par groupe.

    Une offre ne recoit qu'UNE famille - la mieux placee. Les atouts, eux,
    s'additionnent : une offre peut etre a la fois du test, parler
    d'accessibilite et citer Playwright, et les trois comptent.

    Le `plafond` empeche qu'une annonce enumerant quinze technologies gonfle
    son score sans rien dire de plus qu'une annonce qui en cite trois.

    Recherche dans tout le texte, a poids plein : une mention de tests
    d'accessibilite dans le corps de l'annonce est une information ferme.
    """
    disponibles = {
        "titre": offre.titre,
        "employeur": offre.employeur,
        "lieu": offre.lieu,
        "description": offre.description,
        "contrat": offre.type_contrat,
    }
    texte_entier = normaliser(offre.texte_complet)
    declenches: list[str] = []

    pays = bareme_applicable(detecter_pays(offre, c))

    for cle, groupe in c.atouts.items():
        # Un atout peut valoir differemment selon le pays, pour la meme
        # competence : monnayable dans l'un, bloque dans l'autre par une
        # exigence de langue.
        poids = float((groupe.get("poids_par_pays") or {}).get(pays, groupe.get("poids", 0)))
        plafond = float(groupe.get("plafond", poids))

        # `champs` restreint la recherche. Indispensable pour les atouts dont
        # les mots sont courants ailleurs : "transport" apparait dans la
        # description de beaucoup d'annonces (les transports en commun, leur
        # prise en charge), ce qui creditait a tort un atout de domaine
        # logistique a plusieurs offres.
        champs = groupe.get("champs")
        texte = (
            normaliser(" ".join(disponibles.get(ch, "") for ch in champs))
            if champs
            else texte_entier
        )

        ignores = groupe.get("ignorer_contextes") or []
        if ignores and not champs:
            # On retire les PHRASES qui relevent d'un contexte ignore, pas le
            # motif ni l'annonce. Une meme annonce peut parler des deux : un
            # poste d'audit d'accessibilite chez un employeur dont le
            # recrutement est accessible lui aussi. C'est le piege deja
            # rencontre avec
            # « France (A distance) » et avec les HTTP 410 — reconnaitre le
            # contexte, pas supprimer la phrase.
            texte = _texte_hors_contextes(offre, c, ignores)

        trouves = [m for m in groupe.get("motifs", []) if contient(texte, m)]
        if not trouves:
            continue

        brut = len(trouves) * poids
        points = min(brut, plafond)
        detail = ", ".join(f'"{m}"' for m in trouves[:4])
        if len(trouves) > 4:
            detail += f" et {len(trouves) - 4} autre(s)"
        if brut > plafond:
            detail += " - plafonné"

        contribs.append(Contribution(groupe.get("libelle", cle), points, detail))
        declenches.append(cle)

    return declenches


def _langue_tranchee(groupe: dict, exigences: dict) -> bool | None:
    """True = declenche par une exigence validee, False = neutralise, None = rien.

    Le groupe ne participe que s'il declare `exigence:` et `valeurs:` dans
    criteres.yaml. Sans ces deux cles, le comportement est inchange.
    """
    attribut = groupe.get("exigence")
    if not attribut:
        return None
    validee = exigences.get(attribut)
    if not validee:
        return None
    return validee.get("valeur") in set(groupe.get("valeurs") or ())


def _regle_langue_annonce(offre: Offre, c: Criteres,
                          contribs: list[Contribution]) -> str | None:
    """La langue DE L'ANNONCE met-elle l'offre de cote ? Rend le motif, ou None.

    POURQUOI UNE MISE EN ATTENTE, ET PAS UN POIDS NEGATIF. Un poids melange
    deux choses differentes : « cette offre te correspond mal » et « tu ne
    peux pas y repondre ». Une annonce allemande peut decrire exactement son
    metier — elle reste hors de portee tant que l'allemand n'est pas
    pratique. Un malus de -40 laisserait passer les mieux notees et
    enterrerait les autres, sans dire pourquoi. La mise en attente est
    categorique, elle porte son motif, et elle se leve d'une ligne.

    C'est le mecanisme deja en place pour `allemand_exige`, pas un nouveau.
    Les offres differees quittent le flux courant sans partir au rebut, et
    `veille rescorer` les ramene toutes d'un coup le jour ou le reglage change.

    ⚠️ LA LANGUE DE L'ANNONCE N'EST PAS LA LANGUE DE TRAVAIL. A Bale, une
    annonce redigee en allemand peut decrire un poste dont la langue de
    travail est l'anglais. Quand l'annonce le DIT, on ne met pas de cote : on
    signale, et il tranche. Mieux vaut quelques fausses alertes qu'une bonne
    offre perdue.
    """
    regles = c.brut.get("langue_annonce") or {}
    if not regles:
        return None

    from .dossier import detecter_langue

    langue = detecter_langue({
        "titre": offre.titre or "",
        "description": offre.description or "",
    })
    regle = regles.get(langue)
    if not regle or not regle.get("mise_en_attente"):
        return None

    # On cherche la langue de travail dans le texte DEBARRASSE du bruit de
    # l'agregateur. Sans ca, le pied de page d'Arbeitnow — « Find more English
    # Speaking Jobs in Germany on Arbeitnow » — ferait passer toutes ses
    # annonces allemandes pour des postes anglophones. C'est le meme piege que
    # pour le teletravail : nettoyer d'abord, chercher ensuite.
    exception = regle.get("exception_langue_de_travail") or {}
    geo = c.brut.get("geographie", {})
    texte = normaliser(f"{_texte_sans_bruit(offre, geo)} {offre.titre}")
    trouve = next((m for m in exception.get("motifs", []) if contient(texte, m)), "")
    if trouve:
        contribs.append(Contribution(
            "A VÉRIFIER - " + exception.get("libelle", "langue de travail annoncée"),
            0,
            f'annonce en {langue}, mais "{trouve}" : le poste se tient '
            f"peut-etre en anglais. Lis-la avant de l'ecarter.",
        ))
        return None

    contribs.append(Contribution(
        regle.get("libelle", f"Annonce en {langue}"),
        0,
        regle.get("motif", "langue non maîtrisée"),
    ))
    return regle.get("motif", f"annonce en {langue}")


def _regle_langues(
    offre: Offre, c: Criteres, pd: float, contribs: list[Contribution]
) -> tuple[str | None, str | None]:
    """Rend (motif_de_rejet, motif_de_mise_en_attente).

    La mise en attente existe pour l'allemand : une offre germanophone n'est
    pas un refus, c'est une offre recevable plus tard. Elle sort du flux
    courant sans partir au rebut, et reviendra d'un seul reglage le jour ou son
    allemand aura progresse.
    """
    texte = normaliser(offre.texte_complet)
    motif_rejet = None
    motif_differe = None
    exig = getattr(offre, "exigences", None) or {}
    for cle, groupe in c.langues.items():
        # Une exigence validee TRANCHE, dans les deux sens : elle declenche le
        # groupe que les motifs ont rate, et elle le neutralise quand le texte
        # dit autre chose que ce qu'il a lu lui-meme. Les points ne changent
        # pas : ils restent ceux de criteres.yaml.
        decision = _langue_tranchee(groupe, exig)
        if decision is False:
            continue
        if decision is True:
            attribut = str(groupe.get("exigence", ""))
            citation = exig.get(attribut, {}).get("citation", "")
            libelle = groupe.get("libelle", cle)
            contribs.append(Contribution(
                libelle, float(groupe.get("poids", 0)),
                f"exigence que tu as validée — « {citation[:160]} »"))
            if groupe.get("eliminatoire"):
                motif_rejet = libelle
            elif groupe.get("mise_en_attente"):
                motif_differe = f"{libelle} - a revoir quand ton allemand aura progresse"
            continue

        trouve = next((m for m in groupe.get("motifs", []) if contient(texte, m)), None)
        if not trouve:
            continue
        libelle = groupe.get("libelle", cle)
        contribs.append(Contribution(libelle, float(groupe.get("poids", 0)), f'"{trouve}" repérée'))
        if groupe.get("eliminatoire"):
            motif_rejet = libelle
        elif groupe.get("mise_en_attente"):
            motif_differe = f"{libelle} - a revoir quand ton allemand aura progresse"
            contribs.append(
                Contribution(
                    "Mise en attente",
                    0,
                    "recevable plus tard : elle reviendra dans le flux des que tu passeras "
                    "`mise_en_attente: false` dans le criteres.yaml de ta configuration (VEILLE_CONFIG)",
                )
            )
    return motif_rejet, motif_differe


def _texte_des_champs(offre: Offre, champs) -> str:
    """Texte normalise des seuls champs demandes.

    Restreindre a l'intitule change tout pour un critere de METIER : le corps
    d'une annonce parle de qualite pour cent raisons, l'intitule nomme le poste.
    """
    valeurs = [getattr(offre, nom, "") or "" for nom in (champs or [])]
    return normaliser(" ".join(valeurs))


def _regle_eliminatoires(offre: Offre, c: Criteres, contribs: list[Contribution]) -> str | None:
    """Rend TOUS les criteres eliminatoires trouves, pas seulement le premier.

    Une annonce qui demande a la fois des astreintes ET du travail le week-end
    doit le dire deux fois : l'alerte apres lecture du texte complet sert a
    l'avertir, et n'en nommer qu'un seul serait une information tronquee.
    """
    complet = normaliser(offre.texte_complet)
    trouves = []
    for cle, groupe in c.eliminatoires.items():
        # `champs` restreint ou chercher. Sans lui, c'est tout le texte, comme
        # avant : une astreinte annoncee n'importe ou reste une astreinte.
        texte = _texte_des_champs(offre, groupe.get("champs")) if groupe.get("champs") else complet
        motif = next((m for m in groupe.get("motifs", []) if contient(texte, m)), None)
        if not motif:
            continue

        # Un signal SANS AMBIGUITE (`toujours_motifs`) court-circuite le filet
        # de securite : un terme qui ne peut rien vouloir dire d'autre que le
        # metier ecarte l'emporte, meme si une famille a ete attribuee.
        certain = next(
            (m for m in groupe.get("toujours_motifs", []) if contient(texte, m)), None
        )
        if certain:
            motif = certain

        # `sauf_si` : le signal SPECIFIQUE l'emporte sur le motif general.
        # C'est ce qui separe un metier voisin, qu'on ecarte, d'un metier cible
        # qui en partage tout le vocabulaire.
        sauf = {} if certain else (groupe.get("sauf_si") or {})
        if sauf:
            if sauf.get("famille_attribuee") and offre.famille:
                continue
            ou = _texte_des_champs(offre, sauf.get("champs")) if sauf.get("champs") else complet
            garde = next((m for m in sauf.get("motifs", []) if contient(ou, m)), None)
            if garde:
                continue

        libelle = groupe.get("libelle", cle)
        ou_dit = "l'intitule" if groupe.get("champs") == ["titre"] else "le texte"
        contribs.append(
            Contribution(f"ÉLIMINATOIRE - {libelle}", 0, f'"{motif}" repere dans {ou_dit}')
        )
        trouves.append(libelle)
    return " ; ".join(trouves) if trouves else None


def _regle_salaire(offre: Offre, c: Criteres, pays: str, contribs: list[Contribution]) -> str | None:
    bareme = c.salaire.get(pays, {})
    if not bareme:
        return None

    if offre.salaire_min is None and offre.salaire_max is None:
        contribs.append(
            Contribution(
                "Salaire non publié",
                float(c.salaire.get("poids_absent", 0)),
                "l'annonce n'affiche rien - a vérifier au premier contact",
            )
        )
        return None

    # On juge sur la borne haute proposee : c'est ce qui est negociable.
    reference = offre.salaire_max if offre.salaire_max is not None else offre.salaire_min
    plancher = float(bareme.get("plancher", 0))
    devise = bareme.get("devise", "")

    if reference < plancher:
        contribs.append(
            Contribution(
                f"ÉLIMINATOIRE - Salaire sous ton plancher {pays}",
                0,
                f"{offre.salaire_affiche} < {plancher:,.0f} {devise}".replace(",", " "),
            )
        )
        return f"Salaire sous le plancher {pays} ({plancher:,.0f} {devise})".replace(",", " ")

    cible_basse = float(bareme.get("cible_basse", plancher))
    cible_haute = float(bareme.get("cible_haute", plancher))
    if reference > cible_haute:
        pts = float(bareme.get("poids_au_dessus_cible", 0))
        detail = f"{offre.salaire_affiche} - au-dessus de ta cible"
    elif reference >= cible_basse:
        pts = float(bareme.get("poids_dans_cible", 0))
        detail = f"{offre.salaire_affiche} - dans ta cible"
    else:
        pts = 0.0
        detail = f"{offre.salaire_affiche} - au-dessus du plancher mais sous ta cible"
    contribs.append(Contribution("Salaire publié", pts, detail))
    return None


def _regle_contrat(offre: Offre, c: Criteres, pays: str, contribs: list[Contribution]) -> str | None:
    texte = normaliser(f"{offre.type_contrat} {offre.titre}")
    if contient(texte, "cdi") or contient(texte, "unbefristet") or contient(texte, "permanent"):
        contribs.append(Contribution("CDI", float(c.contrat.get("cdi_bonus", 0)), ""))
        return None

    if not est_interim(offre, c):
        return None

    mini = int(c.contrat.get("interim_suisse_duree_minimale_mois", 4))
    duree = detecter_duree_mois(offre)

    if pays != "suisse":
        contribs.append(Contribution("Mission / intérim", 0, "hors Suisse : pas de règle de durée"))
        return None

    if duree is None:
        contribs.append(
            Contribution(
                "Intérim suisse, durée non précisée",
                -5,
                f"A VÉRIFIER AVANT TOUT CONTACT : une mission sous le minimum de {mini} mois "
                f"de tes critères est écartée",
            )
        )
        return None

    if duree < mini:
        contribs.append(
            Contribution(
                "ÉLIMINATOIRE - Intérim suisse trop court",
                0,
                f"{duree} mois annoncés, sous le minimum de {mini} mois de tes critères",
            )
        )
        return f"Intérim suisse de {duree} mois (minimum {mini})"

    contribs.append(Contribution("Intérim suisse de durée suffisante", 0, f"{duree} mois >= {mini}"))
    return None


# --------------------------------------------------------------------------
# Entree publique
# --------------------------------------------------------------------------


def scorer(offre: Offre, criteres: Criteres | None = None) -> Offre:
    """Calcule score, famille, zone, rejet automatique et explication."""
    c = criteres or charger_criteres()
    pd = float(c.scoring.get("poids_description", 0.4))
    contribs: list[Contribution] = []
    motifs_rejet: list[str] = []

    pays = detecter_pays(offre, c)
    bareme = bareme_applicable(pays)
    if pays not in PAYS_SERVIS:
        # On applique le bareme francais, et on le DIT. Une part notable des
        # offres etait silencieusement traitee comme francaise alors qu'elles
        # sont a Hambourg, Londres ou Varsovie.
        contribs.append(Contribution(
            "A VÉRIFIER - pays " + (pays or "indéterminé"), 0,
            f"le lieu « {(offre.lieu or '?')[:40]} » ne correspond ni à la France "
            f"ni à la Suisse : barème salarial français appliqué par défaut"))

    offre.famille = _regle_famille(offre, c, pd, contribs)
    offre.zone, rejet_geo = _regle_geographie(offre, c, contribs)
    offre.atouts = _regle_atouts(offre, c, contribs)

    rejet_langue, differe_langue = _regle_langues(offre, c, pd, contribs)
    # La langue de l'ANNONCE, distincte des exigences linguistiques du
    # poste : une annonce allemande est hors de portee meme si elle
    # n'exige pas l'allemand.
    differe_langue = differe_langue or _regle_langue_annonce(offre, c, contribs)
    for motif in (
        rejet_geo,
        _regle_eliminatoires(offre, c, contribs),
        rejet_langue,
        _regle_salaire(offre, c, bareme, contribs),
        _regle_contrat(offre, c, pays, contribs),
    ):
        if motif:
            motifs_rejet.append(motif)

    if offre.donnees_partielles:
        contribs.append(
            Contribution(
                "Données partielles",
                float(c.scoring.get("malus_donnees_partielles", -5)),
                "le mail ne contenait qu'un extrait : ce score ne porte que sur l'intitule et le lieu, "
                "pas sur le contenu de l'annonce",
            )
        )

    offre.explication = contribs
    offre.score = round(sum(x.points for x in contribs), 1)
    offre.rejete_auto = bool(motifs_rejet)
    offre.motif_rejet_auto = " ; ".join(motifs_rejet)
    # Une mise en attente ne s'applique que si l'offre n'est pas deja au rebut
    # pour une autre raison : inutile de differer ce qui est refuse.
    offre.differee = bool(differe_langue) and not offre.rejete_auto
    offre.motif_differe = differe_langue or ""
    return offre
