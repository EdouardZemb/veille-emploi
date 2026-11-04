"""Tests du moteur de score.

On verifie surtout les regles ou une erreur couterait cher : les criteres
eliminatoires, le plancher salarial, et la duree minimale d'interim suisse
(six mois dans l'exemple).
"""

from __future__ import annotations

import pytest

from veille.config import charger_criteres, normaliser
from veille.models import Offre, canoniser_url, empreinte, empreinte_titre
from veille.scoring import detecter_duree_mois, detecter_pays, scorer


@pytest.fixture(scope="module")
def criteres():
    return charger_criteres()


def _score(offre: Offre, criteres) -> Offre:
    return scorer(offre, criteres)


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


def test_normalisation_retire_accents_et_casse():
    assert "bale" in normaliser("Bâle")
    assert "teletravail" in normaliser("Télétravail")
    assert "strasse" in normaliser("Straße")


@pytest.mark.parametrize(
    "texte,motif",
    [
        # Regression : le point final restait colle au mot, et le motif ne
        # correspondait plus.
        ("Pratique de la recette fonctionnelle.", "recette fonctionnelle"),
        ("Nous cherchons un expert Node.js.", "node.js"),
        ("Pipeline CI/CD moderne.", "ci/cd"),
        ("Taux d'activite 80%.", "80%"),
        ("Experience en C#.", "c#"),
        ("Poste a 100% teletravail, des demain.", "100% teletravail"),
    ],
)
def test_la_ponctuation_de_fin_de_phrase_nempeche_pas_la_correspondance(texte, motif):
    from veille.config import contient

    assert contient(normaliser(texte), motif)


def test_contient_ne_matche_pas_au_milieu_dun_mot():
    from veille.config import contient

    assert contient(normaliser("Ingenieur SRE"), "sre")
    # "sre" ne doit pas matcher dans "desree"
    assert not contient(normaliser("Desree Martin"), "sre")


# --------------------------------------------------------------------------
# Familles et zones
# --------------------------------------------------------------------------


def test_famille_test_fonctionnel_dans_lintitule(criteres):
    """L'automatisation et le pilotage ont leur propre famille : voir
    tests/test_recalibrage.py."""
    o = _score(Offre(titre="Testeur fonctionnel", lieu="Mulhouse"), criteres)
    assert o.famille == "test_fonctionnel"
    assert o.score > 0


def test_l_agglomeration_est_la_zone_la_mieux_payee(criteres):
    """L'exemple prefere une equipe sur place : l'agglomeration rapporte plus
    que le teletravail integral, qui rapporte plus qu'un trajet quotidien."""
    remote = _score(Offre(titre="QA Engineer", lieu="France", description="100% teletravail"), criteres)
    proche = _score(Offre(titre="QA Engineer", lieu="Basel"), criteres)
    trajet = _score(Offre(titre="QA Engineer", lieu="Mulhouse"), criteres)
    assert remote.zone == "teletravail_total"
    assert proche.zone == "zone_proche" and trajet.zone == "zone_trajet"
    assert proche.score > remote.score > trajet.score


def test_zone_ne_se_deduit_pas_de_la_prose_de_lemployeur(criteres):
    """Regression : un poste a Coire etait credite de "Bale" parce que
    l'employeur citait Bale dans sa presentation. La zone se juge sur le lieu."""
    o = _score(
        Offre(
            titre="Software Engineer",
            lieu="Chur, Graubunden",
            description="Exemplia Group, avec des bureaux a Basel, Zurich et Chur.",
        ),
        criteres,
    )
    assert o.zone != "zone_proche"
    assert o.zone == ""


def test_teletravail_garde_son_poids_plein_depuis_la_description(criteres):
    """Regression : "full remote" ne rapportait que 40% du poids parce qu'il
    etait dans la description. C'est un mode de travail que les criteres
    peuvent valoriser, et il est toujours ecrit la."""
    o = _score(
        Offre(titre="Software Engineer", lieu="Remote", description="This is a fully remote position."),
        criteres,
    )
    assert o.zone == "teletravail_total"
    contribution = next(c for c in o.explication if c.libelle.startswith("Zone"))
    assert contribution.points == 18


