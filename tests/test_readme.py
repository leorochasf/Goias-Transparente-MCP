"""Os exemplos de linha de comando do README precisam ser aceitos pela CLI. Offline: só confere os argumentos."""
import re
import shlex
from pathlib import Path

import pytest

from transparencia_municipal.cli import _parser

README = Path(__file__).resolve().parents[1] / "README.md"
PREFIXO = "python -m transparencia_municipal.cli"


def _exemplos():
    blocos = re.findall(r"```bash\n(.*?)```", README.read_text(encoding="utf-8"), re.S)
    linhas = "\n".join(blocos).replace("\\\n", " ").splitlines()
    return [ln.strip()[len(PREFIXO):] for ln in linhas if ln.strip().startswith(PREFIXO)]


def test_readme_tem_exemplos_da_cli():
    assert len(_exemplos()) >= 3


@pytest.mark.parametrize("exemplo", _exemplos())
def test_exemplo_do_readme_e_aceito_pela_cli(exemplo):
    try:
        _parser().parse_args(shlex.split(exemplo))
    except SystemExit:
        pytest.fail(f"a CLI recusa o exemplo do README: {exemplo}")
