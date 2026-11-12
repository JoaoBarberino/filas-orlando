"""
Projeto "Filas em Orlando": frequência x duração das paradas (pilar 2, post 2).

Como rodar (a partir da raiz do projeto; depois do limpar_paradas.py e do checar_clima.py; NÃO rode o
limpar_paradas.py de novo antes, porque o porte é recalculado com os dias novos):
    python src/frequencia_duracao.py
Só lê os CSVs de dados/tratados; não grava nada. NÃO publicar sem revisão.

Versão revisada (11/11/2026) depois de uma auditoria independente. Mudanças:
  1. Contagem de 10 min pela coluna conta_10min e régua "grandes" pela coluna porte, como o
     carrossel_estreia.py (que gerou os números publicados). O original usava duracao_min >= 10
     e fila_media_min >= 20, que são valores ARREDONDADOS a 0,1: uma parada de 9,97 min ou uma
     atração com fila média de 19,97 min entravam no original e não na estreia.
     CRITERIO = "robustez" volta ao critério antigo (o do robustez.py).
  2. "Dia inteiro" pela definição da regra 3 (exceção): atração-dia com 0 min funcionando e
     parada > 0 (vem do atracoes_dia.csv). O original exigia uma parada que começasse
     exatamente na abertura E terminasse exatamente no fechamento, e por isso não achava casos
     como "CLOSED até 9h07 e DOWN até fechar". A sensibilidade tira a atração-dia inteira
     (paradas, horas e minutos parados), não só a parada mais longa.
  3. Conferência com a estreia por valor arredondado (0,41 x 0,42 agora avisa) e com os dois
     critérios lado a lado, para explicar a diferença.
  4. Reamostragem guarda cada réplica por índice (o zip do original desalinhava as réplicas se um
     parque faltasse em alguma) e calcula também a chance pareada da FREQUÊNCIA Epic > Islands.
  5. Duração também por minutos_parada (só minutos DOWN, sem as voltas curtas do meio),
     paradas cortadas na abertura, taxa de paradas longas por 10 h (não depende do corte de 10 min)
     e comparação no nível da atração (uma mediana por atração; permutação).
  6. Avisos de dado estranho: atração-dia repetida, parada sem atração-dia, minutos de raio maiores
     que os minutos parados, período vazio.
"""

import csv
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA_INICIO = "2026-10-05"
DATA_FIM = "2026-11-03"
CRITERIO = "estreia"          # "estreia" (colunas conta_10min e porte) ou "robustez" (valores arredondados)
CORTE_GRANDE = 20
MINIMO = 10
LONGA = 60
REPETICOES = 2000
PERMUTACOES = 20000
SEMENTE = 12

PUBLICADO = {
    "todas": {"epic-universe": 0.67, "islands-of-adventure": 0.59, "universal-studios-florida": 0.50,
              "hollywood-studios": 0.41, "magic-kingdom": 0.27, "epcot": 0.25, "animal-kingdom": 0.08},
    "grandes": {"islands-of-adventure": 0.83, "epic-universe": 0.77, "epcot": 0.68,
                "universal-studios-florida": 0.51, "hollywood-studios": 0.45, "magic-kingdom": 0.43,
                "animal-kingdom": 0.18},
}
NOMES = {
    "magic-kingdom": "Magic Kingdom", "epcot": "EPCOT", "hollywood-studios": "Hollywood Studios",
    "animal-kingdom": "Animal Kingdom", "universal-studios-florida": "Universal Studios",
    "islands-of-adventure": "Islands of Adventure", "epic-universe": "Epic Universe",
}
PASTA = Path(__file__).resolve().parent.parent / "dados" / "tratados"   # raiz do projeto (este script fica em src/)
NAN = float("nan")


def ler(nome):
    caminho = PASTA / nome
    if not caminho.exists():
        sys.exit(f"ERRO: falta {caminho}. Rode antes o limpar_paradas.py e o checar_clima.py.")
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def no_periodo(l):
    return DATA_INICIO <= l["data"] <= DATA_FIM


def chave(l):
    return (l["parque"], l["data"], l["atracao"])


def eh_grande(l, criterio):
    if criterio == "estreia" and "porte" in l:
        return l["porte"] == "grande"
    return (float(l["fila_media_min"]) if l["fila_media_min"] else 0.0) >= CORTE_GRANDE


def conta(p, minimo, criterio):
    if criterio == "estreia" and minimo == 10 and "conta_10min" in p:
        return p["conta_10min"] == "sim"
    return float(p["duracao_min"]) >= minimo