def test_un_lieu_hors_zone_est_maintenant_eliminatoire(criteres):
    """Comportement change apres son retour d'usage : une offre a Toulouse
    sans teletravail complet ne doit plus remonter du tout. Voir
    tests/test_geographie.py pour la regle complete."""
    o = _score(Offre(titre="QA Engineer", lieu="Toulouse"), criteres)
    assert o.zone == ""
    assert o.rejete_auto
    assert any("hors de ta zone" in c.libelle.lower() for c in o.explication)


# --------------------------------------------------------------------------
# Criteres eliminatoires
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texte,attendu",
    [
        ("Travail en soiree requis", "soirée"),
        ("Wochenendarbeit erforderlich", "week-end"),
        ("Astreinte une semaine sur quatre", "astreinte"),
        ("Kundenkontakt auf Deutsch", "clientèle"),
    ],
)
def test_criteres_eliminatoires_detectes(criteres, texte, attendu):
    o = _score(Offre(titre="QA Engineer", lieu="Strasbourg", description=texte), criteres)
    assert o.rejete_auto, f"aurait du etre rejete : {texte}"
    assert attendu.lower() in o.motif_rejet_auto.lower()


def test_allemand_exige_penalise_mais_necarte_pas(criteres):
    """Il progresse en allemand : on signale sans fermer la porte."""
    o = _score(
        Offre(titre="Test Engineer", lieu="Basel", description="Verhandlungssicheres Deutsch erforderlich"),
        criteres,
    )
    assert not o.rejete_auto
    assert any("allemand" in c.libelle.lower() for c in o.explication)
    assert any(c.points < 0 for c in o.explication if "allemand" in c.libelle.lower())


# --------------------------------------------------------------------------
# Salaire
# --------------------------------------------------------------------------


def test_salaire_sous_plancher_francais_ecarte(criteres):
    o = _score(
        Offre(titre="QA Engineer", lieu="Strasbourg", salaire_min=30000, salaire_max=34000, salaire_devise="EUR"),
        criteres,
    )
    assert o.rejete_auto
    assert "plancher" in o.motif_rejet_auto.lower()


def test_salaire_dans_la_cible_est_bonifie(criteres):
    dans = _score(
        Offre(titre="QA Engineer", lieu="Mulhouse", salaire_min=44000, salaire_max=48000, salaire_devise="EUR"),
        criteres,
    )
    sans = _score(Offre(titre="QA Engineer", lieu="Mulhouse"), criteres)
    assert not dans.rejete_auto
    assert dans.score > sans.score


def test_salaire_absent_nest_jamais_eliminatoire(criteres):
    o = _score(Offre(titre="QA Engineer", lieu="Mulhouse"), criteres)
    assert not o.rejete_auto
    assert any("non publié" in c.libelle.lower() for c in o.explication)


def test_plancher_suisse_applique_en_chf(criteres):
    o = _score(
        Offre(titre="Test Engineer", lieu="Basel", salaire_min=70000, salaire_max=80000, salaire_devise="CHF"),
        criteres,
    )
    assert o.rejete_auto
    assert "suisse" in o.motif_rejet_auto.lower()


def test_detection_pays_suisse_par_le_lieu():
    assert detecter_pays(Offre(titre="x", lieu="Allschwil, Basel-Landschaft")) == "suisse"
    assert detecter_pays(Offre(titre="x", lieu="Mulhouse")) == "france"


# --------------------------------------------------------------------------
# Interim suisse : critere de securite
# --------------------------------------------------------------------------


