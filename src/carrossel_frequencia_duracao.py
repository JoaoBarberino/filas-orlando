"""
Projeto "Filas em Orlando": carrossel do post 2 (quinta, 12/11/2026).
"Parar muitas vezes ou ficar parado muito tempo" (pilar 2, frequência x duração).

Identidade nova da série de quinta (escolhida em 11/11/2026): "ingresso", paleta
"noite no parque": fundo azul-noite, ingressos em ciano e rosa, amarelo para avisos.

    1. capa:      dois ingressos, Epic Universe (19 min) x Islands of Adventure (32 min).
    2. 7 parques: um ponto por parque, frequência x duração típica.
    3. atrações:  uma barra por atração grande do Epic e do Islands (a diferença não vem
                  de uma atração só).

Regras (as mesmas da estreia, conferidas pela auditoria de 11/11/2026):
  - paradas de 10 min ou mais pela coluna conta_10min (NÃO por duracao_min >= 10,
    que é arredondada e conta paradas de 9,95 min);
  - atrações grandes pela coluna porte;
  - sem as paradas por raio; só o horário normal; sem teatros e cinemas;
  - base congelada: DATA_INICIO a DATA_FIM (a mesma da estreia);
  - "duração típica" = mediana das paradas de 10 min ou mais (duracao_min).

Como rodar (a partir da raiz do projeto; depois do limpar_paradas.py e do checar_clima.py;
NÃO rode o limpar_paradas.py de novo antes):
    python src/carrossel_frequencia_duracao.py

Precisa, na pasta "fontes_quinta" (a mesma das fontes da estreia), de (gratuitas, licença OFL):
    Rubik-ExtraBold.ttf, Rubik-Medium.ttf, DMSans-Regular.ttf, DMSans-Bold.ttf
Grava em posts/02-frequencia-duracao: post2_1_capa.png, post2_2_parques.png,
post2_3_atracoes.png (1080 x 1350) e carrossel_frequencia_duracao.pdf.
NÃO mexe nos arquivos da estreia.
"""

import csv
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle, Wedge

# ---------------------------------------------------------------------------
# Textos (mude aqui)
# ---------------------------------------------------------------------------
DATA_INICIO, DATA_FIM = "2026-10-05", "2026-11-03"
A, B = "epic-universe", "islands-of-adventure"      # a dupla do post (A em ciano, B em rosa)

ETIQUETA = "FREQUÊNCIA × DURAÇÃO"
SUB = "Atrações grandes · paradas de 10 min ou mais · 5/out a 3/nov de 2026"

TITULO_1 = "Islands of Adventure e Epic\nUniverse param com frequência\nparecida. O que muda é quanto\ndura cada parada."
TITULO_2 = "Os parques que mais param\nnão são os que mais\ndemoram para voltar."
NOTA_2 = ("Disney e Universal podem registrar paradas de jeitos diferentes.\n"
          "Por isso, a comparação mais segura é dentro da mesma empresa.")
LIMIAR_3 = 30          # linha do gráfico 3, em minutos (número redondo, longe dos valores reais)
TITULO_3 = ("No Epic Universe, todas as\natrações grandes têm parada\ntípica abaixo de {limiar} min.\n"
            "No Islands, {acima} de {total} passam disso.")
NOTA_3 = "Parada típica = mediana: metade das paradas daquela atração durou até esse tempo."

PROJETO = "FILAS EM ORLANDO"
DATA = "12/11/2026"
AUTOR = "João Vitor Barberino"
FONTES_DADOS = "Powered by ThemeParks.wiki (dados não oficiais)"

# ---------------------------------------------------------------------------
# Paleta "noite no parque"
# ---------------------------------------------------------------------------
FUNDO = "#16163F"       # azul-noite
CARTAO = "#22225A"      # fundo dos gráficos (um tom acima)
SOMBRA = "#07071F"
CREME = "#FFF4E0"       # texto principal
SEC = "#B9B6E0"         # texto secundário
FRACO = "#3A3A78"       # linhas de grade
CIANO = "#3DDBD9"       # parque A (Epic Universe)
ROSA = "#FF4F9A"        # parque B (Islands of Adventure)
AMARELO = "#FFD23F"     # avisos e anotações
NEUTRO = "#9C99D6"      # os outros parques

