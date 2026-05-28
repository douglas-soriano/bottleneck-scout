import os
import json
import logging
from google import genai
from google.genai import types

log = logging.getLogger(__name__)

def _build_extraction_prompt(topic_title: str) -> str:
    market = topic_title.strip() if topic_title.strip() else "o mercado analisado"
    return f"""Você é um analista especializado em pesquisa de mercado.

Mercado sendo analisado: {market}

Analise este podcast e extraia SOMENTE sinais relevantes sobre o mercado de {market}.

Extraia apenas situações que revelem:
- Gargalos operacionais ou de processo
- Processos manuais, lentos ou ineficientes
- Dores recorrentes de quem atua no setor
- Dificuldades comerciais, de distribuição, vendas ou marketing
- Problemas de produção, atendimento ou relacionamento com clientes
- Custos elevados, atrasos, retrabalho ou desperdício
- Obstáculos para crescer, escalar ou tomar decisões
- Limitações estruturais do mercado

NÃO extraia:
- Reclamações pessoais sem relação com o mercado de {market}
- Piadas, opiniões soltas ou comentários de passagem
- Frases que parecem interessantes mas não revelam um problema concreto
- Resumo ou contexto geral do episódio

Prefira poucos itens com alta evidência a muitos itens fracos.

Para cada item, retorne um objeto JSON com:
- "title": título curto da dor (máximo 10 palavras)
- "summary": resumo objetivo do problema
- "category": categoria — operacional, financeiro, marketing, vendas, atendimento, produção, tecnologia, RH, distribuição, relacionamento, ou outra
- "area": área do processo ou negócio afetada
- "timestamp_seconds": número inteiro em segundos onde é mencionado (ou null)
- "quote": frase falada ou paráfrase próxima do que foi dito (NÃO invente)
- "speaker_context": quem falou, se identificável (ou null)
- "who_suffers": quem sofre essa dor no contexto de {market}
- "business_impact": impacto no negócio ou processo
- "severity": número de 1 a 5 (5 = mais grave)
- "confidence": "low", "medium" ou "high" — certeza sobre a evidência
- "opportunity": possível oportunidade de produto ou solução (separada da evidência)

NÃO invente frases, timestamps ou speakers. Se não tiver certeza, use confidence "low".

Retorne APENAS um JSON array válido, sem texto adicional, sem blocos de código markdown."""

CLUSTER_PROMPT = """Compare esta nova dor com os clusters existentes.

Nova dor:
- Título: {title}
- Resumo: {summary}
- Categoria: {category}

Clusters existentes:
{clusters}

Agrupe APENAS se forem realmente a mesma dor ou muito similares. Não agrupe dores apenas relacionadas ou do mesmo tema.

Retorne APENAS este JSON (sem texto extra): {{"cluster_id": <id_inteiro_ou_null>, "confidence": "low|medium|high"}}"""


def _client():
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _model():
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")


def _parse_json(text: str) -> list | dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def extract_pains_from_url(url: str, topic_title: str = "") -> list[dict]:
    client = _client()
    response = client.models.generate_content(
        model=_model(),
        contents=[
            types.Content(parts=[
                types.Part(file_data=types.FileData(file_uri=url)),
                types.Part(text=_build_extraction_prompt(topic_title)),
            ])
        ]
    )
    result = _parse_json(response.text)
    if isinstance(result, list):
        return result
    return []


def extract_pains_from_transcript(transcript: str, video_url: str = "", topic_title: str = "") -> list[dict]:
    client = _client()
    base_prompt = _build_extraction_prompt(topic_title)
    prompt = f"{base_prompt}\n\nTranscrição do vídeo{' (' + video_url + ')' if video_url else ''}:\n\n{transcript[:60000]}"
    response = client.models.generate_content(model=_model(), contents=prompt)
    result = _parse_json(response.text)
    if isinstance(result, list):
        return result
    return []


def find_cluster(pain: dict, clusters: list[dict]) -> int | None:
    if not clusters:
        return None

    clusters_text = "\n".join(
        f"- ID {c['id']}: {c['title']} | {(c.get('summary') or '')[:80]}"
        for c in clusters
    )

    prompt = CLUSTER_PROMPT.format(
        title=pain.get("title", ""),
        summary=pain.get("summary", ""),
        category=pain.get("category", ""),
        clusters=clusters_text
    )

    try:
        client = _client()
        response = client.models.generate_content(model=_model(), contents=prompt)
        data = _parse_json(response.text)
        cid = data.get("cluster_id")
        if cid is not None:
            return int(cid)
    except Exception as e:
        log.warning("Failed to parse cluster response: %s", e)

    return None
