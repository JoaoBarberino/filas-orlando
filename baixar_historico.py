"""
Projeto "Filas em Orlando": carga inicial do histórico.

Baixa, da API da ThemeParks.wiki, o histórico minuto a minuto (fila anunciada,
status das atrações e preço da fila paga) dos 7 parques de Orlando, para todos
os dias que a sua chave alcança (30 dias na conta gratuita), mais o horário de
funcionamento de cada parque.

Como rodar (dentro desta pasta):
    pip install requests
    python baixar_historico.py

A chave da API fica no arquivo .env desta pasta (veja .env.exemplo).
O script pode ser rodado de novo quantas vezes quiser: ele pula os dias já
baixados e só busca o que falta.

Dados: Powered by ThemeParks.wiki (https://themeparks.wiki).
Os termos de uso NÃO permitem publicar estes dados brutos. Guarde a pasta
"dados" só para você.
"""

import gzip
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

PASTA = Path(__file__).parent
BASE = os.environ.get("THEMEPARKS_BASE_URL", "https://api.themeparks.wiki/v1")
PAUSA_ENTRE_CHAMADAS = 1.0  # segundos; educado com a API e bem abaixo dos limites

PARQUES = {
    "magic-kingdom": "75ea578a-adc8-4116-a54d-dccb60765ef9",
    "epcot": "47f90d2c-e191-4239-a466-5892ef59a88b",
    "hollywood-studios": "288747d1-8b4f-4a64-867e-ea7c9b27bad8",
    "animal-kingdom": "1c84a229-8862-4648-9c71-378ddd2c7693",
    "universal-studios-florida": "eb3f4560-2383-4a36-9152-6b3e5ed6bc57",
    "islands-of-adventure": "267615cc-8943-4c2a-ae2c-5da728ca591f",
    "epic-universe": "12dbb85b-265f-44e6-bccf-f1faa17211fc",
}

PASTA_HISTORICO = PASTA / "dados" / "brutos" / "historico"
PASTA_HORARIOS = PASTA / "dados" / "brutos" / "horarios"


# ---------------------------------------------------------------------------
# Chave e sessão
# ---------------------------------------------------------------------------
def ler_chave():
    """Lê THEMEPARKS_API_KEY do ambiente ou do arquivo .env desta pasta."""
    chave = os.environ.get("THEMEPARKS_API_KEY", "").strip()
    arquivo = PASTA / ".env"
    if not chave and arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha.startswith("THEMEPARKS_API_KEY="):
                chave = linha.split("=", 1)[1].strip().strip('"').strip("'")
    if not chave or chave == "cole_sua_chave_aqui":
        sys.exit(
            "ERRO: chave não encontrada.\n"
            "Crie um arquivo chamado .env nesta pasta com a linha:\n"
            "THEMEPARKS_API_KEY=sua_chave"
        )
    return chave


def criar_sessao(chave):
    sessao = requests.Session()
    sessao.headers.update({
        "X-API-Key": chave,
        "User-Agent": "filas-orlando/1.0 (projeto de estudo; github.com/JoaoBarberino)",
    })
    return sessao


def chamar(sessao, caminho, params=None, tentativas=5):
    """GET com tratamento de limite (429) e de falhas temporárias de rede/servidor."""
    for tentativa in range(1, tentativas + 1):
        try:
            resp = sessao.get(f"{BASE}{caminho}", params=params, timeout=60)
        except requests.RequestException as erro:
            espera = 10 * tentativa
            print(f"    falha de rede ({erro.__class__.__name__}); tentando de novo em {espera}s")
            time.sleep(espera)
            continue

        if resp.status_code == 429:
            espera = 60
            try:
                espera = int(resp.json().get("error", {}).get("retryAfter", 60))
            except (ValueError, AttributeError):
                pass
            espera = int(resp.headers.get("Retry-After", espera))
            print(f"    limite da API atingido; esperando {espera}s")
            time.sleep(espera + 1)
            continue

        if resp.status_code >= 500:
            espera = 15 * tentativa
            print(f"    erro {resp.status_code} no servidor; tentando de novo em {espera}s")
            time.sleep(espera)
            continue

        return resp
    return None


# ---------------------------------------------------------------------------
# Passo 1: conferir a chave
# ---------------------------------------------------------------------------
def conferir_chave(sessao):
    resp = chamar(sessao, "/me")
    if resp is None or resp.status_code != 200:
        codigo = resp.status_code if resp is not None else "sem resposta"
        sys.exit(f"ERRO ao conferir a chave ({codigo}). Confira se ela foi copiada inteira.")
    me = resp.json()
    print("Chave OK")
    print(f"  plano: {me.get('tier')}")
    print(f"  dias de histórico: {me.get('historyDays')}")
    print(f"  dia mais antigo disponível: {me.get('historyEarliestDate')}")
    orcamento = me.get("historyRateLimit") or {}
    if not orcamento.get("unmetered"):
        print(f"  chamadas de histórico restantes nesta hora: "
              f"{orcamento.get('remaining')} de {orcamento.get('limit')}")
    return me