def test_interim_suisse_trop_court_est_eliminatoire(criteres):
    o = _score(
        Offre(
            titre="Test Engineer",
            lieu="Basel",
            type_contrat="Interim",
            description="Mission temporaire de 3 mois.",
            salaire_min=130000,
            salaire_max=140000,
            salaire_devise="CHF",
        ),
        criteres,
    )
    assert o.rejete_auto
    assert "sous le minimum" in " ".join(c.detail for c in o.explication).lower()


def test_interim_suisse_assez_long_passe(criteres):
    o = _score(
        Offre(
            titre="Test Engineer",
            lieu="Basel",
            type_contrat="Interim",
            description="Mission temporaire de 12 mois.",
            salaire_min=130000,
            salaire_max=140000,
            salaire_devise="CHF",
        ),
        criteres,
    )
    assert not o.rejete_auto


def test_interim_suisse_sans_duree_est_signale(criteres):
    o = _score(
        Offre(titre="Test Engineer", lieu="Basel", type_contrat="Interim", description="Contracting role."),
        criteres,
    )
    assert not o.rejete_auto
    assert any("A VÉRIFIER" in c.detail for c in o.explication)


def test_interim_francais_nest_pas_soumis_a_la_duree(criteres):
    o = _score(
        Offre(titre="Testeur", lieu="Mulhouse", type_contrat="Interim", description="Mission de 2 mois."),
        criteres,
    )
    assert not o.rejete_auto


@pytest.mark.parametrize(
    "texte,attendu",
    [
        ("mission de 6 mois", 6),
        ("contrat de 12 months", 12),
        ("Einsatz von 9 Monaten", 9),
        ("mission de 3 a 6 mois", 3),  # on retient la borne garantie
        ("contrat de 2 ans", 24),
        ("mission de 8 semaines", 2),
    ],
)
def test_detection_de_duree(texte, attendu):
    assert detecter_duree_mois(Offre(titre="x", description=texte)) == attendu


# --------------------------------------------------------------------------
# Donnees partielles
# --------------------------------------------------------------------------


def test_donnees_partielles_signalees_et_penalisees(criteres):
    complet = _score(Offre(titre="QA Engineer", lieu="Strasbourg"), criteres)
    partiel = _score(Offre(titre="QA Engineer", lieu="Strasbourg", donnees_partielles=True), criteres)
    assert partiel.score < complet.score
    detail = " ".join(c.detail for c in partiel.explication)
    assert "extrait" in detail.lower()


# --------------------------------------------------------------------------
# Explication
# --------------------------------------------------------------------------


def test_le_score_est_exactement_la_somme_des_contributions(criteres):
    o = _score(
        Offre(
            titre="Senior Test Automation Engineer",
            lieu="Basel",
            description="100% remote possible. English speaking team.",
            salaire_min=130000,
            salaire_max=145000,
            salaire_devise="CHF",
            type_contrat="CDI",
        ),
        criteres,
    )
    assert o.score == pytest.approx(sum(c.points for c in o.explication), abs=0.05)
    assert len(o.explication) >= 3


# --------------------------------------------------------------------------
# Deduplication
# --------------------------------------------------------------------------


def test_canonisation_retire_le_tracking():
    a = canoniser_url("https://www.linkedin.com/jobs/view/4012345678/?refId=abc&trackingId=xyz&utm_source=mail")
    b = canoniser_url("https://linkedin.com/jobs/view/4012345678?utm_medium=email")
    assert a == b


def test_empreinte_identique_pour_la_meme_annonce():
    u = "https://www.linkedin.com/jobs/view/4012345678/"
    assert empreinte(canoniser_url(u + "?trk=a"), "T", "E") == empreinte(canoniser_url(u), "T", "E")


def test_meme_annonce_sur_plusieurs_domaines_nationaux_dedupliquee():
    """Regression : la meme offre arrivait 4 fois, via arbeitnow.ch, .fr, .com
    et .co.uk."""
    chemin = "/jobs/companies/nuagia/remote-software-engineer-infrastructure-100001"
    urls = [f"https://www.arbeitnow.{tld}{chemin}" for tld in ("com", "ch", "fr", "co.uk")]
    empreintes = {empreinte(canoniser_url(u), "Software Engineer", "Nuagia") for u in urls}
    assert len(empreintes) == 1


