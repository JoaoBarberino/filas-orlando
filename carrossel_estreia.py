"""
Projeto "Filas em Orlando": carrossel do post de estreia (quinta, 12/11/2026).

Identidade da série de quinta: "folha de cálculo" (papel de engenharia
quadriculado, grafite, caneta azul, carimbo de desenho técnico no rodapé).

Comparação PARQUE CONTRA PARQUE (os 7 parques da Disney e da Universal em Orlando):
    1. capa:       "Qual parque de Orlando tem mais paradas por atração? Depende da régua."
                   (a posição do EPCOT nas duas réguas: 6º ou 3º)
    2. o que muda: o ranking dos 7 parques nas duas réguas, ligados por linhas
    3. por que:    a mistura de atrações do EPCOT

Medida (revisada em 04/11): paradas de 10 min ou mais por 10 horas de operação da
atração (operação = minutos funcionando + parada, no horário normal), SEM as paradas
por raio. 1º lugar = mais paradas. Teatros e cinemas ficam fora (limpar_paradas.py).
Por que o EPCOT: é o parque cuja posição muda e que passou nos testes do robustez.py
(3º em todos os cortes de porte, nas duas metades do mês e em 88% das reamostragens
por dia). Quem é o 1º (Islands ou Epic) NÃO passou nos testes: por isso não vai em título.

Como rodar (mesma pasta; depois do limpar_paradas.py e do checar_clima.py):
    python carrossel_estreia.py

Precisa da pasta "fontes_quinta" com (todas gratuitas, licença OFL):
    BricolageGrotesque-Bold.ttf, WorkSans-Regular.ttf, Jura-Medium.ttf
Gera: carrossel_1_capa.png, carrossel_2_o_que_muda.png, carrossel_3_por_que.png
      (1080 x 1350 cada) e carrossel_estreia.pdf (as 3 páginas, para o LinkedIn).
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, Rectangle

# ---------------------------------------------------------------------------
# Textos e cores (mude aqui)
# ---------------------------------------------------------------------------
PARQUE_FOCO = "epcot"      # o parque contado na capa e na imagem 3

TITULO_1 = "Qual parque de Orlando\ntem mais paradas por\natração? Depende da régua."
TITULO_2 = "Comparando só atrações\ngrandes, o ranking muda: o\n{parque} sobe do {de}º para o {para}º lugar."
TITULO_3 = "{quanto} das atrações do {parque}\nsão galerias e exposições. Elas\nquase nunca param e puxam\na média para baixo."

PERIODO = "de 5/out a 3/nov de 2026"
SUBTITULO_1 = ("Posição do {parque} entre os 7 parques da Disney\n"
               "e da Universal em Orlando, " + PERIODO + ".")
SUBTITULO_2 = ("1º = mais paradas de 10 min ou mais por 10 h\n"
               "de operação, " + PERIODO + ".\n"
               "Grandes: fila anunciada média de 20 min ou mais.")
SUBTITULO_3 = ("{parque}: paradas de 10 min ou mais por 10 horas\n"
               "de operação, por tipo de atração, " + PERIODO + ".")
NOTA_3 = ("Teatros e cinemas ficam fora da conta em todos os parques:\n"
          "a Universal registra os dela como show, não como atração.")

PROJETO = "Filas em Orlando"
DATA = "05/11/2026"
AUTOR = "João Vitor Barberino"
FONTES_DADOS = "Powered by ThemeParks.wiki (dados não oficiais)"

PAPEL, GRADE, GRADE_FORTE = "#E9F0E0", "#D4E1C6", "#C2D4B0"
GRAFITE, TINTA, SECUNDARIA = "#30362F", "#2448A6", "#5E675B"

TIRAR_RAIO = True          # regra padrão do projeto (seção 4.9 do .md)

NOMES = {
    "magic-kingdom": "Magic Kingdom",
    "epcot": "EPCOT",
    "hollywood-studios": "Hollywood Studios",
    "animal-kingdom": "Animal Kingdom",
    "universal-studios-florida": "Universal Studios",
    "islands-of-adventure": "Islands of Adventure",
    "epic-universe": "Epic Universe",
}
PORTES = {"todas": ("sem_fila", "menor", "grande"), "grandes": ("grande",)}
TIPOS = [("sem_fila", "sem fila"), ("menor", "menores"), ("grande", "grandes")]

PASTA = Path(__file__).parent
PASTA_TRATADOS = PASTA / "dados" / "tratados"
PASTA_FONTES = PASTA / "fontes_quinta"


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
def ler_csv(nome):
    caminho = PASTA_TRATADOS / nome
    if not caminho.exists():
        sys.exit(f"ERRO: falta {caminho}. Rode antes o limpar_paradas.py e o checar_clima.py.")
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def calcular():
    atracoes_dia = ler_csv("atracoes_dia.csv")
    paradas = ler_csv("paradas_clima.csv")
    chaves_dia = {(l["parque"], l["data"], l["atracao"]) for l in atracoes_dia}
    chaves_paradas = {(p["parque"], p["data"], p["atracao"]) for p in paradas if p["conta_10min"] == "sim"}
    if not chaves_paradas <= chaves_dia:
        sys.exit("ERRO: paradas_clima.csv e atracoes_dia.csv são de rodadas diferentes. "
                 "Rode de novo o limpar_paradas.py e depois o checar_clima.py.")

    contam = defaultdict(int)
    for p in paradas:
        if p["conta_10min"] == "sim" and not (TIRAR_RAIO and p["marca_clima"] == "raio"):
            contam[(p["parque"], p["data"], p["atracao"])] += 1

    soma, horas = defaultdict(int), defaultdict(float)   # por (parque, porte)
    atracoes = defaultdict(set)
    for l in atracoes_dia:
        k = (l["parque"], l["porte"])
        soma[k] += contam[(l["parque"], l["data"], l["atracao"])]
        horas[k] += (float(l["min_funcionando"]) + float(l["min_parada"])) / 60
        atracoes[k].add(l["id_atracao"])

    def taxa(parque, portes):
        h = sum(horas[(parque, p)] for p in portes)
        return sum(soma[(parque, p)] for p in portes) / h * 10 if h else None

    tabela = {}
    for parque in NOMES:
        tabela[parque] = {
            "todas": taxa(parque, PORTES["todas"]),
            "grandes": taxa(parque, PORTES["grandes"]),
            "por_tipo": {p: taxa(parque, (p,)) for p, _ in TIPOS},
            "qtd": {p: len(atracoes[(parque, p)]) for p, _ in TIPOS},
        }
        if tabela[parque]["todas"] is None or tabela[parque]["grandes"] is None:
            sys.exit(f"ERRO: sem dados suficientes para {NOMES[parque]}.")
    for regua in PORTES:
        ordem = sorted(NOMES, key=lambda q: -tabela[q][regua])
        for pos, parque in enumerate(ordem, start=1):
            tabela[parque][f"pos_{regua}"] = pos

    print("Paradas de 10 min ou mais por 10 horas de operação (sem raio); 1º = mais paradas")
    print(f"{'Parque':22s} {'todas':>6s} {'pos':>4s} {'grandes':>8s} {'pos':>4s}   sem fila / menores / grandes")
    for parque in sorted(NOMES, key=lambda q: tabela[q]["pos_todas"]):
        t = tabela[parque]
        print(f"{NOMES[parque]:22s} {t['todas']:6.3f} {t['pos_todas']:3d}º {t['grandes']:8.3f} {t['pos_grandes']:3d}º"
              f"   {t['qtd']['sem_fila']:3d} / {t['qtd']['menor']:3d} / {t['qtd']['grande']:3d}")
    f = tabela[PARQUE_FOCO]
    print(f"\n{NOMES[PARQUE_FOCO]}: {f['pos_todas']}º com todas -> {f['pos_grandes']}º só com as grandes")
    sobe = max(NOMES, key=lambda q: tabela[q]["pos_todas"] - tabela[q]["pos_grandes"])
    if sobe != PARQUE_FOCO:
        print(f"AVISO: o parque que mais sobe agora é {NOMES[sobe]}, não {NOMES[PARQUE_FOCO]}. "
              "Os títulos falam do EPCOT: rever antes de usar.")
    if f["pos_todas"] <= f["pos_grandes"]:
        print(f"AVISO: o {NOMES[PARQUE_FOCO]} não sobe no ranking. A história do carrossel não vale mais.")
    for regua in PORTES:
        valores = sorted((round(tabela[q][regua], 2), NOMES[q]) for q in NOMES)
        for (v1, n1), (v2, n2) in zip(valores, valores[1:]):
            if v1 == v2:
                print(f"AVISO: empate na régua '{regua}' entre {n1} e {n2} ({v1}).")
    return tabela


# ---------------------------------------------------------------------------
# Folha (fundo, título, carimbo)
# ---------------------------------------------------------------------------
def carregar_fontes():
    nomes = {"titulo": "BricolageGrotesque-Bold.ttf", "texto": "WorkSans-Regular.ttf", "mao": "Jura-Medium.ttf"}
    faltam = [n for n in nomes.values() if not (PASTA_FONTES / n).exists()]
    if faltam:
        sys.exit(f"ERRO: faltam fontes na pasta {PASTA_FONTES}: {', '.join(faltam)}")
    return {k: font_manager.FontProperties(fname=str(PASTA_FONTES / n)) for k, n in nomes.items()}


def virgula(x, casas=2):
    return f"{x:.{casas}f}".replace(".", ",")


def folha(f, titulo, subtitulo, n_folha, y_subtitulo=330, tamanho_titulo=40):
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=PAPEL)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1080)
    ax.set_ylim(1350, 0)
    ax.axis("off")
    for x in range(0, 1081, 18):
        forte = x % 90 == 0
        ax.plot([x, x], [0, 1350], color=GRADE_FORTE if forte else GRADE, lw=0.8 if forte else 0.5, zorder=0)
    for y in range(0, 1351, 18):
        forte = y % 90 == 0
        ax.plot([0, 1080], [y, y], color=GRADE_FORTE if forte else GRADE, lw=0.8 if forte else 0.5, zorder=0)

    ax.text(72, 96, titulo, fontproperties=f["titulo"], fontsize=tamanho_titulo, color=GRAFITE,
            va="top", linespacing=1.1)
    ax.text(72, y_subtitulo, subtitulo, fontproperties=f["texto"], fontsize=19, color=SECUNDARIA,
            va="top", linespacing=1.4)

    # carimbo (legenda de desenho técnico)
    cx, cy, cw, ch = 72, 1196, 936, 120
    ax.add_patch(Rectangle((cx, cy), cw, ch, fc=PAPEL, ec=GRAFITE, lw=2, zorder=6))
    ax.plot([cx, cx + cw], [cy + 60, cy + 60], color=GRAFITE, lw=1.2, zorder=7)
    for xv in (cx + 330, cx + 700):
        ax.plot([xv, xv], [cy, cy + 60], color=GRAFITE, lw=1.2, zorder=7)
    campos = [(cx + 14, cy, "projeto", PROJETO), (cx + 344, cy, "folha", n_folha), (cx + 714, cy, "data", DATA),
              (cx + 14, cy + 60, "autor", AUTOR)]
    for x, y, rotulo, valor in campos:
        ax.text(x, y + 16, rotulo, fontproperties=f["mao"], fontsize=12, color=SECUNDARIA, va="center", zorder=8)
        ax.text(x, y + 40, valor, fontproperties=f["titulo"], fontsize=17, color=GRAFITE, va="center", zorder=8)
    ax.text(cx + 344, cy + 76, "fontes", fontproperties=f["mao"], fontsize=12, color=SECUNDARIA,
            va="center", zorder=8)
    ax.text(cx + 344, cy + 100, FONTES_DADOS, fontproperties=f["texto"], fontsize=13.5, color=GRAFITE,
            va="center", zorder=8)
    return fig, ax


# ---------------------------------------------------------------------------
# Imagem 1: capa (a posição do EPCOT nas duas réguas)
# ---------------------------------------------------------------------------
def capa(f, tab):
    t = tab[PARQUE_FOCO]
    nome = NOMES[PARQUE_FOCO]
    fig, ax = folha(f, TITULO_1, SUBTITULO_1.format(parque=nome), "1 de 3", y_subtitulo=372, tamanho_titulo=46)
    ax.text(110, 560, nome, fontproperties=f["titulo"], fontsize=34, color=GRAFITE, va="top")
    ax.text(110, 760, f"{t['pos_todas']}º", fontproperties=f["titulo"], fontsize=190, color=GRAFITE,
            ha="left", va="center")
    ax.text(540, 760, "ou", fontproperties=f["mao"], fontsize=32, color=SECUNDARIA, ha="center", va="center")
    ax.text(640, 760, f"{t['pos_grandes']}º", fontproperties=f["titulo"], fontsize=190, color=TINTA,
            ha="left", va="center")
    ax.text(110, 905, "contando todas\nas atrações", fontproperties=f["mao"], fontsize=21,
            color=GRAFITE, va="top", linespacing=1.2)
    ax.text(640, 905, "contando só as\natrações grandes", fontproperties=f["mao"], fontsize=21,
            color=TINTA, va="top", linespacing=1.2)
    ax.text(110, 1060, "1º = o parque com mais paradas", fontproperties=f["mao"], fontsize=18,
            color=SECUNDARIA, va="top")
    return fig


# ---------------------------------------------------------------------------
# Imagem 2: o ranking nas duas réguas
# ---------------------------------------------------------------------------
def ranking(f, tab):
    foco = tab[PARQUE_FOCO]
    titulo = TITULO_2.format(parque=NOMES[PARQUE_FOCO], de=foco["pos_todas"], para=foco["pos_grandes"])
    fig, ax = folha(f, titulo, SUBTITULO_2, "2 de 3", tamanho_titulo=38)
    xa, xb, y0, passo = 400, 680, 605, 86
    Y = lambda pos: y0 + (pos - 1) * passo
    for x, rotulo in ((xa, "todas as\natrações"), (xb, "só as\ngrandes")):
        ax.text(x, 552, rotulo, fontproperties=f["texto"], fontsize=17, color=GRAFITE,
                ha="center", va="bottom", linespacing=1.15)
    for pos in range(1, 8):
        ax.text(80, Y(pos), f"{pos}º", fontproperties=f["mao"], fontsize=17, color=SECUNDARIA,
                ha="left", va="center")
    for parque in NOMES:
        destaque = parque == PARQUE_FOCO
        cor = TINTA if destaque else GRAFITE
        ya, yb = Y(tab[parque]["pos_todas"]), Y(tab[parque]["pos_grandes"])
        ax.plot([xa, xb], [ya, yb], color=cor, lw=3.4 if destaque else 1.2, alpha=1 if destaque else 0.35,
                zorder=4 if destaque else 3, solid_capstyle="round")
        for x, y in ((xa, ya), (xb, yb)):
            ax.add_patch(Circle((x, y), 8 if destaque else 6, fc=cor, ec=cor, zorder=5,
                                alpha=1 if destaque else 0.7))
        fonte = f["titulo"] if destaque else f["texto"]
        for x, y, ha, regua in ((xa - 20, ya, "right", "todas"), (xb + 20, yb, "left", "grandes")):
            ax.text(x, y - 2, NOMES[parque], fontproperties=fonte, fontsize=18, color=cor, ha=ha, va="center")
            ax.text(x, y + 25, virgula(tab[parque][regua]), fontproperties=f["mao"], fontsize=16,
                    color=cor, ha=ha, va="center")
    return fig


# ---------------------------------------------------------------------------
# Imagem 3: por que muda (a mistura de atrações do EPCOT)
# ---------------------------------------------------------------------------
def por_que(f, tab):
    t = tab[PARQUE_FOCO]
    total = sum(t["qtd"].values())
    fracao = t["qtd"]["sem_fila"] / total
    quanto = "Metade" if 0.45 <= fracao <= 0.58 else f"{t['qtd']['sem_fila']} das {total}"
    if quanto != "Metade":
        print(f"AVISO: {t['qtd']['sem_fila']} de {total} atrações sem fila ({fracao:.0%}); confira o título 3.")
    titulo = TITULO_3.format(quanto=quanto, parque=NOMES[PARQUE_FOCO])
    fig, ax = folha(f, titulo, SUBTITULO_3.format(parque=NOMES[PARQUE_FOCO]), "3 de 3",
                    y_subtitulo=405, tamanho_titulo=37)

    base, w = 1015, 180
    vmax = max(v for v in t["por_tipo"].values() if v is not None)
    escala = 360 / max(vmax, 0.1)
    xs = [140, 450, 760]
    for (porte, rotulo), x in zip(TIPOS, xs):
        valor, qtd = t["por_tipo"][porte], t["qtd"][porte]
        grande = porte == "grande"
        cor = TINTA if porte == "sem_fila" else GRAFITE
        if qtd == 0:
            ax.text(x + w / 2, base - 14, "nenhuma", fontproperties=f["mao"], fontsize=17, color=SECUNDARIA,
                    ha="center", va="bottom")
        else:
            h = max(valor * escala, 4)
            ax.add_patch(Rectangle((x, base - h), w, h, fc=GRAFITE if grande else PAPEL, ec=cor, lw=2.2,
                                   hatch=None if grande else ("////" if porte == "menor" else "\\\\\\\\"), zorder=3))
            ax.text(x + w / 2, base - h - 10, virgula(valor), fontproperties=f["titulo"], fontsize=32,
                    color=cor, ha="center", va="bottom")
        ax.text(x + w / 2, base + 14, f"{qtd} atrações\n{rotulo}", fontproperties=f["texto"], fontsize=17,
                color=cor, ha="center", va="top", linespacing=1.15)
    ax.plot([100, 990], [base, base], color=GRAFITE, lw=1.4)

    y = base - t["todas"] * escala
    ax.plot([100, 990], [y, y], color=TINTA, lw=1.6, ls=(0, (2, 3)), zorder=2)
    ax.text(102, y - 8, f"média com todas: {virgula(t['todas'])}", fontproperties=f["mao"], fontsize=17,
            color=TINTA, ha="left", va="bottom")
    ax.text(72, 1182, NOTA_3, fontproperties=f["mao"], fontsize=15, color=TINTA, va="bottom", linespacing=1.25)
    return fig


# ---------------------------------------------------------------------------
def main():
    tab = calcular()
    f = carregar_fontes()
    plt.rcParams["hatch.linewidth"] = 1.0
    plt.rcParams["pdf.fonttype"] = 42
    figuras = [("carrossel_1_capa.png", capa(f, tab)),
               ("carrossel_2_o_que_muda.png", ranking(f, tab)),
               ("carrossel_3_por_que.png", por_que(f, tab))]
    with PdfPages(PASTA / "carrossel_estreia.pdf") as pdf:
        for nome, fig in figuras:
            fig.savefig(PASTA / nome, dpi=100, facecolor=PAPEL)
            pdf.savefig(fig, facecolor=PAPEL)
            plt.close(fig)
    print(f"\nGravados em {PASTA}: {', '.join(n for n, _ in figuras)} e carrossel_estreia.pdf")


if __name__ == "__main__":
    main()
