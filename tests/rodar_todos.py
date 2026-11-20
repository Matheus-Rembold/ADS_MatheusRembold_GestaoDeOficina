"""
Roda a suíte inteira e mostra o placar de cada teste.

Rode da raiz do projeto, com o venv ativo:
    python -m tests.rodar_todos
    python -m tests.rodar_todos os notificacao   # só os que contêm esses nomes

Cada teste roda num processo separado (como se fosse chamado à mão), contra o
PostgreSQL do .env (ou do DB_NAME do ambiente). Todos limpam o que criam.
Sai com código 0 se tudo passou e 1 se algo falhou.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Ordem de dependência dos módulos (RF01 -> RF10)
TESTES = [
    "testar_models",
    "testar_cliente_repository",
    "testar_cliente_service",
    "testar_veiculo_service",
    "testar_produto_service",
    "testar_movimentacao_service",
    "testar_os_service",
    "testar_documento_os",
    "testar_agendamento_service",
    "testar_relatorio_service",
    "testar_paginacao_service",
    "testar_notificacao_service",
    "testar_autenticacao_service",
    "testar_usuario_service",
    "testar_permissoes",
]

RAIZ = Path(__file__).resolve().parent.parent
_PLACAR = re.compile(r"Resultado:\s*(\d+)/(\d+)")


def rodar(nome: str) -> tuple:
    """(passou?, texto do placar, segundos, saída) de um teste."""
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", QT_QPA_PLATFORM="offscreen")
    inicio = time.perf_counter()
    proc = subprocess.run([sys.executable, "-m", f"tests.{nome}"], cwd=RAIZ, env=ambiente,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    segundos = time.perf_counter() - inicio
    saida = proc.stdout + proc.stderr
    placar = _PLACAR.findall(saida)
    falhas = saida.count("[FALHOU]")
    if placar:
        ok, total = map(int, placar[-1])
        texto = f"{ok}/{total}"
        passou = proc.returncode == 0 and ok == total and falhas == 0
    else:  # testes antigos que só imprimem (models, repository): basta rodar sem erro
        texto = "sem placar"
        passou = proc.returncode == 0 and falhas == 0 and "Traceback" not in saida
    return passou, texto, segundos, saida


def main() -> None:
    filtros = [a.lower() for a in sys.argv[1:]]
    escolhidos = [t for t in TESTES if not filtros or any(f in t for f in filtros)]
    banco = os.getenv("DB_NAME") or "(o do .env)"
    print(f"Rodando {len(escolhidos)} teste(s) no banco {banco}...\n")
    falharam = []
    total_ok = total_verif = 0
    for nome in escolhidos:
        passou, texto, segundos, saida = rodar(nome)
        print(f"  [{'OK' if passou else 'FALHOU'}] {nome:<32} {texto:>10}   {segundos:5.1f} s", flush=True)
        if m := _PLACAR.findall(saida):
            ok, total = map(int, m[-1])
            total_ok, total_verif = total_ok + ok, total_verif + total
        if not passou:
            falharam.append((nome, saida))
    print(f"\nTotal: {total_ok}/{total_verif} verificações; "
          f"{len(escolhidos) - len(falharam)}/{len(escolhidos)} testes passaram.")
    for nome, saida in falharam:
        print(f"\n===== {nome}: o que falhou =====")
        linhas = [l for l in saida.splitlines() if "FALHOU" in l or "Error" in l or "Traceback" in l]
        print("\n".join(linhas[-15:]) or saida[-1500:])
    raise SystemExit(1 if falharam else 0)


if __name__ == "__main__":
    main()