NOMES = {
    "magic-kingdom": "Magic Kingdom", "epcot": "EPCOT", "hollywood-studios": "Hollywood Studios",
    "animal-kingdom": "Animal Kingdom", "universal-studios-florida": "Universal Studios",
    "islands-of-adventure": "Islands of Adventure", "epic-universe": "Epic Universe",
}
COR = {A: CIANO, B: ROSA}
POUCAS_PARADAS = 40        # parque com menos paradas que isso aparece vazado ("poucas paradas")

# Posição do nome de cada parque no gráfico 2: (alinhamento, deslocamento x, deslocamento y) em pixels.
# Calibrado com os números de 11/11. Se os pontos mudarem de lugar, confira se os nomes não se sobrepõem.
ROTULOS_2 = {
    "islands-of-adventure": ("center", 0, -38),
    "epic-universe": ("center", 0, 40),
    "epcot": ("left", 22, 0),
    "universal-studios-florida": ("right", -22, 0),
    "hollywood-studios": ("left", 22, -4),
    "magic-kingdom": ("right", -22, 6),
    "animal-kingdom": ("left", 22, 0),
}

# Nomes curtos das atrações (gráfico 3). Sem ™ e ®; o que não estiver aqui é encurtado sozinho.
CURTOS = {
    "Mine-Cart Madness": "Mine-Cart Madness",
    "Harry Potter and the Battle at the Ministry": "Battle at the Ministry",
    "Hiccup's Wing Gliders": "Hiccup's Wing Gliders",
    "Monsters Unchained: The Frankenstein Experiment": "Monsters Unchained",
    "Mario Kart: Bowser's Challenge": "Mario Kart",
    "Pteranodon Flyers": "Pteranodon Flyers",
    "Jurassic World VelociCoaster": "VelociCoaster",
    "Hagrid's Magical Creatures Motorbike Adventure": "Hagrid's Motorbike",
    "Flight of the Hippogriff": "Flight of the Hippogriff",
    "Harry Potter and the Forbidden Journey": "Forbidden Journey",
    "The Incredible Hulk Coaster": "Hulk Coaster",
    "The Amazing Adventures of Spider-Man": "Spider-Man",
}

PASTA = Path(__file__).resolve().parent.parent   # raiz do projeto (este script fica em src/)
PASTA_TRATADOS = PASTA / "dados" / "tratados"
PASTA_FONTES = PASTA / "fontes_quinta"
PASTA_SAIDA = PASTA / "posts" / "02-frequencia-duracao"   # imagens e PDF publicados


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
    no_periodo = lambda l: DATA_INICIO <= l["data"] <= DATA_FIM
    atracoes_dia = [l for l in ler_csv("atracoes_dia.csv") if no_periodo(l) and l["porte"] == "grande"]
    paradas = [p for p in ler_csv("paradas_clima.csv") if no_periodo(p)]
    if not atracoes_dia:
        sys.exit(f"ERRO: nenhuma atração grande entre {DATA_INICIO} e {DATA_FIM}.")

    chave = lambda l: (l["parque"], l["data"], l["atracao"])
    repetidas = [k for k, n in Counter(chave(l) for l in atracoes_dia).items() if n > 1]
    if repetidas:
        print(f"AVISO: {len(repetidas)} atração-dias repetidas (as paradas seriam contadas em dobro): {repetidas[:3]}")

    duracoes = defaultdict(list)          # (parque, data, atracao) -> durações das paradas que contam
    for p in paradas:
        if p["conta_10min"] == "sim" and p["marca_clima"] != "raio":
            duracoes[chave(p)].append(float(p["duracao_min"]))

    horas, dur_parque, dur_atracao = defaultdict(float), defaultdict(list), defaultdict(list)
    for l in atracoes_dia:
        h = (float(l["min_funcionando"]) + float(l["min_parada"])) / 60
        if h <= 0:
            continue
        horas[l["parque"]] += h
        dur_parque[l["parque"]] += duracoes[chave(l)]
        dur_atracao[(l["parque"], l["atracao"])] += duracoes[chave(l)]

    tab = {}
    for parque in NOMES:
        d = dur_parque.get(parque, [])
        if not d:
            sys.exit(f"ERRO: sem paradas de atrações grandes para {NOMES[parque]}.")
        tab[parque] = {"freq": len(d) / horas[parque] * 10, "mediana": statistics.median(d), "n": len(d),
                       "longas": sum(x > 60 for x in d) / horas[parque] * 10}
    atr = {p: sorted(((a, statistics.median(d)) for (pp, a), d in dur_atracao.items() if pp == p and d),
                     key=lambda t: t[1]) for p in (A, B)}
    sem_parada = {p: sorted({l["atracao"] for l in atracoes_dia if l["parque"] == p}
                            - {a for a, _ in atr[p]}) for p in (A, B)}
    for p, nomes in sem_parada.items():
        if nomes:
            print(f"Nota: {NOMES[p]} tem atrações grandes sem nenhuma parada contada (ficam fora do gráfico 3): "
                  f"{', '.join(nomes)}")
    return tab, atr