# ---------------------------------------------------------------------------
# Passo 2: histórico dia a dia
# ---------------------------------------------------------------------------
def baixar_historico(sessao, inicio, fim):
    dias = [inicio + timedelta(d) for d in range((fim - inicio).days + 1)]
    total = len(dias) * len(PARQUES)
    feitos = baixados = pulados = falhas = 0
    print(f"\nHistórico de {inicio} a {fim}: {len(dias)} dias x {len(PARQUES)} parques = {total} arquivos")

    for nome, id_parque in PARQUES.items():
        pasta = PASTA_HISTORICO / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for dia in dias:
            feitos += 1
            arquivo = pasta / f"{dia.isoformat()}.json.gz"
            if arquivo.exists():
                pulados += 1
                continue

            resp = chamar(sessao, f"/entity/{id_parque}/history", {"date": dia.isoformat()})
            time.sleep(PAUSA_ENTRE_CHAMADAS)

            if resp is None:
                falhas += 1
                print(f"  [{feitos}/{total}] {nome} {dia}: sem resposta (rode o script de novo depois)")
                continue
            if resp.status_code == 403:
                print(f"  [{feitos}/{total}] {nome} {dia}: fora da janela da sua chave, pulado")
                continue
            if resp.status_code != 200:
                falhas += 1
                print(f"  [{feitos}/{total}] {nome} {dia}: erro {resp.status_code}")
                continue

            # grava primeiro num arquivo temporário: se o script cair no meio,
            # não fica um arquivo pela metade que seria pulado na próxima vez
            temporario = arquivo.with_suffix(".tmp")
            with gzip.open(temporario, "wb") as f:
                f.write(resp.content)
            temporario.replace(arquivo)
            baixados += 1
            print(f"  [{feitos}/{total}] {nome} {dia}: ok ({len(resp.content) // 1024} KB)")

    print(f"\nHistórico: {baixados} baixados, {pulados} já existiam, {falhas} com falha")
    return falhas


# ---------------------------------------------------------------------------
# Passo 3: horários de funcionamento (e preços da fila paga por dia)
# ---------------------------------------------------------------------------
def baixar_horarios(sessao, inicio, fim):
    meses = sorted({(d.year, d.month) for d in
                    (inicio + timedelta(n) for n in range((fim - inicio).days + 1))})
    print(f"\nHorários de funcionamento: meses {', '.join(f'{m:02d}/{a}' for a, m in meses)}")
    for nome, id_parque in PARQUES.items():
        pasta = PASTA_HORARIOS / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for ano, mes in meses:
            resp = chamar(sessao, f"/entity/{id_parque}/schedule/{ano}/{mes:02d}")
            time.sleep(PAUSA_ENTRE_CHAMADAS)
            if resp is not None and resp.status_code == 200:
                (pasta / f"{ano}-{mes:02d}.json").write_text(resp.text, encoding="utf-8")
            else:
                codigo = resp.status_code if resp is not None else "sem resposta"
                print(f"  {nome} {mes:02d}/{ano}: erro {codigo}")
    print("  horários salvos")


# ---------------------------------------------------------------------------
# Passo 4: primeira olhada nos dados (conferência)
# ---------------------------------------------------------------------------
def resumo():
    print("\nPrimeira olhada (paradas = mudanças para o status DOWN, sem nenhum filtro ainda):")
    total_bytes = 0
    for nome in PARQUES:
        arquivos = sorted((PASTA_HISTORICO / nome).glob("*.json.gz"))
        paradas = atracoes = 0
        for arquivo in arquivos:
            total_bytes += arquivo.stat().st_size
            with gzip.open(arquivo, "rt", encoding="utf-8") as f:
                dados = json.load(f)
            for entidade in dados.get("entities", []):
                if entidade.get("entityType") != "ATTRACTION":
                    continue
                atracoes += 1
                anterior = (entidade.get("opening") or {}).get("status")
                for linha in entidade.get("history", []):
                    status = linha.get("status")
                    if status and status != anterior:
                        if status == "DOWN":
                            paradas += 1
                        anterior = status
        if arquivos:
            media = atracoes / len(arquivos)
            print(f"  {nome:26s} {len(arquivos):3d} dias | ~{media:.0f} atrações por dia | {paradas} paradas")
    print(f"\nEspaço em disco: {total_bytes / 1024 / 1024:.1f} MB (compactado)")
    print("Lembrete: esses números ainda incluem paradas fora do horário do parque e por clima.")


def main():
    print(f"Início: {datetime.now():%d/%m/%Y %H:%M}\n")
    sessao = criar_sessao(ler_chave())
    me = conferir_chave(sessao)

    mais_antigo = me.get("historyEarliestDate")
    inicio = date.fromisoformat(mais_antigo[:10]) if mais_antigo else date.today() - timedelta(29)
    fim = date.today() - timedelta(1)  # ontem: o dia de hoje ainda não terminou

    falhas = baixar_historico(sessao, inicio, fim)
    baixar_horarios(sessao, inicio, fim)
    resumo()

    if falhas:
        print("\nAlguns dias falharam. Rode o script de novo: ele só busca o que falta.")
    print(f"\nFim: {datetime.now():%d/%m/%Y %H:%M}")


if __name__ == "__main__":
    main()
