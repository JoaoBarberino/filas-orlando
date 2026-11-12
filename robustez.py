"""
Projeto "Filas em Orlando": testes de robustez do ranking de paradas (pilar 2).

Pergunta: o ranking dos parques se sustenta ou muda com pouca coisa?
Medida: paradas de 10 min ou mais por 10 horas de operação da atração
(operação = minutos funcionando + parada, no horário normal), sem as paradas por raio.
Réguas: "todas" (todas as atrações) e "grandes" (fila anunciada média de 20 min ou mais).

Testes:
  1. Reamostragem por dia (2.000 vezes): chance de cada parque em cada posição.
  2. Reamostragem por atração (2.000 vezes): idem, sorteando as atrações de cada parque.
  3. Tirar uma atração: a pior mudança de posição de cada parque, e qual atração causa.
  4. Outros cortes: "grande" a partir de 15, 20, 25 e 30 min; parada mínima de 5, 10 e 15 min.
  5. Primeira metade x segunda metade do período.

Correção de 11/11/2026 (auditoria do post 2): o corte de 10 min e a régua "grandes" passaram a
usar as colunas conta_10min e porte. Antes o script lia duracao_min e fila_media_min, que são
arredondadas, e contava algumas paradas de 9,95 a 9,99 min como 10 min. Por isso dava 0,78 no
Epic Universe, contra os 0,77 do carrossel da estreia, que sempre esteve certo.

Como rodar (mesma pasta; depois do limpar_paradas.py e do checar_clima.py):
    python robustez.py
Leva alguns segundos. Só lê os CSVs de dados/tratados; não grava nada.
"""

import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

PASTA = Path(__file__).parent / "dados" / "tratados"
REPETICOES = 2000
SEMENTE = 12   # para o resultado sair igual toda vez
NOMES = {
    "magic-kingdom": "Magic Kingdom", "epcot": "EPCOT", "hollywood-studios": "Hollywood Studios",
    "animal-kingdom": "Animal Kingdom", "universal-studios-florida": "Universal Studios",
    "islands-of-adventure": "Islands of Adventure", "epic-universe": "Epic Universe",
}


def ler(nome):
    caminho = PASTA / nome
    if not caminho.exists():
        sys.exit(f"ERRO: falta {caminho}. Rode antes o limpar_paradas.py e o checar_clima.py.")
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def montar(atracoes_dia, paradas, corte_grande=20, minimo=10):
    """Lista de atração-dias: (parque, data, atracao, horas de operação, paradas, é grande, tem fila).

    No corte padrão (parada de 10 min, fila de 20 min) valem as colunas que o limpar_paradas.py
    já calculou com o valor exato: conta_10min e porte. As colunas duracao_min e fila_media_min
    foram gravadas arredondadas a 0,1, então uma parada de 9,97 min vira "10.0" e entraria por
    engano. Nos outros cortes não existe coluna pronta, e aí o valor arredondado é o que há.
    """
    if minimo == 10:
        conta = lambda p: p["conta_10min"] == "sim"
    else:
        conta = lambda p: float(p["duracao_min"]) >= minimo
    n = Counter((p["parque"], p["data"], p["atracao"]) for p in paradas
                if conta(p) and p["marca_clima"] != "raio")
    linhas = []
    for l in atracoes_dia:
        horas = (float(l["min_funcionando"]) + float(l["min_parada"])) / 60
        fila = float(l["fila_media_min"]) if l["fila_media_min"] else 0.0
        grande = l["porte"] == "grande" if corte_grande == 20 else fila >= corte_grande
        if horas <= 0:
            continue
        linhas.append((l["parque"], l["data"], l["atracao"], horas, n[(l["parque"], l["data"], l["atracao"])],
                       grande, fila >= 1))
    return linhas


def taxas(linhas, regua):
    soma, horas = defaultdict(float), defaultdict(float)
    for parque, _, _, h, k, grande, _ in linhas:
        if regua == "grandes" and not grande:
            continue
        soma[parque] += k
        horas[parque] += h
    return {p: soma[p] / horas[p] * 10 for p in horas if horas[p] > 0}


def ranking(t):
    return {p: i for i, p in enumerate(sorted(t, key=lambda p: -t[p]), start=1)}