def conferir(tab, atr):
    print(f"Atrações grandes, paradas de 10 min ou mais, sem raio, {DATA_INICIO} a {DATA_FIM}")
    print(f"{'Parque':22s} {'paradas':>8s} {'por 10h':>8s} {'mediana':>8s} {'>60 min por 10h':>16s}")
    for p in sorted(tab, key=lambda q: -tab[q]["freq"]):
        t = tab[p]
        print(f"{NOMES[p]:22s} {t['n']:8d} {t['freq']:8.3f} {t['mediana']:7.1f}m {t['longas']:16.3f}")
    a, b = tab[A], tab[B]
    print(f"\nCapa: {NOMES[A]} {a['mediana']:.1f} min x {NOMES[B]} {b['mediana']:.1f} min "
          f"(frequência {a['freq']:.2f} x {b['freq']:.2f})")
    if a["mediana"] >= b["mediana"]:
        print(f"AVISO: a mediana do {NOMES[A]} não é menor que a do {NOMES[B]}. O título da capa não vale mais.")
    if round(a["freq"], 2) != 0.77 or round(b["freq"], 2) != 0.83:
        print("AVISO: a frequência não bate com a estreia (0,77 e 0,83). A base mudou? Não use antes de conferir.")
    maximo = max(m for _, m in atr[A])
    acima = [(n, m) for n, m in atr[B] if m > LIMIAR_3]
    print(f"Atrações: maior mediana do {NOMES[A]} = {maximo:.1f} min; {NOMES[B]} acima de {LIMIAR_3} min: "
          f"{len(acima)} de {len(atr[B])} ({', '.join(f'{n} {m:.1f}' for n, m in acima)})")
    if maximo >= LIMIAR_3:
        print(f"AVISO: uma atração do {NOMES[A]} passa de {LIMIAR_3} min. O título da imagem 3 não vale mais.")
    if not acima:
        print("AVISO: nenhuma atração do Islands passa do máximo do Epic. O título da imagem 3 não vale mais.")
    perto = [n for p in (A, B) for n, m in atr[p] if abs(m - LIMIAR_3) < 1]
    if perto:
        print(f"AVISO: {', '.join(perto)} fica a menos de 1 min da linha de {LIMIAR_3} min. Confira o título.")
    for p in tab:
        if tab[p]["n"] < POUCAS_PARADAS:
            print(f"Nota: {NOMES[p]} tem só {tab[p]['n']} paradas: aparece vazado, com '(poucas paradas)'.")
    for p in (A, B):
        print(f"\n{NOMES[p]} (gráfico 3):")
        for n, m in atr[p]:
            print(f"  {curto(n):28s} {m:5.1f} min   ({n})")


# ---------------------------------------------------------------------------
# Desenho: base comum
# ---------------------------------------------------------------------------
F = {}


