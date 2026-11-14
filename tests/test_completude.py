"""Combien sait-on de ce poste ? — score de COMPLETUDE, pas de correspondance.

Deux axes, jamais melanges :

- le **score de correspondance** dit si l'offre lui va ;
- le **score de complétude** dit si on en sait assez pour ecrire une
  candidature qui tienne.

Une offre parfaite mal documentee et une offre mediocre bien documentee doivent
rester lisibles separement. Aucune moyenne des deux n'existe nulle part, et ce
fichier le verrouille.

Son vrai usage : « Préparer ma candidature », qui s'arrête sous le seuil. Sans
lui, la génération produirait une lettre d'un extrait de trois lignes, sans que
rien ne l'avertisse. Le score doit prevenir AVANT, et surtout dire **ce qui
manque** — « information insuffisante » sans dire laquelle ne sert a rien.
"""

from __future__ import annotations

import itertools

import pytest

from veille import completude, db
from veille.models import Offre
from veille.scoring import scorer
from tests.aide_session import connecter


@pytest.fixture
def client_completude():
    from fastapi.testclient import TestClient

    from veille.app import app

    with TestClient(app, follow_redirects=False) as c:
        connecter(c)
        yield c


@pytest.fixture(autouse=True)
def base():
    db.initialiser()
    with db.connexion() as cx:
        cx.execute("DELETE FROM offres WHERE source = 'test:completude'")


ANNONCE_COMPLETE = (
    "Vous pilotez la recette de notre logiciel de gestion d'entrepot (WMS) sur "
    "notre site logistique de Mulhouse. Vous redigez les plans de test et les "
    "rapports de recette et garantissez la conformite des ecrans au RGAA "
    "et aux WCAG. Vous participez a la migration des donnees lors du "
    "changement d'ERP. Formation superieure en informatique ou qualite. "
    "Anglais professionnel exige. Deux jours de teletravail par semaine. "
    "Remuneration entre 46000 et 50000 euros selon profil. Contact : Marie "
    "Durand, responsable recrutement. Groupe de 1200 personnes, secteur "
    "logistique." * 2
)


_compteur = itertools.count()


def _offre(**kw) -> dict:
    """Chaque variante a sa PROPRE url et son propre intitule.

    Sans ca, `enregistrer_offre` deduplique et toutes les variantes retombent
    sur la meme ligne : on comparait l'offre complete a elle-meme. C'est le
    piege qui a failli ecraser une vraie offre en base il y a deux jours.
    Aucune url reelle ici : `.invalid` est reserve a cet usage par la RFC 2606.
    """
    n = next(_compteur)
    champs = dict(
        titre=f"Ingenieur de test WMS {n}",
        employeur=f"Entrepots Test Completude {n}",
        lieu="Mulhouse",
        description=ANNONCE_COMPLETE,
        url=f"https://exemple-test-completude.invalid/offre/{n}",
        source="test:completude",
        salaire_min=46000.0,
        salaire_max=50000.0,
        salaire_devise="EUR",
        type_contrat="CDI",
        donnees_partielles=False,
    )
    champs.update(kw)
    oid, _ = db.enregistrer_offre(scorer(Offre(**champs)))
    return db.lire_offre(oid)


# --------------------------------------------------------------------------
# 1. Les deux axes ne se melangent jamais
# --------------------------------------------------------------------------


def test_une_offre_parfaite_mais_mal_documentee_garde_son_score_de_correspondance():
    o = _offre(description="Voir l'annonce.", donnees_partielles=True,
               salaire_min=None, salaire_max=None, salaire_devise=None)
    bilan = completude.evaluer(o)
    assert bilan.score < 50, "peu d'informations"
    assert o["score"] > 0, "le score de correspondance n'est pas touche"


def test_une_offre_mediocre_mais_bien_documentee_a_une_bonne_completude():
    o = _offre(titre="Assistant administratif", employeur="Une societe",
               description=ANNONCE_COMPLETE)
    bilan = completude.evaluer(o)
    assert bilan.score >= 60, bilan.manques


def test_le_bilan_ne_contient_aucune_moyenne_des_deux():
    """Verrou explicite : rien ne doit ressembler a une fusion des deux axes."""
    o = _offre()
    bilan = completude.evaluer(o)
    d = bilan.as_dict()
    assert "score_correspondance" not in d
    assert "score_global" not in d
    assert "moyenne" not in d
    assert set(d) >= {"score", "niveau", "manques", "acquis", "suffisant_pour_dossier"}


# --------------------------------------------------------------------------
# 2. Ce qui manque doit etre NOMME
# --------------------------------------------------------------------------


def test_un_extrait_de_trois_lignes_dit_precisement_ce_qui_manque():
    o = _offre(description="Ingenieur de test chez nous. Postulez.",
               donnees_partielles=True, salaire_min=None, salaire_max=None)
    bilan = completude.evaluer(o)
    assert not bilan.suffisant_pour_dossier
    libelles = " ".join(m.libelle.lower() for m in bilan.manques)
    assert "description" in libelles
    assert "salaire" in libelles
    assert bilan.manques, "il faut dire CE QUI manque, pas seulement que c'est insuffisant"
    for m in bilan.manques:
        assert m.quoi_faire, f"« {m.libelle} » ne dit pas quoi faire"


def test_chaque_manque_propose_une_action_realisable():
    o = _offre(description="Court.", donnees_partielles=True)
    for m in completude.evaluer(o).manques:
        assert len(m.quoi_faire) > 15
        assert not m.quoi_faire.lower().startswith("information")