def test_poste_republie_sous_un_nouvel_identifiant_est_reconnu():
    """Regression : chez un meme employeur, la meme offre arrivait sous trois URL
    differentes, l'identifiant changeant a chaque republication."""
    cles = {
        empreinte_titre("Software Engineer, Infrastructure - Self Hosted Platform (SHP)", "Nuagia")
        for _ in range(3)
    }
    assert len(cles) == 1
    # Un intitule different chez le meme employeur reste distinct.
    assert empreinte_titre("Senior Software Engineer, Kubernetes", "Nuagia") not in cles


def test_empreinte_titre_ignore_casse_et_accents():
    assert empreinte_titre("Ingénieur QA", "Société X") == empreinte_titre("INGENIEUR QA", "societe x")


def test_empreinte_se_rabat_sur_titre_et_employeur_sans_url():
    assert empreinte("", "QA Engineer", "Exemplia") == empreinte("", "QA Engineer", "Exemplia")
    assert empreinte("", "QA Engineer", "Exemplia") != empreinte("", "QA Engineer", "Fictivia")


# --------------------------------------------------------------------------
# LA LANGUE DE L'ANNONCE — mise de cote, pas suppression
#
# Une offre en allemand est mise de cote tant que les criteres le disent.
#
# On reutilise la mise en attente qui existe deja pour `allemand_exige` :
# categorique, porteuse d'un motif, et levee par une ligne de configuration.
# Un poids negatif aurait melange « cette offre te correspond mal » et « tu ne
# peux pas y repondre » — et aurait laisse passer les mieux notees.
# --------------------------------------------------------------------------

TEXTE_DE = ("Wir suchen eine erfahrene Entwicklerin fur unser Team in Basel. "
            "Sie arbeiten mit modernen Technologien und sind fur die Qualitat "
            "der Software verantwortlich. Das Team ist international, und wir "
            "bieten ein attraktives Umfeld.")


def _offre_de(**kw):
    from veille.models import Offre

    base = {"titre": "Softwareentwickler (m/w/d)", "description": TEXTE_DE,
            "lieu": "Basel", "employeur": "Une societe"}
    base.update(kw)
    return Offre(**base)


def test_une_annonce_allemande_est_mise_de_cote():
    from veille import scoring

    o = _offre_de()
    scoring.scorer(o)
    assert o.differee is True
    assert "allemand" in o.motif_differe
    assert "langue non maîtrisée" in o.motif_differe


def test_la_mise_de_cote_nest_pas_une_suppression():
    """Elle garde son score : le jour ou le reglage bascule, elle revient
    telle quelle."""
    from veille import scoring

    o = _offre_de()
    scoring.scorer(o)
    assert o.score == round(sum(c.points for c in o.explication), 1)
    assert not o.rejete_auto, "differee n'est pas ecartee"


def test_le_motif_est_ecrit_dans_lexplication():
    from veille import scoring

    o = _offre_de()
    scoring.scorer(o)
    lignes = [c for c in o.explication if "allemand" in c.libelle.lower()]
    assert lignes, [c.libelle for c in o.explication]
    assert lignes[0].points == 0, "une mise de cote n'est pas un malus"


@pytest.mark.parametrize("mention", [
    "Die Arbeitssprache ist Englisch.",
    "Unternehmenssprache Englisch, Deutsch von Vorteil.",
    "English is our working language.",
    "Wir arbeiten in einem englischsprachiges Umfeld.",
])
def test_une_langue_de_travail_anglaise_annoncee_retient_loffre(mention):
    """Le piege : annonce redigee en allemand, poste tenu en anglais. A Bale
    c'est courant — plusieurs grands employeurs y ont une politique anglophone."""
    from veille import scoring

    o = _offre_de(description=TEXTE_DE + " " + mention)
    scoring.scorer(o)
    assert o.differee is False, "une bonne offre ne doit pas partir"
    signale = [c for c in o.explication if "Langue de travail" in c.libelle]
    assert signale, "elle doit etre SIGNALEE, pas seulement retenue"
    assert signale[0].libelle.startswith("A VÉRIFIER")


