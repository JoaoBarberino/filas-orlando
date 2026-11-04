"""
Projeto "Filas em Orlando": limpeza das paradas (pilar 2).

Lê o histórico bruto baixado pelo baixar_historico.py e aplica as regras de
limpeza aprovadas em 04/11/2026 (seção 4.9 do projeto-filas-orlando.md):

  1. Só o horário normal (OPERATING) conta como parque aberto. Entrada
     antecipada, horas extras e eventos pagos ficam de fora.
  2. Contagem de paradas: só as de 10 minutos ou mais. A disponibilidade usa
     todos os minutos parados.
  3. Atração que não funcionou nenhuma vez no horário normal do dia sai da
     conta daquele dia (reforma, fechamento planejado). Exceção, a confirmar:
     se ficou DOWN 10 min ou mais, é quebra e entra (CONTAR_QUEBRA_DIA_INTEIRO).
  4. Casas do Halloween Horror Nights ficam fora.
  5. Paradas separadas por uma volta curta (até 5 minutos) viram uma só.
  6. Clima: NÃO é filtrado aqui (é o checar_clima.py, com os registros de
     raio dos aeroportos). A coluna "outras_paradas_perto_do_inicio" mostra
     paradas em grupo.
  7. Fuso: UTC convertido para America/New_York com zoneinfo.
  8. Dia sem arquivo ou sem horário vira "sem informação", nunca "zero paradas".
  9. Comparar atrações do mesmo porte: cada atração ganha a fila anunciada
     média (só no horário normal) e um "porte" (sem_fila, menor, grande).
     Atrações sem fila anunciada (passeio a pé, trilha, playground) saem das
     comparações por porte.
  10. Teatros e cinemas (lista TEATROS_E_CINEMAS) saem de tudo: a Universal
      registra os dela como "show", a Disney como "atração".
  Medida principal: paradas de 10 min ou mais por 10 horas de operação da
  atração (minutos funcionando + parada, no horário normal).

Como rodar (dentro da mesma pasta do baixar_historico.py):
    pip install tzdata      (só no Windows, uma vez)
    python limpar_paradas.py

Gera, em dados/tratados/:
    paradas.csv        uma linha por parada (dentro do horário normal)
    atracoes_dia.csv   uma linha por atração por dia: minutos funcionando,
                       parada, fechada e a disponibilidade
    exclusoes.csv      o que ficou de fora e por quê

Dados: Powered by ThemeParks.wiki (https://themeparks.wiki).
Os termos de uso NÃO permitem publicar os dados, nem os tratados. Os CSVs
ficam só no seu computador (a pasta "dados" já está no .gitignore).
"""

import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/New_York")
except Exception:
    sys.exit("ERRO: fuso horário não encontrado. No Windows, rode uma vez:\n"
             "    pip install tzdata")

# ---------------------------------------------------------------------------
# Configuração (mude aqui, não no meio do código)
# ---------------------------------------------------------------------------
MINUTOS_MINIMOS = 10          # regra 2: só paradas com 10 min ou mais entram na contagem
JUNTAR_SE_VOLTA_EM_ATE = 5    # regra 5: volta de até 5 min entre duas paradas = uma parada só
LIMITE_ALERTA_EVENTO = 0.30   # avisa se uma atração funciona menos de 30% do tempo no horário normal...
MINIMO_HORAS_ALERTA = 10      # ...e funcionou pelo menos 10 h na base (evita alerta de atração em reforma)
JANELA_SIMULTANEAS = 5        # minutos antes e depois do início para contar paradas "em grupo"

# Regra 9 (04/11/2026): comparar atrações do mesmo porte. O "porte" vem da fila
# anunciada média da atração na base inteira (média ponderada pelo tempo, só
# quando ela estava funcionando). Atração sem fila anunciada (passeio a pé,
# trilha, playground, teatro) sai das comparações.
FILA_MINIMA = 1               # média abaixo de 1 min = "sem_fila"
PORTE_GRANDE = 20             # média de 20 min ou mais = "grande"; entre 1 e 20 = "menor"

# Regra 3, ajuste proposto em 04/11 (A CONFIRMAR COM O JOÃO): atração que não
# funcionou no dia, mas ficou como DOWN por 10 min ou mais no horário normal,
# é quebra (ex.: Pirates of the Caribbean em 14/10, DOWN o dia inteiro), não
# fechamento planejado. True = conta como parada; False = sai da conta.
CONTAR_QUEBRA_DIA_INTEIRO = True