def montar(atracoes_dia, paradas, regua, minimo=MINIMO, criterio=CRITERIO, sem_dia_inteiro=False):
    por_chave = defaultdict(list)
    for p in paradas:
        if no_periodo(p):
            por_chave[chave(p)].append(p)
    linhas = []
    for l in atracoes_dia:
        if not no_periodo(l) or (regua == "grandes" and not eh_grande(l, criterio)):
            continue
        func, parada = float(l["min_funcionando"]), float(l["min_parada"])
        if func + parada <= 0:
            continue
        dia_inteiro = func == 0 and parada > 0
        if sem_dia_inteiro and dia_inteiro:
            continue
        ps = por_chave[chave(l)]
        contadas = [p for p in ps if conta(p, minimo, criterio) and p["marca_clima"] != "raio"]
        linhas.append({
            "parque": l["parque"], "data": l["data"], "atracao": l["atracao"],
            "func": func, "parada": parada, "dia_inteiro": dia_inteiro,
            "raio_min": sum(float(p["minutos_parada"]) for p in ps if p["marca_clima"] == "raio"),
            "duracoes": [float(p["duracao_min"]) for p in contadas],
            "so_down": [float(p["minutos_parada"]) for p in contadas],
            "fechamento": sum(p["parada_ate_fechamento"] == "sim" for p in contadas),
            "abertura": sum(p["ja_parada_na_abertura"] == "sim" for p in contadas),
        })
    return linhas


def medidas(linhas):
    func = sum(l["func"] for l in linhas)
    parada = sum(l["parada"] for l in linhas)
    raio = sum(l["raio_min"] for l in linhas)
    dur = [d for l in linhas for d in l["duracoes"]]
    so_down = [d for l in linhas for d in l["so_down"]]
    n = len(dur)
    horas_op = (func + parada) / 60
    sem_raio = max(parada - raio, 0)
    return {
        "n": n, "horas_op": horas_op,
        "freq": n / horas_op * 10 if horas_op else NAN,
        "longas_10h": sum(d > LONGA for d in dur) / horas_op * 10 if horas_op else NAN,
        "mediana": statistics.median(dur) if dur else NAN,
        "mediana_so_down": statistics.median(so_down) if so_down else NAN,
        "media": statistics.fmean(dur) if dur else NAN,
        "longas": sum(d > LONGA for d in dur) / n if n else NAN,
        "disp": func / (func + sem_raio) if func + sem_raio else NAN,
        "horas_paradas": sem_raio / 60,
        "horas_entre": func / 60 / n if n else NAN,
        "fechamento": sum(l["fechamento"] for l in linhas),
        "abertura": sum(l["abertura"] for l in linhas),
        "dia_inteiro": sum(l["dia_inteiro"] for l in linhas),
        "atracoes": len({l["atracao"] for l in linhas}),
    }


def por_parque(linhas):
    g = defaultdict(list)
    for l in linhas:
        g[l["parque"]].append(l)
    return {p: medidas(x) for p, x in g.items()}


def intervalo(valores, baixo=0.05, alto=0.95):
    v = sorted(x for x in valores if x == x)
    if not v:
        return NAN, NAN
    return v[int(baixo * (len(v) - 1))], v[int(alto * (len(v) - 1))]


def reamostrar(linhas, modo):
    """Lista de réplicas; cada réplica é {parque: medidas}. Parque ausente = ausente do dict."""
    rng = random.Random(SEMENTE)
    replicas = []
    if modo == "dia":
        por_dia = defaultdict(list)
        for l in linhas:
            por_dia[l["data"]].append(l)
        dias = sorted(por_dia)
        for _ in range(REPETICOES):
            replicas.append(por_parque([l for d in rng.choices(dias, k=len(dias)) for l in por_dia[d]]))
    else:
        por_atr = defaultdict(lambda: defaultdict(list))
        for l in linhas:
            por_atr[l["parque"]][l["atracao"]].append(l)
        for _ in range(REPETICOES):
            amostra = []
            for atrs in por_atr.values():
                nomes = list(atrs)
                for a in rng.choices(nomes, k=len(nomes)):
                    amostra += atrs[a]
            replicas.append(por_parque(amostra))
    return replicas


def serie(replicas, parque, campo):
    return [r[parque][campo] if parque in r else NAN for r in replicas]


def chance(replicas, a, b, campo, menor=True):
    pares = [(r[a][campo], r[b][campo]) for r in replicas if a in r and b in r
             and r[a][campo] == r[a][campo] and r[b][campo] == r[b][campo]]
    if not pares:
        return NAN
    return sum((x < y) if menor else (x > y) for x, y in pares) / len(pares)