def carregar_fontes():
    nomes = {"forte": "Rubik-ExtraBold.ttf", "medio": "Rubik-Medium.ttf", "texto": "DMSans-Regular.ttf",
             "texto_forte": "DMSans-Bold.ttf"}
    faltam = [n for n in nomes.values() if not (PASTA_FONTES / n).exists()]
    if faltam:
        sys.exit(f"ERRO: faltam fontes na pasta {PASTA_FONTES}: {', '.join(faltam)}")
    F.update({k: font_manager.FontProperties(fname=str(PASTA_FONTES / n)) for k, n in nomes.items()})


def curto(nome):
    limpo = re.sub(r"[™®©]", "", nome).strip()
    if limpo in CURTOS:
        return CURTOS[limpo]
    limpo = limpo.split(":")[0].strip()
    return limpo if len(limpo) <= 26 else limpo[:25].rstrip() + "..."


def virgula(x, casas=2):
    return f"{x:.{casas}f}".replace(".", ",")


def t(ax, x, y, s, fonte, tam, cor, **kw):
    return ax.text(x, y, s, fontproperties=F[fonte], fontsize=tam, color=cor, **kw)


def linhas(ax, x, y, texto, fonte, tam, cor, passo, **kw):
    """Uma linha por vez, com espaçamento fixo em pixels."""
    for i, linha in enumerate(texto.split("\n")):
        t(ax, x, y + i * passo, linha, fonte, tam, cor, va="top", **kw)
    return y + len(texto.split("\n")) * passo


def depois(ax, obj, folga=10):
    """x (em pixels da folha) onde um texto já desenhado termina."""
    r = ax.figure.canvas.get_renderer()
    return ax.transData.inverted().transform(obj.get_window_extent(r))[1][0] + folga


def caixa(ax, x, y, w, h, r, **kw):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", **kw))


def confete(ax, semente):
    rng = np.random.default_rng(semente)
    for _ in range(140):                                              # só nas margens
        x, y = rng.uniform(0, 1080), rng.uniform(0, 1350)
        if 50 < y < 1320 and 55 < x < 1025:
            continue
        c = rng.choice([CIANO, ROSA, AMARELO, CREME])
        if rng.random() < 0.5:
            ax.add_patch(Circle((x, y), rng.uniform(4, 8), fc=c, ec="none", alpha=0.6, zorder=1))
        else:
            a = rng.uniform(0, math.pi)
            ax.plot([x, x + 16 * math.cos(a)], [y, y + 16 * math.sin(a)], color=c, lw=4, alpha=0.6,
                    solid_capstyle="round", zorder=1)


def folha(titulo, n_folha, tamanho_titulo=42, passo=64, semente=3):
    """Fundo, etiqueta, título, subtítulo e rodapé. Devolve (fig, ax, y logo abaixo do subtítulo)."""
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=FUNDO)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1080)
    ax.set_ylim(1350, 0)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1080, 1350, fc=FUNDO, ec="none", zorder=0))
    confete(ax, semente)
    caixa(ax, 72, 64, 330, 44, 22, fc=CREME, ec="none", zorder=2)
    t(ax, 237, 86, ETIQUETA, "forte", 15, FUNDO, ha="center", va="center", zorder=3)
    y = linhas(ax, 72, 136, titulo, "forte", tamanho_titulo, CREME, passo, zorder=3)
    t(ax, 72, y + 18, SUB, "texto", 17, SEC, va="top", zorder=3)

    for i in range(46):                                               # código de barras decorativo
        ax.add_patch(Rectangle((72 + i * 8.4, 1218), [2, 3, 5][i % 3], 52, fc=CREME, ec="none"))
    t(ax, 480, 1222, PROJETO, "forte", 20, CREME, va="top")
    t(ax, 480, 1252, f"{AUTOR} · {DATA}", "texto", 15, CREME, va="top")
    t(ax, 480, 1280, FONTES_DADOS, "texto", 13.5, SEC, va="top")
    t(ax, 1008, 1222, n_folha, "forte", 20, CIANO, ha="right", va="top")
    return fig, ax, y + 18 + 30