EMPRESA = {
    "magic-kingdom": "Disney",
    "epcot": "Disney",
    "hollywood-studios": "Disney",
    "animal-kingdom": "Disney",
    "universal-studios-florida": "Universal",
    "islands-of-adventure": "Universal",
    "epic-universe": "Universal",
}

# Regra 4: casas do Halloween Horror Nights 2026 (Universal Studios Florida).
# Identificadas em 04/11/2026: funcionam quase só na janela do evento pago.
EVENTO_PAGO = {
    "Sinners",
    "INVASION: Alien Abduction",
    "Ozzy Osbourne: Prince of Darkness",
    "Evil Dead Burn",
    "MADLANDS: Caged Cannibals",
    "Cybergoria",
    "H.R. Bloodengutz Presents: A Halloween Fright-Tacular!",
    "Hellraiser",
    "Stranger Things 5",
    "Jack & Oddfellow: Chaos & Control",
}

# Regra 10 (04/11/2026): teatros e cinemas saem de TODAS as comparações. A Universal
# registra os dela como "show" (fora da lista de atrações); a Disney registra vários
# como "atração". Tirando os da Disney, os dois lados ficam iguais. A fila anunciada
# deles também engana: costuma ser o tempo até a próxima sessão.
TEATROS_E_CINEMAS = {
    # Magic Kingdom
    "Country Bear Musical Jamboree", "Mickey's PhilharMagic", "Monsters, Inc. Laugh Floor",
    "The Hall of Presidents", "Walt Disney's Enchanted Tiki Room", "Enchanted Tales with Belle",
    # EPCOT
    "Impressions de France", "Palais du Cinéma", "Canada Far and Wide in Circle-Vision 360",
    "Reflections of China", "Beauty and the Beast Sing-Along", "Turtle Talk With Crush",
    "Disney and Pixar Short Film Festival", "Awesome Planet", "The American Adventure",
    # Hollywood Studios
    "Vacation Fun - An Original Animated Short with Mickey & Minnie", "Once Upon a Studio Theater",
    "Walt Disney Presents", "Olaf Draws!",
    # Animal Kingdom
    "Zootopia: Better Zoogether!",
}

STATUS_CONHECIDOS = {"OPERATING", "DOWN", "CLOSED", "REFURBISHMENT"}

PASTA = Path(__file__).parent
PASTA_HISTORICO = PASTA / "dados" / "brutos" / "historico"
PASTA_HORARIOS = PASTA / "dados" / "brutos" / "horarios"
PASTA_SAIDA = PASTA / "dados" / "tratados"