def test_le_pied_de_page_de_lagregateur_ne_declenche_pas_lexception():
    """« Find more English Speaking Jobs in Germany on Arbeitnow » est le pied
    de page du site, pas une phrase de l'annonce. Certaines de ses annonces
    allemandes le portent : sans nettoyage, elles seraient toutes retenues."""
    from veille import scoring

    o = _offre_de(description=TEXTE_DE
                  + " Find more English Speaking Jobs in Germany on Arbeitnow")
    scoring.scorer(o)
    assert o.differee is True, "le bruit de l'agregateur a fait passer l'offre"
    assert not [c for c in o.explication if "Langue de travail" in c.libelle]


def test_mentionner_langlais_comme_exigence_ne_retient_pas_loffre():
    """Une part notable des annonces allemandes parle d'anglais — mais pour
    le DEMANDER en plus de l'allemand. Ce n'est pas une langue de travail."""
    from veille import scoring

    for exigence in ("Fliessende Deutsch - und Englischkenntnisse.",
                     "Sehr gute Englischkenntnisse erforderlich.",
                     "Kommunikationsstarke in Deutsch und Englisch."):
        o = _offre_de(description=TEXTE_DE + " " + exigence)
        scoring.scorer(o)
        assert o.differee is True, exigence


def test_une_annonce_francaise_ou_anglaise_nest_pas_touchee():
    from veille import scoring
    from veille.models import Offre

    fr = Offre(titre="Ingenieur validation", lieu="Mulhouse",
               description=("Nous recherchons un ingenieur pour la validation "
                            "des systemes, dans une equipe et avec les metiers."))
    scoring.scorer(fr)
    assert fr.differee is False


def test_la_regle_se_leve_dune_ligne_de_configuration(monkeypatch):
    """« pour le moment » : la bascule doit couter un reglage, pas du code."""
    from veille import scoring
    from veille.config import charger_criteres

    c = charger_criteres()
    assert c.brut["langue_annonce"]["de"]["mise_en_attente"] is True

    import copy
    leve = copy.deepcopy(c)
    leve.brut["langue_annonce"]["de"]["mise_en_attente"] = False
    o = _offre_de()
    scoring.scorer(o, leve)
    assert o.differee is False, "mise_en_attente: false doit tout ramener"


def test_sans_section_langue_annonce_le_comportement_est_inchange():
    """Une configuration qui ne declare pas la regle ne doit rien changer."""
    import copy

    from veille import scoring
    from veille.config import charger_criteres

    c = copy.deepcopy(charger_criteres())
    c.brut.pop("langue_annonce", None)
    o = _offre_de()
    scoring.scorer(o, c)
    assert o.differee is False


def test_le_rescorage_global_applique_la_mise_de_cote(tmp_path, monkeypatch):
    """DEFAUT TROUVE LE 02/10/2026 EN REJOUANT L'HISTORIQUE.

    `rescorer_tout` ne faisait circuler les offres qu'entre « nouveau » et
    « ecartee ». Le reglage `mise_en_attente`, documente depuis le debut
    comme « repasse a true et lance veille rescorer », ne produisait donc
    aucun effet par cette commande. Le rejeu rendait 0 mise de cote la ou
    la mesure a blanc en annoncait 16.
    """
    import uuid

    from veille import db, scoring
    from veille.models import Offre

    db.initialiser()
    marque = uuid.uuid4().hex[:8]
    o = Offre(titre=f"Softwareentwickler {marque}", lieu="Basel",
              description=TEXTE_DE, url=f"https://exemple.test/{marque}")
    scoring.scorer(o)
    # On la force en « nouveau » pour simuler une offre collectee avant la regle.
    offre_id, nouvelle = db.enregistrer_offre(o)
    assert nouvelle
    with db.connexion() as cx:
        cx.execute("UPDATE offres SET statut='nouveau', motif_ecartement=NULL "
                   "WHERE id=?", (offre_id,))

    recalculees, ecartees, remises, differees = db.rescorer_tout()
    assert differees >= 1, "le rescorage global doit appliquer la mise de cote"
    ligne = db.lire_offre(offre_id)
    assert ligne["statut"] == "differee"
    assert "allemand" in (ligne["motif_ecartement"] or "")


