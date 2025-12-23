import json
from datetime import datetime
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# =============================================
# CONFIGURAÇÃO BÁSICA
# =============================================

# Chave pública do DataJud (confira na wiki se mudar)
DATAJUD_API_KEY = "APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

DEFAULT_SOURCE_FIELDS = [
    "numeroProcesso",
    "classeProcessual",
    "assuntos",
    "orgaoJulgador",
    "dataAjuizamento",
    "dataBaixa",
    "movimentos",
]

# =============================================
# MODELOS DE REQUISIÇÃO / RESPOSTA
# =============================================


class DatajudSearchRequest(BaseModel):
    tribunal_alias: str  # ex.: api_publica_tjgo, api_publica_tjsp
    numero_processo: Optional[str] = None  # busca exata por número CNJ
    assunto_codigo: Optional[int] = None   # código da tabela de assuntos do CNJ
    classe_processual: Optional[int] = None  # código da classe processual
    data_ajuizamento_ini: Optional[str] = None  # "YYYY-MM-DD"
    data_ajuizamento_fim: Optional[str] = None  # "YYYY-MM-DD"
    size: int = 10  # quantos processos retornar (máx. que você quiser)
    source_fields: Optional[List[str]] = None   # se quiser customizar os campos retornados


class MovimentoSimplificado(BaseModel):
    data: Optional[str]
    codigo: Optional[int]
    nome: Optional[str]


class ProcessoSimplificado(BaseModel):
    numero: Optional[str]
    classe: Optional[Any]
    orgao_julgador: Optional[str]
    data_ajuizamento: Optional[str]
    data_baixa: Optional[str]
    assuntos: List[Dict[str, Any]]
    ultimos_movimentos: List[MovimentoSimplificado]


class DatajudSearchResponse(BaseModel):
    total: int
    processos: List[ProcessoSimplificado]


# =============================================
# FUNÇÕES AUXILIARES
# =============================================

def formata_data_br(valor: Optional[Any]) -> Optional[str]:
    """Converte datas tipo '20150810000000' ou '2025-09-15T09:34:12.000Z' para dd/mm/aaaa hh:mm."""
    if not valor:
        return None
    s = str(valor)
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", ""))
        else:
            dt = datetime.strptime(s, "%Y%m%d%H%M%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return s


def build_es_query(req: DatajudSearchRequest) -> Dict[str, Any]:
    """Monta o objeto 'query' no estilo Elasticsearch conforme os filtros da requisição."""
    must_clauses = []

    if req.numero_processo:
        must_clauses.append({"match": {"numeroProcesso": req.numero_processo}})

    if req.assunto_codigo is not None:
        must_clauses.append({"term": {"assuntos.codigo": req.assunto_codigo}})

    if req.classe_processual is not None:
        must_clauses.append({"term": {"classeProcessual": req.classe_processual}})

    if req.data_ajuizamento_ini or req.data_ajuizamento_fim:
        range_filter: Dict[str, Any] = {}
        if req.data_ajuizamento_ini:
            range_filter["gte"] = req.data_ajuizamento_ini
        if req.data_ajuizamento_fim:
            range_filter["lte"] = req.data_ajuizamento_fim
        must_clauses.append({"range": {"dataAjuizamento": range_filter}})

    if not must_clauses:
        # se nenhum filtro foi passado, usa match_all (cuidado em produção!)
        return {"match_all": {}}

    return {"bool": {"must": must_clauses}}


def simplificar_processo(source: Dict[str, Any]) -> ProcessoSimplificado:
    numero = source.get("numeroProcesso")
    classe = source.get("classeProcessual")
    orgao = source.get("orgaoJulgador") or {}
    orgao_nome = orgao.get("nome")

    data_ajuiz = formata_data_br(source.get("dataAjuizamento"))
    data_baixa = formata_data_br(source.get("dataBaixa"))

    assuntos = source.get("assuntos", []) or []
    movimentos = source.get("movimentos", []) or []

    ultimos = []
    for m in movimentos[-10:]:
        ultimos.append(
            MovimentoSimplificado(
                data=formata_data_br(m.get("dataHora")),
                codigo=m.get("codigo"),
                nome=m.get("nome"),
            )
        )

    return ProcessoSimplificado(
        numero=numero,
        classe=classe,
        orgao_julgador=orgao_nome,
        data_ajuizamento=data_ajuiz,
        data_baixa=data_baixa,
        assuntos=assuntos,
        ultimos_movimentos=ultimos,
    )


# =============================================
# APLICAÇÃO FASTAPI
# =============================================

app = FastAPI(title="Bridge DataJud → GPT", version="1.0.0")


@app.post("/datajud/search", response_model=DatajudSearchResponse)
def search_datajud(req: DatajudSearchRequest):
    # Monta payload para o DataJud
    source_fields = req.source_fields or DEFAULT_SOURCE_FIELDS

    payload = {
        "size": req.size,
        "_source": source_fields,
        "query": build_es_query(req),
    }

    headers = {
        "Authorization": DATAJUD_API_KEY,
        "Content-Type": "application/json",
    }

    url = f"{DATAJUD_BASE_URL}/{req.tribunal_alias}/_search"

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro ao acessar DataJud: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro do DataJud: {resp.text}",
        )

    data = resp.json()
    hits = data.get("hits", {}).get("hits", []) or []

    processos_simplificados = [simplificar_processo(h.get("_source", {})) for h in hits]

    total = data.get("hits", {}).get("total", {}).get("value", len(processos_simplificados))

    return DatajudSearchResponse(
        total=total,
        processos=processos_simplificados,
    )
