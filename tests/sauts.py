"""Les sauts faute de dependance systeme, et ou ils sont interdits.

Sous Windows, des tests se sautent : WeasyPrint, systemd utilisateur, groupes
de processus POSIX. La CI et le serveur ont tout, et la suite y est lancee avec
`SUITE_COMPLETE=1` : ces tests y tournent quoi qu'il arrive, si bien qu'une
dependance perdue (une mise a jour de Pango, un WeasyPrint qui ne s'importe
plus) y echoue bruyamment au lieu de se sauter en silence.
"""

from __future__ import annotations

import os
from collections.abc import Callable


def sauter(disponible: Callable[[], bool]) -> bool:
    """Vrai s'il faut sauter le test : sa dependance manque, et la suite n'est
    pas declaree complete. Une suite complete ne sonde meme pas la dependance."""
    if os.environ.get("SUITE_COMPLETE") == "1":
        return False
    return not disponible()