def test_le_rescorage_global_ramene_les_offres_quand_le_reglage_est_leve():
    """L'autre sens : c'est la promesse « elles reviennent toutes d'un coup »."""
    import uuid
    from pathlib import Path

    from veille import db, scoring
    from veille.models import Offre

    db.initialiser()
    marque = uuid.uuid4().hex[:8]
    o = Offre(titre=f"Entwickler {marque}", lieu="Basel", description=TEXTE_DE,
              url=f"https://exemple.test/{marque}")
    scoring.scorer(o)
    offre_id, _ = db.enregistrer_offre(o)
    assert db.lire_offre(offre_id)["statut"] == "differee"

    # On bascule le reglage DANS LE FICHIER, puisque c'est ce qu'il fera :
    # `rescorer_tout` commence par `recharger()`, qui vide le cache et relit
    # criteres.yaml. Modifier l'objet en memoire ne survivrait pas a cet appel.
    from veille import config

    original = config.CHEMIN_CRITERES
    copie = Path(str(original)).read_text(encoding="utf-8").replace(
        'mise_en_attente: true', 'mise_en_attente: false')
    temporaire = Path(str(original)).parent / "criteres-essai-langue.yaml"
    temporaire.write_text(copie, encoding="utf-8")
    try:
        config.CHEMIN_CRITERES = temporaire
        db.rescorer_tout()
        assert db.lire_offre(offre_id)["statut"] == "nouveau", (
            "« elles reviennent toutes d'un coup » est la promesse de la doc")
    finally:
        config.CHEMIN_CRITERES = original
        temporaire.unlink(missing_ok=True)
        config.recharger()


def test_le_rescorage_ne_touche_pas_une_offre_quil_a_triee():
    """Regle habituelle : le moteur revient sur SES decisions, pas les siennes."""
    import uuid

    from veille import db, scoring
    from veille.models import Offre

    db.initialiser()
    marque = uuid.uuid4().hex[:8]
    o = Offre(titre=f"Entwicklerin {marque}", lieu="Basel", description=TEXTE_DE,
              url=f"https://exemple.test/{marque}")
    scoring.scorer(o)
    offre_id, _ = db.enregistrer_offre(o)
    db.changer_statut(offre_id, "interessante")

    db.rescorer_tout()
    assert db.lire_offre(offre_id)["statut"] == "interessante"


# --------------------------------------------------------------------------
# LE RECRUTEMENT DE L'EMPLOYEUR N'EST PAS LE POSTE
#
# Beaucoup d'annonces parlent de leur propre processus de recrutement, et
# cette phrase creditait un atout dont elle citait les mots. Transpose a
# l'exemple : « notre processus de recrutement est accessible » creditait
# l'atout de l'accessibilite.
#
# La plus parlante : une annonce qui dit NE PAS demander de lecteur d'ecran
# pour candidater recevait le bonus de l'accessibilite.
#
# Dans l'exemple, les atouts abonnes sont `accessibilite` et `contexte_mobile` :
# une annonce qui dit que son recrutement est accessible, ou qu'il se suit sur
# une application mobile, ne les credite pas.
#
# ⚠️ ON RETIRE LA PHRASE, PAS LE MOTIF. Une annonce peut parler des deux : un
# poste d'accessibilite chez un employeur dont le recrutement l'est aussi.
# --------------------------------------------------------------------------

