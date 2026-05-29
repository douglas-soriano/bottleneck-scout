# Revisão Técnica - Business Bottlenecks Finder

> Revisão de engenharia (Staff level) do projeto local antes de publicação em GitHub público.
> Escopo avaliado: `app.py`, `worker.py`, `db.py`, `gemini_client.py`, `templates/`, configs e git.

---

## Veredito

**QUASE PRONTO, MAS PRECISA DE AJUSTES**

O projeto está acima da média de "vibe coding": responsabilidades razoavelmente separadas (web / worker / db / LLM), schema SQL coerente com chaves estrangeiras e cascade, prompts centralizados e templates limpos (Jinja com autoescape, sem `| safe`, sem XSS). Para uma ferramenta local, a base é sólida e legível.

O que impede o selo de "pronto" é um conjunto pequeno mas relevante de itens que um entrevistador técnico nota em segundos:

1. **Bug de idempotência no retry/reprocessamento** que gera dores e clusters duplicados.
2. **Código morto que contradiz o fluxo documentado** (`extract_pains_from_url` nunca é chamado.
3. **Chamada síncrona ao Gemini dentro de um request HTTP** (`submit_transcript`), inconsistente com a fila assíncrona do resto do sistema.
4. **Zero testes**, incluindo nas partes determinísticas e fáceis de testar (parsing, ranking, extração de ID).
5. **Acoplamento total ao YouTube** no schema e na lógica, o que torna TikTok/Reddit uma cirurgia, não uma extensão.

Nenhum desses é grave isoladamente, mas juntos passam a impressão de protótipo não finalizado. Corrigir os itens "Obrigatórios" abaixo (≈ meio dia de trabalho) leva o projeto a "pronto".

---

## Principais problemas encontrados

### 1. Retry/reprocessamento duplica dores e clusters (severidade: alta)
**O que está errado:** `retry_video` apenas seta `status="queued"`. Quando o worker reprocessa, `save_pains` insere novas linhas em `pains` e cria novos `pain_clusters` sem remover as dores antigas daquele vídeo. Um vídeo processado 2x conta em dobro no ranking. O mesmo vale para reenvio de transcrição manual.
**Por que prejudica:** ranking é o produto final do sistema; contagens duplicadas o tornam não confiável. É exatamente o tipo de bug que um revisor procura ao avaliar maturidade de pipeline.
**Como corrigir:** antes de reprocessar (no início de `process_video` e em `submit_transcript`), apagar as dores existentes do vídeo: `DELETE FROM pains WHERE video_id = ?`. O trigger `cleanup_empty_clusters` já remove clusters órfãos. Reprocessar deve ser idempotente por `video_id`.

### 2. Código morto contradiz o fluxo documentado (severidade: alta para percepção)
**O que está errado:** `extract_pains_from_url` implementa o passo 1, mas **nunca é chamado** - `process_video` vai direto para transcrição. Há código não usado e uma divergência entre a doc de intenção e o comportamento real.
**Por que prejudica:** revisor lê `goal.md` (removido, pois era goal apenas inicial, não se aplica mais), lê o worker, e vê que o fluxo descrito não existe. Sinaliza "implementação inacabada" ou "doc desatualizada".
**Como corrigir:** decidir explicitamente um dos dois caminhos: (a) remover `extract_pains_from_url`.

### 3. Gemini chamado de forma síncrona no handler HTTP (severidade: média)
**O que está errado:** `POST /videos/{id}/transcript` chama `extract_pains_from_transcript` + `find_clusters_batch` dentro do request. Duas chamadas de LLM bloqueiam a resposta por dezenas de segundos, e o `try/except` engole a exceção mas deixa a UX travada. O resto do sistema usa fila; só esse caminho não.
**Por que prejudica:** inconsistência arquitetural óbvia. Mostra que a fila foi feita "para o caminho feliz" e o manual foi colado depois.
**Como corrigir:** o handler deve apenas salvar a transcrição e enfileirar (`status="queued"`), deixando o worker processar. Unifica os dois caminhos em um só.

### 4. Ausência total de testes (severidade: média)
**O que está errado:** não há diretório de testes nem um único teste. Há lógica pura e determinística fácil de cobrir.
**Por que prejudica:** "parece profissional" depende fortemente de existir ao menos uma suíte mínima. Zero testes em código com parsing de JSON de LLM e ordenação de ranking é bandeira vermelha.
**Como corrigir:** ver seção de testabilidade. Foco em `extract_youtube_id`, `_parse_json`, `yt_link_with_ts` e a query de ranking com um SQLite em memória + stub do cliente Gemini. ~6–10 testes resolvem.

### 5. Acoplamento ao YouTube bloqueia evolução (severidade: média, dado o objetivo declarado)
**O que está errado:** `videos.youtube_id`, `youtube_link`, `extract_youtube_id`, `yt_link_with_ts`, headers e parsing de transcript são todos YouTube-específicos e espalhados entre `app.py` e `worker.py` (regex `YT_PATTERN` está duplicada nos dois arquivos).
**Por que prejudica:** o objetivo declarado é adicionar TikTok e Reddit. Hoje isso exige tocar schema, worker e rotas. Não é "extensão", é reescrita parcial.
**Como corrigir:** ver "Arquitetura recomendada". Generalizar para `source` + `external_id` + `source_url` e introduzir uma abstração mínima de provider. Não precisa de plugin system - só uma interface e um dicionário de registro.

### 6. `_parse_json` frágil (severidade: baixa-média)
**O que está errado:** o parsing depende de o modelo devolver JSON limpo ou cercado por ``` ```. Qualquer prosa extra quebra `json.loads` e derruba o vídeo para `failed`.
**Por que prejudica:** robustez de pipeline de LLM é justamente o que se avalia aqui.
**Como corrigir:** usar `response_mime_type="application/json"` (e idealmente `response_schema`) na config do `google-genai`, eliminando a heurística de strip de markdown. Mantém o fallback como rede de segurança.

### 7. Sem retry/backoff em chamadas de LLM (severidade: baixa)
**O que está errado:** qualquer erro transitório do Gemini (rate limit, 5xx) marca o vídeo como `failed` imediatamente; só um retry manual recupera.
**Como corrigir:** um retry simples com backoff exponencial (2–3 tentativas) em torno das chamadas de `generate_content`. Sem bibliotecas pesadas.

### 8. Duplicações e deprecations menores (severidade: baixa)
- `YT_PATTERN` e `extract_youtube_id` duplicados em `app.py` e `worker.py` → mover para um único módulo.
- `@app.on_event("startup")` está deprecado no FastAPI → migrar para `lifespan`.
- `datetime.datetime.utcnow()` deprecado no Python 3.12+ → `datetime.now(datetime.UTC)`.
- `imports` locais dentro de funções (`import datetime`, `from youtube_transcript_api import ...`) sem motivo claro → subir para o topo.

### 9. Falta de observabilidade (severidade: baixa)
- Todo o flow precisa ter logs claros e úteis em pontos essenciais. Sugiro integração com LangSmith para cálculo exato de custos e chamadas.
- O projeto deverá ser facilmente trocado de pt-BR para en-US via env, e esse idioma deve ser passado como resultado final das análises. As prompts deverão ser em ingles.

---

## Decisões arquiteturais que precisam ser tomadas

2. **Modelo de fontes (YouTube/TikTok/Reddit/fóruns).** Adotar `source` (enum textual) + `external_id` + `source_url` em `videos` (renomear para `items`/`sources` é opcional). Definir o contrato de provider antes de adicionar o segundo canal.
5. **Versionamento de prompts.** Para projeto local: extrair os prompts para `prompts/extraction.md` e `prompts/clustering.md` (ou um módulo `prompts.py` com constantes) e versioná-los no git. Suficiente; não precisa de registry.
6. **Concorrência do worker.** Hoje o worker é uma thread dentro do processo web. Decidir e documentar: rodar **um único** processo uvicorn (sem `--workers >1` e sem `--reload` em uso real), senão múltiplos workers processam a mesma fila e duplicam trabalho. Alternativa simples: rodar o worker como processo separado (`python worker.py`).

---

## Refatorações recomendadas antes de publicar

- Corrigir idempotência do retry/reprocessamento (problema #1).
- Resolver o código morto / divergência de fluxo (problema #2).
- Unificar o caminho manual na fila (problema #3).
- Adicionar suíte mínima de testes (problema #4).
- Rotacionar a chave Gemini e confirmar que `.env` segue ignorada (ver checklist).
- `response_mime_type="application/json"` no cliente Gemini (problema #6).
- Generalizar schema/lógica para múltiplas fontes (problema #5) - pelo menos a nomenclatura, mesmo que só YouTube exista hoje.
- Dedup de `YT_PATTERN`/`extract_youtube_id` e mover prompts para arquivos.
- Retry com backoff (problema #7).
- Migrar `on_event` → `lifespan` e `utcnow` → timezone-aware.
- Documentar concorrência do worker / separar em processo próprio.

---

## Arquitetura recomendada

Mantendo local-first e simples, sem microserviços nem filas externas. A mudança maior é introduzir uma fina camada de "provider" e generalizar a fonte.

### Estrutura de pastas sugerida
```
.
├── app.py                  # rotas FastAPI (fino, só HTTP)
├── worker.py               # loop da fila + orquestração da pipeline
├── db.py                   # acesso a dados (já está bom)
├── pipeline/
│   ├── extractor.py        # extração de dores via Gemini (ex-gemini_client)
│   └── clustering.py       # agrupamento via Gemini
├── sources/
│   ├── base.py             # interface SourceProvider
│   └── youtube.py          # implementação YouTube (transcript + título + link)
├── prompts/
│   ├── extraction.md
│   └── clustering.md
├── templates/
└── tests/
```

### Schema (generalização mínima)
- Renomear conceitualmente `youtube_id` → `external_id`, `youtube_link` → `source_link`, e adicionar `source TEXT NOT NULL DEFAULT 'youtube'`.
- Reddit não tem "transcript" mas tem corpo do post + comentários: cabe no mesmo campo `transcript`/`content`. O extractor é agnóstico ao texto.

### Fluxo da pipeline (alvo)
```
add item → status=queued
  worker pega queued (1 worker)
    → resolve provider por URL
    → fetch_title
    → fetch_transcript  (None → waiting_manual_transcript, fim)
    → DELETE pains do item   (idempotência)
    → extractor → lista de dores
    → clustering (batch) contra clusters do tópico
    → insert pains + clusters
    → status=completed
manual submit → salva transcript → status=queued  (mesmo caminho acima)
retry → status=queued
```

### Onde colocar cada coisa
- **Prompts:** arquivos em `prompts/` carregados no boot (versionáveis, diffáveis).
- **Jobs/queue:** continuar com a tabela `videos`/`items` como fila + 1 thread/processo worker. Não introduzir Celery/Redis para uso local.
- **Estados intermediários:** já persistidos (`status`, `transcript`, `error_msg`, `processed_at`). Manter. A coluna `transcript` é o principal artefato intermediário e evita re-fetch.

---

### Sobre Tiktok e Reddit

- A ideia é aceitar links do tiktok também, extrair transcription (se possível), e analisar junto.
- Reddit é um grande forum com opiniões e reclamações, então a ideia é para cada item do nosso ranking final de pain points, ter um botão que busca no reddit topicos e comentários sobre essa reclamação, junta tudo, e a LLM analisa pontos positivos, negativos, com finalidade de "provar" se esse pain point é relatado por usuários lá.