def ler_data_hora(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def minutos(inicio, fim):
    # conta em UTC: no dia da troca de horário (01/11), a conta no fuso local erra 1 hora
    return (fim.astimezone(timezone.utc) - inicio.astimezone(timezone.utc)).total_seconds() / 60


# ---------------------------------------------------------------------------
# Horário normal de cada parque (regra 1)
# ---------------------------------------------------------------------------
def carregar_horario_normal(parque):
    """Devolve {data: [(abertura, fechamento), ...]} só com as janelas OPERATING."""
    janelas = defaultdict(list)
    for arquivo in sorted((PASTA_HORARIOS / parque).glob("*.json")):
        for item in json.loads(arquivo.read_text(encoding="utf-8")).get("schedule", []):
            if item.get("type") == "OPERATING" and item.get("openingTime"):
                janelas[item["date"]].append(
                    (ler_data_hora(item["openingTime"]), ler_data_hora(item["closingTime"])))
    return janelas


# ---------------------------------------------------------------------------
# Linha do tempo de uma atração num dia
# ---------------------------------------------------------------------------
def linha_do_tempo(entidade, inicio_dia, fim_dia):
    """Trechos [inicio, fim, status] do dia inteiro, já juntando status repetidos."""
    abertura = entidade.get("opening") or {}
    mudancas = [(inicio_dia, abertura.get("status"))]
    for linha in entidade.get("history", []):
        mudancas.append((max(ler_data_hora(linha["time"]), inicio_dia), linha.get("status")))
    mudancas.sort(key=lambda m: m[0])

    trechos = []
    for momento, status in mudancas:
        if status not in STATUS_CONHECIDOS:
            status = "DESCONHECIDO"
        if trechos and trechos[-1][2] == status:
            continue
        if trechos:
            trechos[-1][1] = momento
        trechos.append([momento, fim_dia, status])
    return [t for t in trechos if t[1] > t[0]]


def recortar(trechos, janelas):
    """Só a parte dos trechos que cai dentro do horário normal (uma lista por janela)."""
    por_janela = []
    for abre, fecha in janelas:
        dentro = []
        for inicio, fim, status in trechos:
            a, b = max(inicio, abre), min(fim, fecha)
            if b > a:
                dentro.append((a, b, status))
        por_janela.append((abre, fecha, dentro))
    return por_janela


def fila_funcionando(entidade, inicio_dia, fim_dia, janelas):
    """Soma (fila anunciada x minutos) e os minutos com fila, só com a atração funcionando
    e só dentro do horário normal (corrigido em 04/11: antes contava também horas extras,
    entrada antecipada e o fim da noite)."""
    estados = [(inicio_dia, entidade.get("opening") or {})]
    estados += sorted(((max(ler_data_hora(l["time"]), inicio_dia), l) for l in entidade.get("history", [])),
                      key=lambda e: e[0])
    soma = peso = 0.0
    for (momento, estado), (seguinte, _) in zip(estados, estados[1:] + [(fim_dia, None)]):
        espera = ((estado.get("queue") or {}).get("STANDBY") or {}).get("waitTime")
        if estado.get("status") != "OPERATING" or espera is None:
            continue
        for abre, fecha in janelas:
            duracao = minutos(max(momento, abre), min(seguinte, fecha))
            if duracao > 0:
                soma += espera * duracao
                peso += duracao
    return soma, peso


def classificar_porte(media):
    if media is None or media < FILA_MINIMA:
        return "sem_fila"
    return "grande" if media >= PORTE_GRANDE else "menor"


def juntar_paradas(dentro):
    """Regra 5: junta paradas separadas por uma volta de até JUNTAR_SE_VOLTA_EM_ATE minutos."""
    paradas = []
    for inicio, fim, status in dentro:
        if status != "DOWN":
            continue
        if paradas and minutos(paradas[-1]["fim"], inicio) <= JUNTAR_SE_VOLTA_EM_ATE:
            paradas[-1]["fim"] = fim
            paradas[-1]["minutos_parada"] += minutos(inicio, fim)
            paradas[-1]["juntadas"] += 1
        else:
            paradas.append({"inicio": inicio, "fim": fim,
                            "minutos_parada": minutos(inicio, fim), "juntadas": 1})
    return paradas


# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
def processar_parque(parque, dias_esperados):
    horario = carregar_horario_normal(parque)
    linhas_paradas, linhas_dia, linhas_exclusao = [], [], []
    alerta_dentro, alerta_total = Counter(), Counter()
    fila_soma, fila_peso = Counter(), Counter()

    for dia in dias_esperados:
        texto_dia = dia.isoformat()
        arquivo = PASTA_HISTORICO / parque / f"{texto_dia}.json.gz"
        if not arquivo.exists():
            linhas_exclusao.append([parque, texto_dia, "", "dia sem arquivo de histórico (sem informação)"])
            continue
        janelas = horario.get(texto_dia)
        if not janelas:
            linhas_exclusao.append([parque, texto_dia, "", "dia sem horário normal (sem informação)"])
            continue

        with gzip.open(arquivo, "rt", encoding="utf-8") as f:
            dados = json.load(f)
        atracoes = [e for e in dados.get("entities", []) if e.get("entityType") == "ATTRACTION"]
        if not atracoes:
            linhas_exclusao.append([parque, texto_dia, "", "histórico vazio (sem informação)"])
            continue

        inicio_dia = datetime(dia.year, dia.month, dia.day, tzinfo=FUSO)
        fim_dia = datetime.combine(dia + timedelta(1), datetime.min.time(), tzinfo=FUSO)

        paradas_do_dia = []      # (nome, parada) para calcular a simultaneidade depois
        trechos_down = []        # trechos DOWN crus, dentro do horário normal, de todas as atrações

        for entidade in atracoes:
            nome = entidade.get("name", "")
            trechos = linha_do_tempo(entidade, inicio_dia, fim_dia)
            por_janela = recortar(trechos, janelas)

            soma = Counter()
            for _, _, dentro in por_janela:
                for a, b, status in dentro:
                    soma[status] += minutos(a, b)

            # dado para o alerta de atrações que só funcionam fora do horário normal
            total_funcionando = sum(minutos(a, b) for a, b, s in trechos if s == "OPERATING")
            alerta_dentro[nome] += soma["OPERATING"]
            alerta_total[nome] += total_funcionando

            s, p = fila_funcionando(entidade, inicio_dia, fim_dia, janelas)
            fila_soma[entidade.get("id", "")] += s
            fila_peso[entidade.get("id", "")] += p

            if nome in TEATROS_E_CINEMAS:
                linhas_exclusao.append([parque, texto_dia, nome, "teatro ou cinema (a Universal registra como show)"])
                continue
            if nome in EVENTO_PAGO:
                linhas_exclusao.append([parque, texto_dia, nome, "casa do Halloween Horror Nights (evento pago)"])
                continue
            if soma["OPERATING"] == 0:
                quebra_dia_inteiro = soma["DOWN"] >= MINUTOS_MINIMOS
                if not (quebra_dia_inteiro and CONTAR_QUEBRA_DIA_INTEIRO):
                    motivo = "não funcionou no horário normal"
                    if quebra_dia_inteiro:
                        motivo += f" (ficou {soma['DOWN']:.0f} min como DOWN)"
                    linhas_exclusao.append([parque, texto_dia, nome, motivo])
                    continue
                print(f"  quebra o dia todo: {parque} {texto_dia} {nome} "
                      f"({soma['DOWN']:.0f} min DOWN, nenhum minuto funcionando)")

            n_contadas = 0
            for abre, fecha, dentro in por_janela:
                for a, b, s in dentro:
                    if s == "DOWN":
                        trechos_down.append((nome, a, b))
                for p in juntar_paradas(dentro):
                    p["duracao"] = minutos(p["inicio"], p["fim"])
                    p["conta"] = p["duracao"] >= MINUTOS_MINIMOS
                    p["na_abertura"] = p["inicio"] == abre
                    p["ate_fechamento"] = p["fim"] == fecha
                    n_contadas += p["conta"]
                    paradas_do_dia.append((nome, entidade.get("id", ""), p))

            funcionando, parada = soma["OPERATING"], soma["DOWN"]
            linhas_dia.append([
                parque, EMPRESA[parque], texto_dia, nome, entidade.get("id", ""),
                round(sum(minutos(a, b) for a, b in janelas)),
                round(funcionando, 1), round(parada, 1),
                round(soma["CLOSED"] + soma["REFURBISHMENT"], 1), round(soma["DESCONHECIDO"], 1),
                round(funcionando / (funcionando + parada), 4),
                n_contadas,
            ])

        # simultaneidade: quantas OUTRAS atrações estiveram paradas até 5 min antes ou depois
        # do início desta (sinal de clima ou de falha geral do dado)
        folga = timedelta(minutes=JANELA_SIMULTANEAS)
        for nome, id_atracao, p in paradas_do_dia:
            outras = {n for n, a, b in trechos_down
                      if n != nome and a < p["inicio"] + folga and b > p["inicio"] - folga}
            linhas_paradas.append([
                parque, EMPRESA[parque], texto_dia, nome, id_atracao,
                p["inicio"].astimezone(FUSO).isoformat(timespec="minutes"),
                p["fim"].astimezone(FUSO).isoformat(timespec="minutes"),
                round(p["duracao"], 1), round(p["minutos_parada"], 1), p["juntadas"],
                "sim" if p["conta"] else "não",
                "sim" if p["na_abertura"] else "não",
                "sim" if p["ate_fechamento"] else "não",
                len(outras),
            ])

    alertas = [(nome, alerta_dentro[nome] / alerta_total[nome])
               for nome in alerta_total
               if nome not in EVENTO_PAGO and alerta_total[nome] >= MINIMO_HORAS_ALERTA * 60
               and alerta_dentro[nome] / alerta_total[nome] < LIMITE_ALERTA_EVENTO]

    # regra 9: porte de cada atração (coluna nova no fim das duas tabelas)
    media_fila = {i: fila_soma[i] / fila_peso[i] for i in fila_peso if fila_peso[i] > 0}
    for linha in linhas_dia + linhas_paradas:
        media = media_fila.get(linha[4])
        linha += ["" if media is None else round(media, 1), classificar_porte(media)]
    return linhas_paradas, linhas_dia, linhas_exclusao, alertas


def percentual_parado(linhas):
    """Minutos parada / (funcionando + parada), somando várias linhas de atracoes_dia."""
    funcionando = sum(l[6] for l in linhas)
    parada = sum(l[7] for l in linhas)
    return parada / (funcionando + parada) if funcionando + parada else 0.0


def gravar(nome_arquivo, cabecalho, linhas):
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    with open(PASTA_SAIDA / nome_arquivo, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def main():
    parques = [p for p in EMPRESA if (PASTA_HISTORICO / p).exists()]
    if not parques:
        sys.exit(f"ERRO: não achei dados em {PASTA_HISTORICO}. Rode antes o baixar_historico.py.")

    datas = sorted(date.fromisoformat(a.name[:10])
                   for p in parques for a in (PASTA_HISTORICO / p).glob("*.json.gz"))
    dias = [datas[0] + timedelta(n) for n in range((datas[-1] - datas[0]).days + 1)]
    print(f"Base: {dias[0]:%d/%m/%Y} a {dias[-1]:%d/%m/%Y} ({len(dias)} dias), {len(parques)} parques\n")

    todas_paradas, todos_dias, todas_exclusoes = [], [], []
    for parque in parques:
        paradas, linhas_dia, exclusoes, alertas = processar_parque(parque, dias)
        todas_paradas += paradas
        todos_dias += linhas_dia
        todas_exclusoes += exclusoes
        for nome, fracao in alertas:
            print(f"  ALERTA {parque}: '{nome}' funciona só {fracao:.0%} do tempo no horário normal. "
                  f"Evento pago? Se for, coloque na lista EVENTO_PAGO.")

    gravar("paradas.csv",
           ["parque", "empresa", "data", "atracao", "id_atracao", "inicio_local", "fim_local",
            "duracao_min", "minutos_parada", "paradas_juntadas", "conta_10min",
            "ja_parada_na_abertura", "parada_ate_fechamento", "outras_paradas_perto_do_inicio",
            "fila_media_min", "porte"],
           todas_paradas)
    gravar("atracoes_dia.csv",
           ["parque", "empresa", "data", "atracao", "id_atracao", "minutos_horario_normal",
            "min_funcionando", "min_parada", "min_fechada", "min_desconhecido",
            "disponibilidade", "paradas_10min", "fila_media_min", "porte"],
           todos_dias)
    gravar("exclusoes.csv", ["parque", "data", "atracao", "motivo"], todas_exclusoes)

    # ---- resumo para conferência no terminal (NÃO publicar estes números sem revisão) ----
    # Medida principal (04/11): paradas por 10 horas de operação da atração
    # (operação = minutos funcionando + parada, no horário normal). Justa entre parques
    # com horários diferentes (ex.: Universal com dias curtos no Halloween Horror Nights).
    reguas = {"todas": ("sem_fila", "menor", "grande"), "com fila": ("menor", "grande"), "grandes": ("grande",)}
    print("\nParadas de 10 min ou mais por 10 horas de operação (sem tirar o raio; isso é no checar_clima.py):")
    print(f"{'Parque':27s} " + " ".join(f"{r:>10s}" for r in reguas) + f" {'% parado (grandes)':>19s}")
    for parque in parques:
        partes = []
        for aceitos in reguas.values():
            linhas = [l for l in todos_dias if l[0] == parque and l[13] in aceitos]
            horas = sum(l[6] + l[7] for l in linhas) / 60
            partes.append(f"{sum(l[11] for l in linhas) / horas * 10:10.2f}" if horas else f"{'-':>10s}")
        grandes = [l for l in todos_dias if l[0] == parque and l[13] == "grande"]
        print(f"{parque:27s} " + " ".join(partes) + f" {percentual_parado(grandes):19.1%}")

    motivos = Counter(e[3].split(" (")[0] for e in todas_exclusoes)
    print("\nExclusões (atração-dia ou dia):")
    for motivo, n in motivos.most_common():
        print(f"  {n:5d}  {motivo}")
    print(f"\nArquivos gravados em {PASTA_SAIDA}")
    print("Próximo passo: python checar_clima.py (marca as paradas com raio por perto).")


if __name__ == "__main__":
    main()
