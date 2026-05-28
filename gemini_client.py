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

Analise este podcast e extraia SOMENTE sinais de gargalo, dor ou ineficiência do mercado de {market}.

CRITÉRIO DE INCLUSÃO — inclua apenas se passar por ao menos 1 destes testes:
- Revela processo manual, lento ou feito "na mão"
- Revela gargalo operacional claro
- Revela dificuldade de venda, marketing, distribuição ou aquisição
- Revela custo alto ou inesperado
- Revela perda de tempo recorrente
- Revela retrabalho ou erro que precisa ser corrigido
- Revela decisão tomada com pouca informação ou às cegas
- Revela dificuldade de crescer ou escalar
- Revela risco financeiro ou comercial concreto
- Revela coordenação difícil entre partes do mercado (autores, editoras, livrarias, fornecedores, leitores, canais, etc.)
- Revela algo que alguém do mercado precisaria resolver para ganhar mais dinheiro, economizar tempo, reduzir risco ou operar melhor

IGNORE — não extraia:
- Histórias pessoais sem consequência clara para o mercado
- Frases inspiracionais ou motivacionais
- Comentários culturais ou literários genéricos
- Observações de carreira ou trajetória pessoal
- Opiniões sem impacto comercial ou processual
- Curiosidades, anedotas ou contexto histórico
- Qualquer coisa que não responda: "qual processo ou resultado de negócio isso afeta?"

Prefira 5 itens excelentes a 20 itens mediocres.

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
- "severity": número de 1 a 5 (5 = mais grave para o mercado)
- "confidence": "low", "medium" ou "high" — certeza sobre a evidência
- "opportunity": possível oportunidade de produto ou solução (separada da evidência)
- "commercial_actionability": número de 1 a 5 seguindo esta escala:
    1 = curioso, mas pouco acionável
    2 = problema real mas vago, sem dono claro
    3 = problema real, impacto identificável, mas amplo
    4 = gargalo concreto com dono e impacto razoavelmente claro
    5 = gargalo concreto, dono claro, impacto financeiro/operacional claro e consequência real se não resolvido

NÃO invente frases, timestamps ou speakers. Se não tiver certeza, use confidence "low".

Retorne APENAS um JSON array válido, sem texto adicional, sem blocos de código markdown."""


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


def find_clusters_batch(pains: list[dict], clusters: list[dict]) -> list[int | None]:
    """Single Gemini call to assign all pains to existing clusters.
    Returns a list of cluster_id (int) or None, one per pain, in the same order."""
    if not clusters or not pains:
        return [None] * len(pains)

    pains_text = "\n".join(
        f"{i}. {p.get('title', '')} — {(p.get('summary') or '')[:80]}"
        for i, p in enumerate(pains)
    )
    clusters_text = "\n".join(
        f"ID {c['id']}: {c['title']} — {(c.get('summary') or '')[:80]}"
        for c in clusters
    )

    prompt = f"""Compare cada nova dor com os clusters existentes.

Novas dores ({len(pains)} itens, indexados de 0):
{pains_text}

Clusters existentes:
{clusters_text}

Para cada nova dor, retorne o cluster_id do cluster existente se for realmente a mesma dor (ou muito similar), ou null se for diferente.

Retorne APENAS um JSON array com exatamente {len(pains)} elementos, na mesma ordem das novas dores:
[cluster_id_ou_null, ...]

Exemplo para 3 dores: [42, null, 17]

Agrupe APENAS dores realmente iguais ou muito similares. Não agrupe dores só por serem relacionadas."""

    try:
        client = _client()
        response = client.models.generate_content(model=_model(), contents=prompt)
        data = _parse_json(response.text)
        if isinstance(data, list):
            result = []
            for item in data[:len(pains)]:
                try:
                    result.append(int(item) if item is not None else None)
                except (TypeError, ValueError):
                    result.append(None)
            while len(result) < len(pains):
                result.append(None)
            return result
    except Exception as e:
        log.warning("Batch cluster failed: %s", e)

    return [None] * len(pains)