def cartao(ax, x, y, w, h, picote=None):
    """Fundo dos gráficos, em forma de ingresso: entalhes e picote na horizontal, em y = picote."""
    caixa(ax, x + 10, y + 12, w, h, 26, fc=SOMBRA, ec="none", zorder=1.5)
    caixa(ax, x, y, w, h, 26, fc=CARTAO, ec=SOMBRA, lw=3, zorder=2)
    if picote:
        for cx in (x, x + w):
            ax.add_patch(Circle((cx, picote), 24, fc=FUNDO, ec=SOMBRA, lw=3, zorder=2.5))
            ax.add_patch(Rectangle((cx - 28 if cx == x else cx + 1.5, picote - 28), 26.5, 56, fc=FUNDO,
                                   ec="none", zorder=2.6))
        ax.plot([x + 36, x + w - 36], [picote, picote], color=SEC, lw=2, ls=(0, (4, 6)), alpha=0.6, zorder=2.7)


def relogio(ax, cx, cy, r, minutos, cor, fundo, aro, lw=4):
    """Mostrador de 60 min com a fatia da duração (sentido horário a partir das 12)."""
    ax.add_patch(Circle((cx, cy), r, fc=fundo, ec=aro, lw=lw, zorder=6))
    ax.add_patch(Wedge((cx, cy), r - lw, -90, -90 + 360 * min(minutos, 60) / 60, fc=cor, ec="none", zorder=7))
    for k in range(12):
        a = math.radians(-90 + 30 * k)
        r1 = r - lw - (14 if k % 3 == 0 else 8)
        ax.plot([cx + r1 * math.cos(a), cx + (r - lw) * math.cos(a)],
                [cy + r1 * math.sin(a), cy + (r - lw) * math.sin(a)], color=aro, lw=2 if k % 3 == 0 else 1.2,
                zorder=8)
    ax.add_patch(Circle((cx, cy), 6, fc=aro, ec="none", zorder=9))


# ---------------------------------------------------------------------------
# Imagem 1: capa (dois ingressos)
# ---------------------------------------------------------------------------
def capa(tab):
    fig, ax, _ = folha(TITULO_1, "1/3")
    for y, parque in ((470, A), (820, B)):
        cor, d = COR[parque], tab[parque]
        x, w, h, corte = 72, 936, 310, 690
        caixa(ax, x + 10, y + 12, w, h, 26, fc=SOMBRA, ec="none", zorder=2)
        caixa(ax, x, y, w, h, 26, fc=cor, ec=SOMBRA, lw=3, zorder=3)
        for cy in (y, y + h):                                         # entalhes do picote
            ax.add_patch(Circle((x + corte, cy), 26, fc=FUNDO, ec=SOMBRA, lw=3, zorder=4))
            ax.add_patch(Rectangle((x + corte - 30, cy - 30 if cy == y else cy + 1.5), 60, 28.5,
                                   fc=FUNDO, ec="none", zorder=4.5))
        ax.plot([x + corte, x + corte], [y + 34, y + h - 34], color=FUNDO, lw=3, ls=(0, (4, 6)), zorder=5)
        t(ax, x + 40, y + 34, f"INGRESSO · {NOMES[parque].upper()}", "forte", 20, FUNDO, va="top", zorder=6)
        n = t(ax, x + 34, y + 262, f"{d['mediana']:.0f}", "forte", 150, FUNDO, va="baseline", zorder=6)
        m = t(ax, depois(ax, n, 12), y + 262, "min", "forte", 46, FUNDO, va="baseline", zorder=6)
        t(ax, depois(ax, m, 0) - 2, y + 160, "parada\ntípica", "medio", 24, FUNDO, va="center", ha="right",
          linespacing=1.1, zorder=6)
        relogio(ax, x + 812, y + 120, 66, d["mediana"], FUNDO, CREME, FUNDO)
        t(ax, x + 812, y + 232, f"{virgula(d['freq'])} paradas\npor 10 h", "medio", 17, FUNDO, ha="center",
          va="top", linespacing=1.1, zorder=6)
    return fig


