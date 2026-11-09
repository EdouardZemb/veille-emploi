"""Les cinq états d'une offre et la file « À faire » (ADR-0003, § 1).

Module pur : aucune lecture de base, d'horloge ni de configuration. Tout arrive
en paramètre. Les onze statuts de `models.STATUTS` restent ceux de la base ;
l'état n'en est qu'une lecture, jamais écrite.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

ETATS: tuple[str, ...] = ("a_voir", "je_postule", "envoyee", "entretien", "close")
MISE_DE_COTE = "mise_de_cote"

# La seule traduction du statut vers l'état.
_ETAT_DU_STATUT: dict[str, str] = {
    "nouveau": "a_voir",
    "a_traiter": "a_voir",
    "interessante": "je_postule",
    "candidature_envoyee": "envoyee",
    "relance_envoyee": "envoyee",
    "reponse_recue": "envoyee",
    "entretien": "entretien",
    "ecartee": "close",
    "refus": "close",
    "accepte": "close",
    "differee": MISE_DE_COTE,
}

_STATUTS_RELANCABLES = ("candidature_envoyee", "relance_envoyee")
_ORDRE_RAISON = {"relance_due": 0, "a_envoyer": 1, "a_preparer": 2}


def etat_de(offre: Mapping[str, Any]) -> str:
    statut = offre.get("statut")
    try:
        return _ETAT_DU_STATUT[statut]
    except (KeyError, TypeError):
        raise ValueError(f"statut sans état : {statut!r}") from None


def raison_a_finir(offre: Mapping[str, Any], aujourd_hui: date) -> str | None:
    statut = offre.get("statut")
    if statut in _STATUTS_RELANCABLES:
        due = offre.get("date_relance_due")
        if due and due <= aujourd_hui.isoformat():
            return "relance_due"
        return None
    if statut == "interessante":
        return "a_envoyer" if offre.get("dossier_chemin") else "a_preparer"
    return None


def _score(offre: Mapping[str, Any]) -> float:
    return offre.get("score") or 0


def _collecte(offre: Mapping[str, Any]) -> str:
    return offre.get("date_collecte") or ""


def _par_score(offres: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score décroissant ; à score égal, la collecte la plus récente d'abord."""
    triees = sorted(offres, key=_collecte, reverse=True)
    return sorted(triees, key=_score, reverse=True)


def _par_relance(offres: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Échéance croissante, les dates absentes en dernier ; puis le meilleur score."""
    return sorted(
        _par_score(offres),
        key=lambda o: (o.get("date_relance_due") is None, o.get("date_relance_due") or ""),  # pragma: no mutate
    )


def composer_a_faire(
    offres: list[dict[str, Any]],
    seuil: float,
    aujourd_hui: date,
    limite_a_voir: int = 50,
) -> dict[str, Any]:
    a_finir: list[dict[str, Any]] = []
    a_voir: list[dict[str, Any]] = []
    plus_tard: list[dict[str, Any]] = []
    for source in offres:
        etat = etat_de(source)
        offre = {**source, "etat": etat}
        if etat == "a_voir":
            # Une annonce disparue n'est plus à voir ; une candidature, elle, continue.
            if source.get("archivee_le"):
                continue
            if source["statut"] == "a_traiter":
                plus_tard.append(offre)
            elif _score(source) >= seuil:
                a_voir.append(offre)
            continue
        raison = raison_a_finir(source, aujourd_hui)
        if raison:
            a_finir.append({**offre, "raison": raison})

    a_finir = _par_score(a_finir)
    a_finir.sort(key=lambda o: _ORDRE_RAISON[o["raison"]])
    relances = _par_relance([o for o in a_finir if o["raison"] == "relance_due"])
    autres = [o for o in a_finir if o["raison"] != "relance_due"]
    a_voir = _par_score(a_voir)
    return {
        "a_finir": relances + autres,
        "a_voir": a_voir[:limite_a_voir],
        "a_voir_restantes": max(0, len(a_voir) - limite_a_voir),
        "plus_tard": _par_score(plus_tard),
    }


def grouper_candidatures(offres: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    je_postule: list[dict[str, Any]] = []
    envoyee: list[dict[str, Any]] = []
    entretien: list[dict[str, Any]] = []
    for source in offres:
        etat = etat_de(source)
        offre = {**source, "etat": etat}
        if etat == "je_postule":
            je_postule.append({**offre, "dossier": bool(source.get("dossier_chemin"))})
        elif etat == "envoyee":
            envoyee.append(offre)
        elif etat == "entretien":
            entretien.append(offre)
    return {
        "je_postule": _par_score(je_postule),
        "envoyee": _par_relance(envoyee),
        "entretien": _par_score(entretien),
    }