MENTION_RECRUTEMENT = (
    "Our hiring process is accessible: application forms follow WCAG, work "
    "with any screen reader, and can be followed in our mobile app.")
MENTION_NEGATIVE = (
    "No screen reader or mobile app is needed for the selection of candidates "
    "for this position.")
POSTE_MOBILE = ("You will test our iOS and Android apps before each release "
                "of the mobile application.")


def _offre_texte(texte, titre="Software Engineer"):
    from veille.models import Offre

    return Offre(titre=titre, lieu="Mulhouse", description=texte)


@pytest.mark.parametrize("mention", [MENTION_RECRUTEMENT, MENTION_NEGATIVE])
def test_une_mention_de_recrutement_ne_donne_aucun_bonus(mention):
    from veille import scoring

    o = _offre_texte("Nous recherchons un developpeur backend. " + mention)
    scoring.scorer(o)
    assert "contexte_mobile" not in o.atouts, [c.libelle for c in o.explication]
    assert "accessibilite" not in o.atouts


def test_une_annonce_qui_dit_ne_PAS_exiger_l_application_nest_pas_creditee():
    """Le cas le plus net : une mention qui ecarte l'application la nomme."""
    from veille import scoring

    o = _offre_texte("Backend engineer. " + MENTION_NEGATIVE)
    scoring.scorer(o)
    assert "contexte_mobile" not in o.atouts


def test_un_vrai_poste_mobile_garde_son_bonus():
    from veille import scoring

    o = _offre_texte(POSTE_MOBILE)
    scoring.scorer(o)
    assert "contexte_mobile" in o.atouts


def test_une_annonce_qui_parle_des_DEUX_garde_son_bonus():
    """LE PIEGE. On retire la phrase du recruteur, pas celle du poste."""
    from veille import scoring

    o = _offre_texte(POSTE_MOBILE + " " + MENTION_RECRUTEMENT)
    scoring.scorer(o)
    assert "contexte_mobile" in o.atouts, (
        "la mention de recrutement a emporte la phrase qui parle du poste")


def test_un_poste_d_accessibilite_chez_un_recruteur_au_recrutement_accessible():
    """Le cas limite : l'atout rare et la mention de recrutement, ensemble."""
    from veille import scoring

    o = _offre_texte(
        "You will run WCAG audits and accessibility testing on our products. "
        + MENTION_RECRUTEMENT, titre="Accessibility Tester")
    scoring.scorer(o)
    assert "accessibilite" in o.atouts
    ligne = [c for c in o.explication if "Accessibilité" in c.libelle and c.points >= 25]
    assert ligne, [(c.libelle, c.points) for c in o.explication]


def test_les_motifs_de_contexte_sont_des_formulations_pas_des_mots():
    """« candidat », « diversity », « privacy » seuls feraient tomber des
    phrases qui parlent vraiment du poste. Des offres de sa base l'ont
    montre pendant la mesure."""
    from veille.config import charger_criteres

    ACRONYMES = {"rgpd", "gdpr"}
    motifs = charger_criteres().brut["contextes_ignores"]["recrutement"]["motifs"]
    for m in motifs:
        # Soit plusieurs mots, soit un mot long et sans ambiguite — les
        # composes allemands comme « bewerbungsprozess » sont aussi precis
        # qu'une locution. « candidat », « privacy », « diversity » ne le
        # seraient pas, et c'est eux qu'on refuse.
        assert " " in m or len(m) >= 12 or m in ACRONYMES, (
            f"« {m} » est trop court et trop general pour un contexte")


def test_un_groupe_sans_abonnement_nest_pas_affecte():
    """`ignorer_contextes` est un choix par groupe, pas un comportement global."""
    from veille.config import charger_criteres

    c = charger_criteres()
    assert c.atouts["outils_test"].get("ignorer_contextes") is None
    assert c.atouts["accessibilite"].get("ignorer_contextes") == ["recrutement"]
