Quero que você construa uma ferramenta local simples para eu analisar podcasts longos do YouTube usando Gemini.

Objetivo:
Eu quero criar tópicos de pesquisa, adicionar links de podcasts do YouTube dentro desses tópicos e extrair automaticamente dores, gargalos, reclamações e problemas mencionados nas conversas.

Não é um SaaS.
Não precisa de autenticação.
Não precisa de login.
Não precisa de deploy.
Não precisa ser bonito.
Não precisa ser robusto demais.
Faça da forma mais simples possível para rodar localmente.

Stack, bibliotecas, persistência local, fila e UI ficam à sua escolha. Escolha o caminho mais simples e funcional.

Fluxo principal:

1. Eu crio um tópico com título.
   Exemplos:

* Mercado editorial
* Clínicas veterinárias
* Restaurantes

2. Dentro de um tópico, eu colo um ou vários links do YouTube.

3. Cada link entra em uma fila assíncrona de processamento.

4. Para cada vídeo:

* primeiro tente enviar a URL diretamente para o Gemini;
* se falhar, tente obter a transcrição/legendas e enviar a transcrição para o Gemini;
* se também falhar, mostre o vídeo como “aguardando transcrição manual”.

5. Quando um vídeo estiver aguardando transcrição manual:

* mostre um textarea para eu colar a transcrição;
* botão para processar essa transcrição;
* botão para ignorar o vídeo.

6. Eu preciso poder excluir links enviados.
   Se eu excluir um vídeo já processado, remova também as dores dele do ranking.

O que extrair de cada vídeo:

Extraia evidências reais da conversa, não resumo genérico.

Para cada dor/problema/gargalo mencionado, extraia:

* título curto da dor
* resumo da dor
* categoria
* área do processo/negócio
* timestamp/minutagem
* link do YouTube já com timestamp
* frase falada ou paráfrase próxima
* contexto de quem falou, se possível
* quem sofre essa dor
* impacto no negócio/processo
* severidade de 1 a 5
* confiança: low, medium ou high
* possível oportunidade de produto/software, separada da evidência original

Importante:

* Não invente frase.
* Não invente timestamp.
* Não invente speaker.
* Se não tiver certeza, marque baixa confiança.
* Pode extrair dores de negócio, processo, marketing, vendas, operação, distribuição, financeiro, relacionamento, produção, atendimento, etc.
* Não limite apenas a problemas de software.

Ranking global dentro do tópico:

Depois que os vídeos forem processados, agrupe dores parecidas.

Na home do tópico, quero ver uma lista rankeada de dores recorrentes.

Cada item do ranking deve mostrar:

* título da dor
* categoria
* quantidade de vídeos onde apareceu
* quantidade total de menções
* severidade média
* resumo
* melhor frase de evidência

A ordenação deve priorizar:

1. quantidade de vídeos diferentes onde a dor apareceu;
2. quantidade total de menções;
3. severidade;
4. confiança.

Quando eu clicar em uma dor do ranking, quero ver todas as menções relacionadas:

* vídeo
* timestamp
* link para abrir o YouTube naquela minutagem
* frase/paráfrase
* contexto
* severidade
* confiança

Telas mínimas:

1. Lista de tópicos

* criar tópico
* editar título
* deletar tópico

2. Página do tópico

* campo para adicionar links do YouTube
* lista de vídeos adicionados com status
* ranking global de dores

3. Detalhe do vídeo

* dores extraídas daquele vídeo
* timestamps e links

4. Detalhe da dor

* todas as menções agrupadas daquela dor

Status dos vídeos:

* queued
* processing
* waiting_manual_transcript
* completed
* ignored
* failed

Gemini:

* Use GEMINI_API_KEY via variável de ambiente.
* Use GEMINI_MODEL via variável de ambiente.
* Modelo padrão: gemini-2.5-flash-lite.
* Mantenha os prompts objetivos para economizar tokens.
* A resposta do Gemini deve vir em JSON estruturado.

Prompt de extração para o Gemini:
Crie um prompt interno que peça para o Gemini extrair dores, gargalos, reclamações e problemas concretos da conversa, com timestamp, frase/paráfrase, categoria, impacto e possível oportunidade de produto. Não pedir resumo do episódio.

Prompt de agrupamento:
Crie um prompt interno simples para comparar novas dores extraídas com dores já existentes no tópico e agrupar apenas quando forem realmente parecidas. Não agrupe dores diferentes só porque parecem relacionadas. Preserve todas as menções originais.

Critérios de pronto:

* Consigo criar tópicos.
* Consigo adicionar vários links do YouTube.
* Os links entram em fila assíncrona.
* O sistema tenta Gemini com URL.
* Se falhar, tenta transcrição.
* Se falhar, pede transcrição manual ou permite ignorar.
* Consigo excluir vídeos.
* Consigo ver dores por vídeo.
* Consigo ver ranking global de dores por tópico.
* Consigo clicar numa dor e ver todas as menções com timestamp.
* Tudo roda localmente.
* Sem autenticação.

Antes de implementar:

1. Olhe rapidamente a pasta atual.
2. Escolha a solução mais simples.
3. Implemente.
4. No final, me diga apenas:

   * como rodar;
   * quais env vars preciso configurar;
   * onde os dados ficam salvos;
   * limitações conhecidas.