# ---------------------------------------------------------------------------
# Imagem 2: os 7 parques (frequência x duração típica)
# ---------------------------------------------------------------------------
def parques(tab):
    fig, ax, y_topo = folha(TITULO_2, "2/3", semente=5)
    cy0, cy1 = y_topo + 10, 1172
    cartao(ax, 72, cy0, 936, cy1 - cy0, picote=cy1 - 92)
    t(ax, 110, cy1 - 46, NOTA_2, "texto", 15, SEC, va="center", linespacing=1.35, zorder=3)

    x0, x1, y0, y1 = 190, 960, cy1 - 175, cy0 + 70          # área do gráfico (y0 = base)
    xmax = 1.0
    ymax = max(80, 20 * (int(max(d["mediana"] for d in tab.values()) // 20) + 1))
    X = lambda v: x0 + v / xmax * (x1 - x0)
    Y = lambda v: y0 - v / ymax * (y0 - y1)

    for v in range(0, ymax + 1, 20):                            # grade
        ax.plot([x0, x1], [Y(v), Y(v)], color=FRACO, lw=1.2, zorder=3)
        t(ax, x0 - 16, Y(v), str(v), "texto", 15, SEC, ha="right", va="center", zorder=3)
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        ax.plot([X(v), X(v)], [y0, y0 + 8], color=SEC, lw=1.2, zorder=3)
        t(ax, X(v), y0 + 14, virgula(v) if v else "0", "texto", 15, SEC, ha="center", va="top", zorder=3)
    ax.plot([x0, x1], [y0, y0], color=SEC, lw=1.6, zorder=3)
    t(ax, x1, y0 + 44, "paradas por 10 h de operação", "texto_forte", 16, CREME, ha="right", va="top", zorder=3)
    t(ax, x0 - 16, y1 - 26, "duração típica de uma parada (min)", "texto_forte", 16, CREME, ha="left",
      va="bottom", zorder=3)

    # cantos: como ler o gráfico
    cantos = [(x1 - 12, y1 + 10, "right", "top", "param muito,\ndemoram a voltar"),
              (x1 - 12, y0 - 10, "right", "bottom", "param muito,\nvoltam rápido")]
    for x, y, ha, va, texto in cantos:
        t(ax, x, y, texto, "texto", 14, SEC, ha=ha, va=va, alpha=0.75, linespacing=1.15, zorder=3)

    for parque, d in tab.items():
        dupla = parque in (A, B)
        cor = COR.get(parque, NEUTRO)
        x, y = X(d["freq"]), Y(d["mediana"])
        poucas = d["n"] < POUCAS_PARADAS
        ax.add_patch(Circle((x, y), 16 if dupla else 10, fc=CARTAO if poucas else cor, ec=cor, lw=2.5,
                            zorder=6))
        ha, dx, dy = ROTULOS_2[parque]
        nome = NOMES[parque] + ("\n(poucas paradas)" if poucas else "")
        t(ax, x + dx, y + dy, nome, "forte" if dupla else "texto", 20 if dupla else 16, cor, ha=ha, va="center",
          linespacing=1.1, zorder=7)

    a, b = tab[A], tab[B]
    xm = max(X(a["freq"]), X(b["freq"])) + 40
    ax.annotate("", xy=(xm, Y(a["mediana"]) + 4), xytext=(xm, Y(b["mediana"]) - 4),
                arrowprops=dict(arrowstyle="<->", color=AMARELO, lw=2), zorder=7)
    t(ax, xm + 12, (Y(a["mediana"]) + Y(b["mediana"])) / 2, f"+{b['mediana'] - a['mediana']:.0f}\nmin",
      "forte", 18, AMARELO, ha="left", va="center", linespacing=1.0, zorder=7)
    return fig


# ---------------------------------------------------------------------------
# Imagem 3: uma barra por atração grande (Epic x Islands)
# ---------------------------------------------------------------------------
def atracoes(atr):
    acima = [m for _, m in atr[B] if m > LIMIAR_3]
    titulo = TITULO_3.format(limiar=LIMIAR_3, acima=len(acima), total=len(atr[B]))
    fig, ax, y_topo = folha(titulo, "3/3", tamanho_titulo=40, passo=60, semente=9)
    cy0, cy1 = y_topo + 10, 1172
    cartao(ax, 72, cy0, 936, cy1 - cy0, picote=cy1 - 62)
    t(ax, 110, cy1 - 31, NOTA_3, "texto", 14.5, SEC, va="center", zorder=3)

    n_barras = len(atr[A]) + len(atr[B])
    area = (cy1 - 62 - 30) - (cy0 + 30) - 2 * 46 - 40         # espaço para as barras
    passo = min(34, area / n_barras)
    alt = passo * 0.66
    xn, x0, x1 = 112, 400, 900                                  # nomes | início das barras | 60 min
    vmax = max(60, 15 * math.ceil(max(m for p in atr for _, m in atr[p]) / 15))
    X = lambda v: x0 + v / vmax * (x1 - x0)

    y = cy0 + 30
    topo_barras = None
    for parque in (A, B):
        cor = COR[parque]
        rot = t(ax, xn + 12, y + 17, f"{NOMES[parque].upper()} · {len(atr[parque])} atrações", "forte", 14,
                FUNDO, va="center", zorder=4)
        caixa(ax, xn - 6, y, depois(ax, rot, 18) - (xn - 6), 34, 17, fc=cor, ec="none", zorder=3)
        y += 46
        topo_barras = topo_barras or y
        for nome, m in sorted(atr[parque], key=lambda k: -k[1]):
            destaque = parque == A or m > LIMIAR_3
            caixa(ax, x0, y + (passo - alt) / 2, X(m) - x0, alt, alt / 2, fc=cor, ec="none",
                  alpha=1 if destaque else 0.4, zorder=4)
            t(ax, x0 - 14, y + passo / 2, curto(nome), "texto", 15, CREME if destaque else SEC, ha="right",
              va="center", zorder=4)
            t(ax, X(m) + 10, y + passo / 2, f"{m:.0f}", "forte", 15, cor, ha="left", va="center",
              alpha=1 if destaque else 0.6, zorder=6,
              bbox=dict(boxstyle="square,pad=0.15", fc=CARTAO, ec="none"))      # tampa a linha amarela
            y += passo
        y += 14
    base = y + 4

    xm = X(LIMIAR_3)                                            # linha de referência
    ax.plot([xm, xm], [topo_barras - 10, base], color=AMARELO, lw=2, ls=(0, (3, 4)), zorder=5)
    t(ax, xm, topo_barras - 50, f"linha de {LIMIAR_3} min", "forte", 15, AMARELO, ha="center",
      va="center", zorder=5)
    for v in range(0, vmax + 1, 15):                            # escala
        t(ax, X(v), base + 6, f"{v} min" if v == vmax else str(v), "texto", 13, SEC, ha="center", va="top",
          zorder=4)
    return fig


# ---------------------------------------------------------------------------
def gerar(tab, atr, pasta_saida):
    pasta_saida.mkdir(parents=True, exist_ok=True)
    carregar_fontes()
    plt.rcParams["pdf.fonttype"] = 42
    figuras = [("post2_1_capa.png", capa(tab)),
               ("post2_2_parques.png", parques(tab)),
               ("post2_3_atracoes.png", atracoes(atr))]
    with PdfPages(pasta_saida / "carrossel_frequencia_duracao.pdf") as pdf:
        for nome, fig in figuras:
            fig.savefig(pasta_saida / nome, dpi=100, facecolor=FUNDO)
            pdf.savefig(fig, facecolor=FUNDO)
            plt.close(fig)
    print(f"\nGravados em {pasta_saida}: {', '.join(n for n, _ in figuras)} e carrossel_frequencia_duracao.pdf")


def main():
    tab, atr = calcular()
    conferir(tab, atr)
    gerar(tab, atr, PASTA_SAIDA)


if __name__ == "__main__":
    main()
