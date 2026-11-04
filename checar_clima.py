"""
Projeto "Filas em Orlando": raio x paradas (regra 6 do pilar 2).

Por que raio e não chuva: os parques fecham as atrações ao ar livre quando há
raio na região; chuva sem raio pode não fechar nada. Por isso este script usa
os boletins meteorológicos (METAR) dos aeroportos perto dos parques, que
registram trovoada detectada por sensor:
    TS    trovoada a até ~5 milhas (8 km) da estação
    VCTS  trovoada nas proximidades, de ~5 a 10 milhas (8 a 16 km)
    LTG DSNT  raio distante, de ~10 a 30 milhas (só informativo)

Estações (aeroportos com boletim automático; distâncias aproximadas):
    ISM  Kissimmee Gateway           ~15 a 19 km dos parques da Disney
    MCO  Orlando International        ~16 km da Universal; ~27 km do Magic Kingdom
    ORL  Orlando Executive            ~15 km da Universal

Cada parada ganha uma marca (nada é apagado):
    raio                  atração ao ar livre (fecha com raio) e trovoada (TS ou
                          VCTS) registrada entre 60 min antes e 45 min depois do início
    raio_atracao_coberta  trovoada no mesmo intervalo, mas a atração é coberta
                          (provavelmente NÃO foi o clima)
    sem_raio              nenhuma trovoada registrada no intervalo
    sem_classificacao     atração fora da lista atracoes_ar_livre.csv

Limites (dizer nos posts): a estação fica a 15-27 km dos parques, então o raio
registrado pode estar longe do parque (ou um raio perto do parque pode não
aparecer); a regra exata de distância dos parques não é pública.

Como rodar (mesma pasta; depois do limpar_paradas.py):
    python checar_clima.py

Precisa do arquivo atracoes_ar_livre.csv na mesma pasta (quais atrações fecham
com raio; pode ser editado). Gera:
    dados/brutos/clima/metar_<inicio>_<fim>.csv   boletins brutos
    dados/tratados/paradas_clima.csv              paradas.csv + colunas de raio

Boletins: Iowa Environmental Mesonet (Iowa State University),
https://mesonet.agron.iastate.edu/ , a partir dos dados da NOAA/NWS.
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/New_York")
except Exception:
    sys.exit("ERRO: fuso horário não encontrado. No Windows, rode uma vez:\n    pip install tzdata")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
MINUTOS_ANTES = 60     # trovoada até 60 min antes do início da parada...
MINUTOS_DEPOIS = 45    # ...ou até 45 min depois. Calibrado em 04/11: os parques fecham as
                       # atrações antes de o aeroporto (a ~15 km) registrar a trovoada.
                       # Ex.: 10/10, Islands of Adventure parou entre 13h44 e 14h20; primeiro
                       # registro de trovoada às 14h29.

ESTACOES = {
    "magic-kingdom": ["ISM", "MCO"],
    "epcot": ["ISM", "MCO"],
    "hollywood-studios": ["ISM", "MCO"],
    "animal-kingdom": ["ISM", "MCO"],
    "universal-studios-florida": ["MCO", "ORL"],
    "islands-of-adventure": ["MCO", "ORL"],
    "epic-universe": ["MCO", "ORL"],
}

URL_IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

PASTA = Path(__file__).parent
PASTA_CLIMA = PASTA / "dados" / "brutos" / "clima"
PASTA_TRATADOS = PASTA / "dados" / "tratados"
ARQUIVO_AR_LIVRE = PASTA / "atracoes_ar_livre.csv"

# trovoada no corpo do boletim: TS, -TSRA, +TSRA, VCTS...
PADRAO_TS = re.compile(r"(?:^|\s)[-+]?(VC)?TS")


# ---------------------------------------------------------------------------
# Boletins dos aeroportos
# ---------------------------------------------------------------------------
def baixar_metar(inicio, fim):
    """Baixa (se ainda não existir) os boletins de todas as estações no período."""
    arquivo = PASTA_CLIMA / f"metar_{inicio}_{fim}_v2.csv"
    if arquivo.exists():
        print("  boletins já estavam baixados")
        return arquivo
    # A data final do serviço não entra e as horas são em UTC: pede dois dias a mais, para
    # cobrir as paradas do fim da tarde do último dia (corrigido em 04/11).
    ultimo = fim + timedelta(2)
    estacoes = sorted({e for lista in ESTACOES.values() for e in lista})
    params = [("station", e) for e in estacoes] + [
        ("data", "metar"), ("data", "wxcodes"), ("data", "p01i"),
        ("year1", inicio.year), ("month1", inicio.month), ("day1", inicio.day),
        ("year2", ultimo.year), ("month2", ultimo.month), ("day2", ultimo.day),
        ("tz", "Etc/UTC"), ("format", "onlycomma"), ("latlon", "no"),
        ("missing", "empty"), ("trace", "0.0001"), ("direct", "no"),
        ("report_type", "3"), ("report_type", "4"),
    ]
    try:
        resp = requests.get(URL_IEM, params=params, timeout=120,
                            headers={"User-Agent": "filas-orlando/1.0 (projeto de estudo)"})
    except requests.RequestException as erro:
        sys.exit(f"ERRO de conexão com a Iowa State ({erro.__class__.__name__}). "
                 "Confira a internet e rode de novo.")
    if resp.status_code != 200 or not resp.text.startswith("station"):
        sys.exit(f"ERRO ao baixar os boletins ({resp.status_code}):\n{resp.text[:500]}")
    PASTA_CLIMA.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(resp.text, encoding="utf-8")
    print(f"  boletins baixados: {resp.text.count(chr(10)) - 1} linhas")
    return arquivo


def ler_metar(arquivo):
    """Devolve {estacao: [(hora_utc, trovoada_perto, raio_distante, chuva_mm), ...]}."""
    boletins = defaultdict(list)
    with open(arquivo, encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            texto = linha.get("metar") or ""
            corpo, _, observacoes = texto.partition(" RMK")
            codigos = (linha.get("wxcodes") or "") + " " + corpo
            perto = bool(PADRAO_TS.search(codigos))
            distante = "LTG" in observacoes and "DSNT" in observacoes
            try:
                chuva = float(linha.get("p01i") or 0) * 25.4
            except ValueError:
                chuva = 0.0
            hora = datetime.strptime(linha["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            boletins[linha["station"]].append((hora, perto, distante, chuva))
    for lista in boletins.values():
        lista.sort(key=lambda b: b[0])
    return boletins


def raio_perto_da_parada(boletins, estacoes, inicio):
    """Trovoada (TS/VCTS), raio distante e chuva máxima nas estações do parque, perto do início."""
    de, ate = inicio - timedelta(minutes=MINUTOS_ANTES), inicio + timedelta(minutes=MINUTOS_DEPOIS)
    achados = [b for e in estacoes for b in boletins.get(e, []) if de <= b[0] <= ate]
    if not achados:
        return None
    return (any(b[1] for b in achados), any(b[2] for b in achados), max(b[3] for b in achados))


# ---------------------------------------------------------------------------
# Cruzamento
# ---------------------------------------------------------------------------
def ler_csv(caminho):
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    if not (PASTA_TRATADOS / "paradas.csv").exists():
        sys.exit("ERRO: rode antes o limpar_paradas.py (falta dados/tratados/paradas.csv).")
    if not ARQUIVO_AR_LIVRE.exists():
        sys.exit("ERRO: falta o arquivo atracoes_ar_livre.csv nesta pasta.")
    paradas = ler_csv(PASTA_TRATADOS / "paradas.csv")
    atracoes_dia = ler_csv(PASTA_TRATADOS / "atracoes_dia.csv")
    if "porte" not in paradas[0]:
        sys.exit("ERRO: o paradas.csv é da versão antiga. Rode de novo o limpar_paradas.py novo.")
    ar_livre = {(l["parque"], l["atracao"]): l["fecha_com_raio"] == "sim" for l in ler_csv(ARQUIVO_AR_LIVRE)}

    sem_lista = sorted({(a["parque"], a["atracao"]) for a in atracoes_dia
                        if a["porte"] != "sem_fila" and (a["parque"], a["atracao"]) not in ar_livre})
    for parque, nome in sem_lista:
        print(f"  ATENÇÃO: '{nome}' ({parque}) tem fila mas não está no atracoes_ar_livre.csv")

    inicio = date.fromisoformat(min(p["data"] for p in paradas))
    fim = date.fromisoformat(max(p["data"] for p in paradas))
    print(f"Boletins de {inicio} a {fim}:")
    boletins = ler_metar(baixar_metar(inicio, fim))
    for estacao in sorted({e for lista in ESTACOES.values() for e in lista}):
        n = len(boletins.get(estacao, []))
        print(f"  {estacao}: {n} boletins, {sum(b[1] for b in boletins.get(estacao, []))} com trovoada")
        if n == 0:
            print(f"  ATENÇÃO: nenhum boletim da estação {estacao}.")

    sem_boletim = 0
    for p in paradas:
        hora = datetime.fromisoformat(p["inicio_local"]).astimezone(timezone.utc)
        r = raio_perto_da_parada(boletins, ESTACOES[p["parque"]], hora)
        externa = ar_livre.get((p["parque"], p["atracao"]))
        if r is None:
            sem_boletim += 1
            p.update(trovoada_perto="", raio_distante="", chuva_mm_max="", fecha_com_raio="",
                     marca_clima="sem_boletim")
            continue
        perto, distante, chuva = r
        p.update(trovoada_perto="sim" if perto else "não", raio_distante="sim" if distante else "não",
                 chuva_mm_max=round(chuva, 1),
                 fecha_com_raio="" if externa is None else ("sim" if externa else "não"),
                 marca_clima=("sem_classificacao" if externa is None else
                              "raio" if perto and externa else
                              "raio_atracao_coberta" if perto else "sem_raio"))

    with open(PASTA_TRATADOS / "paradas_clima.csv", "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(paradas[0].keys()))
        escritor.writeheader()
        escritor.writerows(paradas)

    resumo(paradas, atracoes_dia, ar_livre, boletins)
    if sem_boletim:
        print(f"\nATENÇÃO: {sem_boletim} paradas sem nenhum boletim no intervalo (buraco nos boletins).")
    print(f"\nArquivo gravado: {PASTA_TRATADOS / 'paradas_clima.csv'}")
    print("Boletins: Iowa Environmental Mesonet (Iowa State University), dados NOAA/NWS.")


def resumo(paradas, atracoes_dia, ar_livre, boletins):
    """Conferência no terminal (NÃO publicar sem revisão)."""
    contam = [p for p in paradas if p["conta_10min"] == "sim" and p["porte"] != "sem_fila"]

    # 1) o sinal funciona? Paradas de atrações ao ar livre devem coincidir mais com trovoada
    print("\nO sinal de raio funciona? (paradas de 10 min ou mais, atrações com fila)")
    for rotulo, valor in [("ao ar livre", "sim"), ("cobertas", "não")]:
        grupo = [p for p in contam if p["fecha_com_raio"] == valor]
        com_ts = sum(p["trovoada_perto"] == "sim" for p in grupo)
        print(f"  {rotulo:12s}: {com_ts} de {len(grupo)} paradas com trovoada perto "
              f"({com_ts / len(grupo) if grupo else 0:.0%})")
    print("  (se as ao ar livre não tiverem bem mais que as cobertas, o sinal está fraco)")

    # 2) por parque: paradas por 10 horas de operação, com e sem as paradas de raio
    todas_contam = [p for p in paradas if p["conta_10min"] == "sim"]
    reguas = {"todas": ("sem_fila", "menor", "grande"), "grandes": ("grande",)}
    print("\nParadas de 10 min ou mais por 10 horas de operação (com raio -> sem raio):")
    print(f"{'Parque':27s} " + " ".join(f"{r:>17s}" for r in reguas))
    for parque in sorted({l["parque"] for l in atracoes_dia}):
        partes = []
        for aceitos in reguas.values():
            linhas = [l for l in atracoes_dia if l["parque"] == parque and l["porte"] in aceitos]
            chaves = {(l["parque"], l["data"], l["atracao"]) for l in linhas}
            horas = sum(float(l["min_funcionando"]) + float(l["min_parada"]) for l in linhas) / 60
            n = [p for p in todas_contam if (p["parque"], p["data"], p["atracao"]) in chaves]
            sem = [p for p in n if p["marca_clima"] != "raio"]
            partes.append(f"{len(n) / horas * 10:8.2f} -> {len(sem) / horas * 10:5.2f}" if horas else f"{'-':>17s}")
        print(f"{parque:27s} " + " ".join(partes))

    # 3) dias com mais paradas por raio
    print("\nDias com mais paradas marcadas como 'raio':")
    por_dia = Counter((p["parque"], p["data"]) for p in contam if p["marca_clima"] == "raio")
    for (parque, dia), n in por_dia.most_common(10):
        horas_ts = sorted({b[0].astimezone(FUSO).strftime("%H:%M")
                           for e in ESTACOES[parque] for b in boletins.get(e, [])
                           if b[1] and b[0].astimezone(FUSO).date().isoformat() == dia})
        print(f"  {dia} {parque:27s} {n:3d} paradas | trovoada nos boletins: "
              f"{', '.join(horas_ts[:6])}{' ...' if len(horas_ts) > 6 else ''}")


if __name__ == "__main__":
    main()