def permutacao_atracoes(linhas, a, b):
    """Uma mediana por atração (só atrações com parada). P(diferença das medianas das medianas >=
    observada) sob permutação dos rótulos de parque. Unilateral: a < b."""
    meds = defaultdict(list)
    for l in linhas:
        meds[(l["parque"], l["atracao"])] += l["duracoes"]
    va = [statistics.median(v) for (p, _), v in meds.items() if p == a and v]
    vb = [statistics.median(v) for (p, _), v in meds.items() if p == b and v]
    if len(va) < 2 or len(vb) < 2:
        return va, vb, NAN
    obs = statistics.median(vb) - statistics.median(va)
    todos = va + vb
    rng = random.Random(SEMENTE)
    extremos = 0
    for _ in range(PERMUTACOES):
        rng.shuffle(todos)
        if statistics.median(todos[len(va):]) - statistics.median(todos[:len(va)]) >= obs:
            extremos += 1
    return va, vb, extremos / PERMUTACOES


def checar_dados(atracoes_dia, paradas):
    ad = [l for l in atracoes_dia if no_periodo(l)]
    rep = [k for k, n in Counter(chave(l) for l in ad).items() if n > 1]
    if rep:
        print(f"  AVISO: {len(rep)} atração-dias repetidas (mesmo parque, data e nome). As paradas delas "
              f"seriam contadas em dobro. Ex.: {rep[:3]}")
    chaves_ad = {chave(l) for l in ad}
    orfas = [p for p in paradas if no_periodo(p) and chave(p) not in chaves_ad and p.get("conta_10min") == "sim"]
    if orfas:
        print(f"  AVISO: {len(orfas)} paradas de 10 min ou mais sem linha no atracoes_dia (ficam fora).")
    estranhas = [p for p in paradas if float(p["minutos_parada"]) > float(p["duracao_min"]) + 0.05]
    if estranhas:
        print(f"  AVISO: {len(estranhas)} paradas com minutos_parada maior que duracao_min.")
    if "conta_10min" in (paradas[0] if paradas else {}):
        fronteira = Counter((p["parque"], "grande" if p.get("porte") == "grande" else "outra")
                            for p in paradas if no_periodo(p) and p["conta_10min"] == "não"
                            and float(p["duracao_min"]) >= 10 and p["marca_clima"] != "raio")
        print(f"  Paradas entre 9,95 e 10 min (entrariam pelo critério arredondado, mas não contam aqui): "
              f"{dict(fronteira) or 'nenhuma'}")
    if ad and "porte" in ad[0]:
        f2 = sorted({(l["parque"], l["atracao"]) for l in ad if l["porte"] != "grande"
                     and l["fila_media_min"] and float(l["fila_media_min"]) >= CORTE_GRANDE})
        print(f"  Atrações com fila média arredondada >= 20 mas porte != grande: {f2 or 'nenhuma'}")


