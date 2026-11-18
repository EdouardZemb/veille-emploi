"""Les messages de la ligne de commande renvoient aux écrans qui existent (lot 3 de l'ADR-0003).

Depuis le lot 3, l'archive est au Bilan, les offres mises de côté se trouvent par le filtre d'état
de Toutes les offres, et un appareil s'abonne aux notifications dans Plus › Réglages : l'en-tête
n'a plus de bouton « Notifications ». Les clés VAPID naissent au démarrage de la console, dans
tous les modes : `veille init` est retirée (la fin du mode systemd). Les messages restent sans
accents, comme leurs voisins.
"""

from __future__ import annotations

import argparse

from veille import cli, db, notifications, verification


def test_verifier_renvoie_au_bilan_pour_les_archivees(monkeypatch, capsys):
    monkeypatch.setattr(
        verification, "passe", lambda **k: verification.Rapport(sondees=[1], archivees=[1])
    )
    assert cli.cmd_verifier(argparse.Namespace(limite=60, sans_enrichir=True)) == 0
    sortie = capsys.readouterr().out
    assert "1 offre(s) archivees. Plus › Bilan pour les voir, " in sortie
    assert "Archive pour" not in sortie


def test_rescorer_renvoie_au_filtre_d_etat_pour_les_mises_de_cote(monkeypatch, capsys):
    monkeypatch.setattr(db, "rescorer_tout", lambda: (3, 0, 0, 2))
    assert cli.cmd_rescorer(argparse.Namespace()) == 0
    sortie = capsys.readouterr().out
    assert (
        "2 offre(s) mise(s) de cote : recevables plus tard, consultables par le filtre d'etat "
        "« Mises de cote » de Plus › Toutes les offres, et dans le Bilan." in sortie
    )
    assert "filtre Statut" not in sortie


def test_tester_notification_dit_ou_naissent_les_cles_et_ou_s_abonner(monkeypatch, tmp_path,
                                                                      capsys):
    monkeypatch.setattr(notifications, "CHEMIN_VAPID", tmp_path / "absent.json")
    db.initialiser()
    for a in db.lister_abonnements():
        db.supprimer_abonnement(a["endpoint"])
    cli.cmd_tester_notification(argparse.Namespace(envoyer=False))
    sortie = capsys.readouterr().out
    assert "  cles VAPID absentes : elles naissent au demarrage de la console\n" in sortie
    assert "veille init" not in sortie
    assert "Il faut d'abord ouvrir la console sur le telephone, puis" in sortie
    assert "Plus › Reglages, « Activer les notifications »" in sortie
    assert "lance `veille init`" not in sortie
    assert "tailnet" not in sortie