def tabela_posicoes(contagens, titulo):
    print(f"\n{titulo}")
    print(f"{'Parque':22s} " + " ".join(f"{i}º".rjust(5) for i in range(1, 8)))
    for p in NOMES:
        c = contagens[p]
        total = sum(c.values()) or 1
        print(f"{NOMES[p]:22s} " + " ".join(f"{c[i] / total:5.0%}" if c[i] else "    ." for i in range(1, 8)))


def main():
    random.seed(SEMENTE)
    atracoes_dia, paradas = ler("atracoes_dia.csv"), ler("paradas_clima.csv")
    base = montar(atracoes_dia, paradas)
    dias = sorted({l[1] for l in base})

    for regua in ("todas", "grandes"):
        t = taxas(base, regua)
        r = ranking(t)
        print("=" * 78)
        print(f"RÉGUA: {regua.upper()} (paradas por 10 h de operação, sem raio)")
        for p in sorted(t, key=lambda p: r[p]):
            print(f"  {r[p]}º {NOMES[p]:22s} {t[p]:.2f}")

        # 1. reamostragem por dia
        por_dia = defaultdict(list)
        for l in base:
            por_dia[l[1]].append(l)
        cont = defaultdict(Counter)
        for _ in range(REPETICOES):
            amostra = [l for d in random.choices(dias, k=len(dias)) for l in por_dia[d]]
            for p, pos in ranking(taxas(amostra, regua)).items():
                cont[p][pos] += 1
        tabela_posicoes(cont, "1. Reamostragem por dia: chance de cada posição")

        # 2. reamostragem por atração (dentro de cada parque)
        por_atr = defaultdict(lambda: defaultdict(list))
        for l in base:
            if regua == "todas" or l[5]:
                por_atr[l[0]][l[2]].append(l)
        cont = defaultdict(Counter)
        for _ in range(REPETICOES):
            amostra = []
            for p, atrs in por_atr.items():
                nomes = list(atrs)
                for a in random.choices(nomes, k=len(nomes)):
                    amostra += atrs[a]
            for p, pos in ranking(taxas(amostra, regua)).items():
                cont[p][pos] += 1
        tabela_posicoes(cont, "2. Reamostragem por atração: chance de cada posição")

        # 3. tirar uma atração de cada vez
        print("\n3. Tirando uma atração de cada vez: posição mais alta e mais baixa de cada parque")
        for p in NOMES:
            nomes = {l[2] for l in base if l[0] == p and (regua == "todas" or l[5])}
            posicoes = []
            for a in nomes:
                pos = ranking(taxas([l for l in base if not (l[0] == p and l[2] == a)], regua))[p]
                posicoes.append((pos, a))
            alto, baixo = min(posicoes), max(posicoes)
            extra = f" (sem {baixo[1]})" if baixo[0] != r[p] else ""
            extra += f" (sem {alto[1]})" if alto[0] != r[p] else ""
            print(f"  {NOMES[p]:22s} hoje {r[p]}º | de {alto[0]}º a {baixo[0]}º{extra}")

        # 4. outros cortes
        print("\n4. Outros cortes (posição de cada parque)")
        cortes = [(f"grande>={c}", c, 10) for c in (15, 20, 25, 30)] if regua == "grandes" else []
        cortes += [(f"parada>={m}min", 20, m) for m in (5, 10, 15)]
        print(f"{'Parque':22s} " + " ".join(f"{c[0]:>13s}" for c in cortes))
        for p in NOMES:
            partes = []
            for _, c, m in cortes:
                tt = taxas(montar(atracoes_dia, paradas, c, m), regua)
                partes.append(f"{ranking(tt)[p]}º ({tt[p]:.2f})".rjust(13))
            print(f"{NOMES[p]:22s} " + " ".join(partes))

        # 5. metades do período
        meio = dias[len(dias) // 2]
        print(f"\n5. Primeira metade (até {dias[len(dias) // 2 - 1]}) x segunda metade (a partir de {meio})")
        t1 = taxas([l for l in base if l[1] < meio], regua)
        t2 = taxas([l for l in base if l[1] >= meio], regua)
        r1, r2 = ranking(t1), ranking(t2)
        for p in sorted(NOMES, key=lambda p: r[p]):
            print(f"  {NOMES[p]:22s} {r1[p]}º ({t1[p]:.2f})  x  {r2[p]}º ({t2[p]:.2f})")
    print("=" * 78)


if __name__ == "__main__":
    main()
