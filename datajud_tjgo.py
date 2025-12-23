import requests
import json
from datetime import datetime

# 1) Configurações básicas
API_KEY = "APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="  # confira na wiki do DataJud se a chave mudou
BASE_URL = "https://api-publica.datajud.cnj.jus.br"
TRIBUNAL_ALIAS = "api_publica_tjgo"  # TJGO; para outro tribunal, troque o alias

# 2) Defina aqui se quer buscar TUDO (match_all) ou por número
BUSCAR_POR_NUMERO = False  # coloque True quando quiser buscar por um número específico
NUMERO_PROCESSO = "6117330-06.2024.8.09.0144"  # ajuste aqui quando BUSCAR_POR_NUMERO=True

if BUSCAR_POR_NUMERO:
    query = {
        "match": {
            "numeroProcesso": NUMERO_PROCESSO
        }
    }
else:
    # teste genérico: qualquer processo
    query = {
        "match_all": {}
    }

# 3) Corpo da requisição
payload = {
    "size": 1,  # traz só 1 processo
    "_source": [
        "numeroProcesso",
        "classeProcessual",
        "assuntos",
        "orgaoJulgador",
        "dataAjuizamento",
        "dataBaixa",
        "movimentos"
    ],
    "query": query
}

# 4) Cabeçalhos HTTP
headers = {
    "Authorization": API_KEY,
    "Content-Type": "application/json"
}

# 5) Faz a requisição POST ao DataJud
url = f"{BASE_URL}/{TRIBUNAL_ALIAS}/_search"
response = requests.post(url, headers=headers, json=payload)

print("Status code:", response.status_code)

if response.status_code != 200:
    print("Erro ao consultar DataJud:", response.text)
    raise SystemExit()

data = response.json()

# Verifica se veio algum processo
hits = data.get("hits", {}).get("hits", [])
if not hits:
    print("Nenhum processo retornado pelo DataJud para esse filtro.")
    raise SystemExit()

# Pega o primeiro processo retornado
proc = hits[0].get("_source", {})

numero = proc.get("numeroProcesso")
classe = proc.get("classeProcessual")
assuntos = proc.get("assuntos", [])
orgao = proc.get("orgaoJulgador") or {}
orgao_nome = orgao.get("nome")
data_ajuiz = proc.get("dataAjuizamento")
data_baixa = proc.get("dataBaixa")
movimentos = proc.get("movimentos", [])

def formata_data_br(valor):
    """Converte datas tipo '20150810000000' ou '2025-09-15T09:34:12.000Z' para formato dd/mm/aaaa hh:mm."""
    if not valor:
        return "—"
    s = str(valor)
    try:
        if "T" in s:
            # formato ISO: 2025-09-15T09:34:12.000Z
            dt = datetime.fromisoformat(s.replace("Z", ""))
        else:
            # formato numérico: 20150810000000 (yyyymmddHHMMSS)
            dt = datetime.strptime(s, "%Y%m%d%H%M%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return s

print("\n=== RESUMO DO PROCESSO ===")
print("Número:        ", numero)
print("Classe:        ", classe)
print("Órgão julgador:", orgao_nome)
print("Data ajuiz.:   ", formata_data_br(data_ajuiz))
print("Data baixa:    ", formata_data_br(data_baixa))

print("\nAssuntos:")
for a in assuntos:
    nome_assunto = a.get("nome")
    codigo_assunto = a.get("codigo")
    print(f"  - ({codigo_assunto}) {nome_assunto}")

print("\nÚltimos movimentos (até 10):")
for m in movimentos[-10:]:
    codigo_mov = m.get("codigo")
    nome_mov = m.get("nome")
    data_mov = formata_data_br(m.get("dataHora"))
    print(f"  - {data_mov} | ({codigo_mov}) {nome_mov}")