def main():
    atracoes_dia, paradas = ler("atracoes_dia.csv"), ler("paradas_clima.csv")
    dias = sorted({l["data"] for l in atracoes_dia if no_periodo(l)})
    if not dias:
        sys.exit(f"ERRO: nenhum dia entre {DATA_INICIO} e {DATA_FIM} no atracoes_dia.csv.")
    print(f"Base: {dias[0]} a {dias[-1]} ({len(dias)} dias com dado) | critério: {CRITERIO}")
    fora = sorted({l["data"] for l in atracoes_dia if not no_periodo(l)})
    if fora:
        print(f"  ATENÇÃO: {len(fora)} dias fora do período ({fora[0]} a {fora[-1]}). As linhas são ignoradas, "
              "mas o PORTE (fila média) foi calculado pelo limpar_paradas.py com eles: a régua não está congelada.")
    checar_dados(atracoes_dia, paradas)

    for regua in ("grandes", "todas"):
        linhas = montar(atracoes_dia, paradas, regua)
        m = por_parque(linhas)
        ordem = sorted(m, key=lambda p: -m[p]["freq"])
        print("=" * 110)
        print(f"RÉGUA: {regua.upper()}")
        print(f"{'Parque':22s} {'atr':>4s} {'paradas':>8s} {'por 10h':>8s} {'>60/10h':>8s} {'mediana':>8s} "
              f"{'med.DOWN':>9s} {'média':>6s} {'disp.':>7s} {'h paradas':>10s} {'dia int.':>9s}")
        for p in ordem:
            x = m[p]
            print(f"{NOMES.get(p, p):22s} {x['atracoes']:4d} {x['n']:8d} {x['freq']:8.3f} {x['longas_10h']:8.3f} "
                  f"{x['mediana']:8.1f} {x['mediana_so_down']:9.1f} {x['media']:6.1f} {x['disp']:7.1%} "
                  f"{x['horas_paradas']:10.1f} {x['dia_inteiro']:9d}")

        print("\n  Conferência com a estreia (valor arredondado a 2 casas):")
        alt = por_parque(montar(atracoes_dia, paradas, regua, criterio="robustez"))
        for p in PUBLICADO[regua]:
            if p not in m:
                print(f"    {NOMES[p]:22s} sem dados")
                continue
            a, b = round(m[p]["freq"], 2), round(alt[p]["freq"], 2)
            marca = "" if a == PUBLICADO[regua][p] else "  <- NÃO BATE"
            print(f"    {NOMES[p]:22s} publicado {PUBLICADO[regua][p]:.2f} | critério estreia {m[p]['freq']:.4f} "
                  f"| critério robustez {alt[p]['freq']:.4f}{marca}")

        sem = por_parque(montar(atracoes_dia, paradas, regua, sem_dia_inteiro=True))
        m15 = por_parque(montar(atracoes_dia, paradas, regua, minimo=15))
        print("\n  Sensibilidade (mediana / média / horas paradas):")
        for p in ordem:
            s = sem.get(p)
            txt_sem = f"{s['mediana']:5.1f} / {s['media']:5.1f} / {s['horas_paradas']:6.1f} h" if s else "-"
            print(f"    {NOMES.get(p, p):22s} base {m[p]['mediana']:5.1f} / {m[p]['media']:5.1f} / "
                  f"{m[p]['horas_paradas']:6.1f} h | sem dias inteiros {txt_sem} | corte 15: "
                  f"{m15[p]['mediana']:5.1f} | cortadas abertura/fechamento {m[p]['abertura']}/{m[p]['fechamento']}")
        for l in linhas:
            if l["dia_inteiro"]:
                print(f"    dia inteiro: {l['parque']} {l['data']} {l['atracao'][:40]} "
                      f"({l['parada'] / 60:.1f} h paradas, {len(l['duracoes'])} paradas contadas)")

        res = {modo: reamostrar(linhas, modo) for modo in ("dia", "atracao")}
        print(f"\n  Reamostragem ({REPETICOES}x): intervalos de 90% (estabilidade do procedimento, não probabilidade)")
        for p in ordem:
            partes = [f"{intervalo(serie(res[md], p, 'mediana'))[0]:5.1f}-{intervalo(serie(res[md], p, 'mediana'))[1]:5.1f}"
                      for md in ("dia", "atracao")]
            partes += [f"{intervalo(serie(res[md], p, 'freq'))[0]:.2f}-{intervalo(serie(res[md], p, 'freq'))[1]:.2f}"
                       for md in ("dia", "atracao")]
            print(f"    {NOMES.get(p, p):22s} mediana dia {partes[0]} | atr {partes[1]} | freq dia {partes[2]} | atr {partes[3]}")
        e, i = "epic-universe", "islands-of-adventure"
        if e in m and i in m:
            for md in ("dia", "atracao"):
                print(f"    [{md}] mediana Epic < Islands: {chance(res[md], e, i, 'mediana'):.1%} | "
                      f"freq Epic > Islands: {chance(res[md], e, i, 'freq', menor=False):.1%}")
            va, vb, pv = permutacao_atracoes(linhas, e, i)
            print(f"    Nível da atração (1 mediana por atração): Epic {[round(v) for v in sorted(va)]} | "
                  f"Islands {[round(v) for v in sorted(vb)]}")
            print(f"    mediana das medianas {statistics.median(va) if va else NAN:.1f} x "
                  f"{statistics.median(vb) if vb else NAN:.1f} | permutação unilateral p = {pv:.3f}")

        # por atração, com e sem os dias inteiros parados (para o exemplo do carrossel)
        print("\n  Por atração (ordenado por horas paradas; 'sem dia int.' tira as atração-dias sem nenhum minuto funcionando):")
        com = defaultdict(list)
        for l in linhas:
            com[(l["parque"], l["atracao"])].append(l)
        for p in ordem:
            print(f"    {NOMES.get(p, p)}")
            atrs = sorted(com.items(), key=lambda kv: -medidas(kv[1])["horas_paradas"])
            for (pp, a), g in [kv for kv in atrs if kv[0][0] == p][:8 if regua == "grandes" else 5]:
                x, s = medidas(g), medidas([l for l in g if not l["dia_inteiro"]])
                med = f"{x['mediana']:4.0f}" if x["n"] else "   -"
                med_s = f"{s['mediana']:4.0f}" if s["n"] else "   -"
                print(f"      {a[:40]:40s} {x['n']:3d} paradas | {x['freq']:5.2f} por 10h | mediana {med} min | "
                      f"{x['horas_paradas']:5.1f} h paradas | sem dia int.: {s['n']:3d} paradas, mediana {med_s} min, "
                      f"{s['horas_paradas']:5.1f} h")


if __name__ == "__main__":
    main()