def test_le_manque_de_description_dit_de_coller_le_texte_sans_nommer_de_bouton():
    """Le geste se dit sans nom de bouton : « Lire l'annonce » n'est pas sur les écrans de la
    préparation, où « Coller le texte de l'annonce » le porte, et un nom de bouton vieillit."""
    o = _offre(description="Court.", donnees_partielles=True)
    manque = next(m for m in completude.evaluer(o).manques
                  if "description" in m.libelle.lower())
    assert "colle" in manque.quoi_faire.lower()
    assert "«" not in manque.quoi_faire, manque.quoi_faire


def test_les_acquis_sont_nommes_aussi():
    """Il doit voir ce qu'il a, pas seulement ce qui lui manque."""
    bilan = completude.evaluer(_offre())
    assert bilan.acquis
    assert any("salaire" in a.lower() for a in bilan.acquis)


# --------------------------------------------------------------------------
# 3. Ce que le score mesure
# --------------------------------------------------------------------------


def test_la_description_complete_pese_le_plus_lourd():
    complet = completude.evaluer(_offre()).score
    extrait = completude.evaluer(
        _offre(description="Voir l'annonce.", donnees_partielles=True)
    ).score
    assert complet - extrait >= 25, (complet, extrait)


def test_le_salaire_connu_compte():
    avec = completude.evaluer(_offre()).score
    sans = completude.evaluer(
        _offre(salaire_min=None, salaire_max=None, salaire_devise=None)
    ).score
    assert avec > sans


def test_un_lieu_imprecis_compte_moins_quun_lieu_precis():
    precis = completude.evaluer(_offre()).score
    vague = completude.evaluer(_offre(lieu="Grand Est, France")).score
    assert precis > vague


def test_un_employeur_absent_est_signale():
    bilan = completude.evaluer(_offre(employeur=""))
    assert any("employeur" in m.libelle.lower() for m in bilan.manques)


def test_une_source_agregateur_vaut_moins_quune_source_primaire():
    primaire = completude.evaluer(
        _offre(url="https://carrieres-exemple.invalid/offre/primaire")).score
    agregee = completude.evaluer(
        _offre(url="https://arbeitnow.com/jobs/companies/x/y-123")).score
    assert primaire > agregee


# --------------------------------------------------------------------------
# 4. Le garde-fou sur la generation de dossier
# --------------------------------------------------------------------------


def test_une_offre_bien_documentee_passe():
    assert completude.evaluer(_offre()).suffisant_pour_dossier


def test_une_offre_a_extrait_ne_passe_pas():
    o = _offre(description="Voir l'annonce.", donnees_partielles=True,
               salaire_min=None, salaire_max=None)
    assert not completude.evaluer(o).suffisant_pour_dossier


def test_le_niveau_est_lisible_sans_calcul():
    for description, attendus in (
        (ANNONCE_COMPLETE, ("solide", "correct")),
        ("Voir l'annonce.", ("mince", "insuffisant")),
    ):
        o = _offre(description=description,
                   donnees_partielles=description == "Voir l'annonce.")
        assert completude.evaluer(o).niveau in attendus, completude.evaluer(o).niveau


# --------------------------------------------------------------------------
# 5. L'enrichissement fait monter la complétude — un seul mecanisme
# --------------------------------------------------------------------------


def test_coller_le_texte_complet_fait_monter_la_completude():
    from veille import enrichissement

    o = _offre(description="Ingenieur de test. Voir l'annonce.", donnees_partielles=True,
               salaire_min=None, salaire_max=None, salaire_devise=None)
    avant = completude.evaluer(o)
    assert not avant.suffisant_pour_dossier

    enrichissement.appliquer_texte(o["id"], ANNONCE_COMPLETE, "colle a la main")
    apres = completude.evaluer(db.lire_offre(o["id"]))
    assert apres.score > avant.score + 20, (avant.score, apres.score)
    assert apres.suffisant_pour_dossier


# --------------------------------------------------------------------------
# Le filtre « a documenter » — sa file de travail la plus rentable
#
# Score de correspondance eleve ET complétude sous le seuil : dix minutes de
# recherche les rendent candidatables. C'est le meilleur usage de son temps,
# donc ca ne doit pas se trouver au fond d'un panneau replie.
# --------------------------------------------------------------------------


def test_le_filtre_isole_le_bon_couple(client_completude):
    """Fort potentiel, information trop mince : ni l'un sans l'autre."""
    # Des intitules des familles de l'exemple : la correspondance est forte.
    bonne = _offre(titre="Testeuse fonctionnelle")      # correspondance ok, dossier ok
    a_documenter = _offre(titre="Automaticienne de tests",
                          description="Automatisation des tests web et mobile.",
                          donnees_partielles=True, salaire_min=None, salaire_max=None)
    faible = _offre(titre="Assistant administratif", employeur="Une societe",
                    description="Court.", donnees_partielles=True,
                    salaire_min=None, salaire_max=None)

    ids = [o["id"] for o in
           client_completude.get("/api/offres?a_documenter=true&limite=500").json()["offres"]]
    assert a_documenter["id"] in ids, "score eleve + dossier mince doit y etre"
    assert bonne["id"] not in ids, "bien documentee : rien a chercher"
    assert faible["id"] not in ids, "score trop bas : pas la peine d'y passer du temps"


def test_le_compte_est_rendu_avec_la_liste(client_completude):
    _offre(titre="Automaticienne de tests",
           description="Automatisation des tests web et mobile.",
           donnees_partielles=True, salaire_min=None, salaire_max=None)
    charge = client_completude.get("/api/offres?limite=500").json()
    assert "a_documenter" in charge, "le compte doit venir sans requete supplementaire"
    assert charge["a_documenter"] >= 1
