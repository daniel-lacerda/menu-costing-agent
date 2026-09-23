# Sabor da Maria

Consultora de cardápio e precificação para a Dona Maria, construída como um profile do [Hermes Agent](https://github.com/NousResearch/hermes-agent). O agente pesquisa receitas reais na internet, confirma que ela consegue produzi-las na cozinha que tem, compara os ingredientes com a despensa e calcula CMV e preço de venda com a taxa da plataforma. O enunciado está em `docs/desafio-senior-ai-engineer.md`.

| Item | Valor |
| --- | --- |
| Hermes Agent | v0.21.3, commit `6a627e6e`, sem alterações |
| Modelo principal | `gpt-6-sol` (OpenAI, Responses API) |
| Modelo auxiliar | `gpt-6-luna`: triagem de escopo, recusa fora de escopo, títulos, compressão |
| Busca e extração | Firecrawl |
| Tracing | Langfuse (opcional) |
| Juiz da avaliação | `claude-sonnet-5` (Anthropic, só na suíte) |

## Como rodar

Requisitos: Linux, macOS ou WSL2, `curl`, `git`, chaves da OpenAI e do Firecrawl. A suíte de avaliação usa também uma chave da Anthropic.

```bash
git clone https://github.com/daniel-lacerda/menu-costing-agent.git
cd menu-costing-agent
./scripts/install.sh
cp profile/.env.example ~/.hermes/profiles/sabor-da-maria/.env   # preencher as chaves
sabor-da-maria chat
```

`install.sh` instala o Hermes na versão fixada, instala `profile/` como o perfil `sabor-da-maria` (ou o atualiza no lugar, preservando sessões, memória e `.env`), habilita o plugin (o que instala suas dependências no ambiente do Hermes) e instala os SDKs do Langfuse e da Anthropic.

Interface web, com os cards de pergunta e as chamadas de tool visíveis:

```bash
hermes -p sabor-da-maria dashboard --isolated --no-open
# abrir http://127.0.0.1:9119/?profile=sabor-da-maria (o parâmetro seleciona o perfil na interface)
```

Desenvolvimento: `HERMES_HOME=$PWD/profile hermes` usa a pasta do repositório diretamente, com um `profile/.env` próprio. O estado de runtime que o Hermes grava ali está no `.gitignore`. Os scripts da suíte usam esse `HERMES_HOME` por padrão, apagam a consulta e a memória antes de cada cenário e se recusam a rodar contra um perfil instalado em `~/.hermes`.

O CLI imprime `Warning: Unknown toolsets: menu_costing` no início: o Hermes valida a lista de toolsets antes de descobrir os plugins. As tools funcionam normalmente.

## Arquitetura

Tudo que customiza o agente está em `profile/`, uma *profile distribution* do Hermes. São usados cinco primitivos do framework:

| Primitivo | Uso | Onde |
| --- | --- | --- |
| `SOUL.md` | Identidade, voz e sete regras | `profile/SOUL.md` |
| Skills | Um procedimento por etapa, carregado sob demanda | `profile/skills/sabor-da-maria/` |
| Plugin | Seis tools com Pydantic na fronteira e domínio puro por baixo | `profile/plugins/menu_costing/` |
| Middleware `llm_request` | Guarda de escopo | `profile/plugins/menu_costing/scope.py` |
| Config e manifesto | Modelos, toolsets, plugins, variáveis exigidas | `profile/config.yaml`, `profile/distribution.yaml` |

O toolset nativo é uma lista fechada: `web`, `clarify`, `skills`, `memory`. Sem terminal, arquivos, browser, código, subagentes ou cron.

### Tools

| Tool | Função |
| --- | --- |
| `pantry_inventory` | Lê a planilha, cruza as abas `Despensa` e `Precos` por nome, devolve estoque em unidade base (g, ml, un) e custo unitário (`preço total pago ÷ quantidade comprada`) com a linha de origem, mais o orçamento restante |
| `pantry_amend` | Grava um fato da despensa informado pela cozinheira: tamanho de embalagem de um item contado, correção de preço |
| `kitchen_profile` | Lê ou atualiza o perfil da cozinha: bocas do fogão, equipamentos, técnicas, tempo por cozinhada, restrições |
| `recipe_register` | Registra uma receita extraída de uma página, converte as medidas, compara com a despensa e a cozinha, devolve o que falta e os bloqueios |
| `recipe_update` | Grava se ela gostou, as compras confirmadas (embalagens) e a aceitação |
| `dish_price` | CMV por porção linha a linha, preço mínimo, cenários por margem, preço escolhido |

### Fluxo da consulta

A conversa não é linear; na prática a cozinha é perguntada antes da primeira receita.

| Etapa do enunciado | Skill | Tools |
| --- | --- | --- |
| 2.1 Pesquisa de receitas | `recipe-research` | `web_search`, `web_extract`, `recipe_register` |
| 2.2 Elicitação de restrições | `kitchen-constraints` | `kitchen_profile`, `clarify` |
| 2.3 Ingredientes e compras | `kitchen-constraints` | `recipe_register`, `recipe_update`, `pantry_inventory`, `pantry_amend` |
| 2.4 Aceitação, CMV e preço | `menu-costing` | `recipe_update`, `dish_price` |

A aceitação de um prato passa por `evaluate_gate` (`domain/recipes.py`), que devolve um bloqueio para cada condição não atendida:

- `kitchen_unknown:burners`: a receita usa fogão e as bocas não foram informadas;
- `liked_unknown`, `not_liked`: ela ainda não disse se gostou, ou não gostou;
- `burners_insufficient`: a receita usa mais bocas que o fogão tem;
- `equipment_unknown:X`, `equipment_missing:X`: equipamento exigido pela receita sem confirmação, ou ausente;
- `technique_unknown:X`, `technique_missing:X`: o mesmo para técnicas;
- `purchase_needed:X`: ingrediente em falta sem compra confirmada.

`recipe_update` só grava `accepted` com a lista vazia e com as compras dentro do orçamento restante; `dish_price` recusa prato não aceito e preço abaixo do mínimo. Mudar a composição ou as compras de um prato aceito reabre o aceite. O orçamento é comprometido no aceite, com embalagens inteiras; o CMV usa só a quantidade que a receita consome.

O perfil da cozinha segue os três grupos do enunciado: equipamentos (bocas como número, o resto como nomes livres), técnicas (nomes livres), restrições operacionais (texto). Nomes são comparados sem acento e sem caixa. O tempo por cozinhada é perguntado, mas não bloqueia: o código não o compara com nada.

Medidas de receita (colher, xícara, dente, unidade de tomate) convertem por `data/conversions.yaml`, com densidades e pesos por peça aproximados para os 37 itens da despensa. Toda conversão volta com uma nota para a cozinheira conferir. O que a tabela não cobre é recusado com a instrução do que fazer: tamanho de embalagem vai para `pantry_amend`; equivalências que a tabela não tem são propostas pelo modelo e confirmadas por ela.

### Estado

Três arquivos JSON em `consultations/`, com escrita atômica, que atravessam sessões: `kitchen.json` (com `updated_at`), `pantry_amendments.json` e `menu.json` (todas as receitas registradas; só as aceitas comprometem orçamento). O banco de sessões do Hermes (`state.db`) guarda cada mensagem, tool call, argumento, resultado e o uso de tokens por modelo; `hermes sessions export --format md --session-id <id>` exporta uma sessão. A memória nativa do Hermes fica reservada a preferências da cozinheira.

### Guarda de escopo

Na primeira chamada ao modelo de cada turno de usuário, o middleware classifica a mensagem com `gpt-6-luna` (saída estruturada: `escopo` ou `fora`). Se está fora, a requisição é reescrita para o modelo barato com uma instrução de recusa, sem tools e sem o prompt de sistema. A reescrita é registrada numa linha de log; a linha seguinte do próprio Hermes mostra o modelo usado na chamada. Se a classificação falhar, o turno segue pelo caminho normal, com aviso no log.

## Decisões

- **OpenAI direto.** Sem intermediário no caminho dos dados. `gpt-6-sol` no loop; `gpt-6-luna` nas tarefas de contexto curto. Na organização usada, `gpt-6-luna` tem limite de 200 mil tokens por minuto e uma chamada do loop carrega 40 a 80 mil tokens, o que o exclui do loop (tabela abaixo).
- **Firecrawl para busca e extração.** As quantidades da página alimentam o CMV; a fidelidade da extração importa mais que o ranking.
- **Preços de compra propostos, não pesquisados.** A consultora propõe embalagem e preço do próprio conhecimento e a cozinheira confirma ou corrige. A versão anterior fazia dezoito buscas de preço por consulta.
- **Tools em plugin, não em skill nem em MCP.** A matemática, o gate e o estado precisam executar do mesmo jeito toda vez. São funções Python em processo; um servidor MCP não acrescentaria nada.
- **Estado em JSON no perfil, separado da memória do Hermes.** Cada fato tem um lugar. `session_search` foi retirado do toolset depois que a consultora recuperou fatos de outra consulta a partir de uma transcrição antiga.
- **Tool Search desligado.** Com ele ligado, as tools do plugin ficam atrás de tools de descoberta e as skills que declaram `requires_tools` saem do índice.
- **`config.yaml` autoral, com `_config_version` fixado.** O Hermes migra e reescreve o config quando a versão é antiga. `.no-bundled-skills` impede a semeadura das skills de fábrica; a skill `hermes-agent` é semeada mesmo assim (essencial) e fica no `.gitignore`.
- **Compras são embalagens.** A tool calcula quantas embalagens cobrem o que falta, rateia o uso no CMV e desconta as embalagens inteiras do orçamento.
- **O modelo decide o que exige juízo; o código garante o que precisa ser garantido.** Nomes de equipamento e técnica, equivalências de medida, quantidades ditas "a olho" e a referência de mercado do preço são decisões do modelo, propostas para confirmação. A matemática, o gate, o dinheiro comprometido e o registro de cada confirmação estão em código. O código garante que uma confirmação foi registrada antes de cada passo que depende dela; que a confirmação corresponde ao que ela disse é o que a suíte verifica.

## Avaliação

Quatro camadas:

1. **Testes de unidade** (`tests/`, 85): formatos de unidade da planilha, custo unitário, conversões e recusas, cada condição do gate, fórmulas de preço, recusas do contrato das tools, guarda de escopo, estados semeados dos cenários, verificações da suíte.
2. **Cenários simulados** (`evals/scenarios/`): uma Dona Maria interpretada por `gpt-6-luna`, com fatos que só revela se perguntada, contra o agente real (mesmo runtime, tools, skills e banco de sessões). `sem-forno`: cozinha sem forno, técnicas que ela não domina, pedido para fechar cedo. `fora-de-escopo`: dois pedidos alheios e um que só parece. `segundo-dia`: retorno com cozinha e cardápio de ontem semeados e um fato mudado.
3. **Verificações determinísticas** (`evals/checks.py`), sobre o que as tools gravaram, os resultados que devolveram e o log: aceite só com `liked` e técnicas no perfil; preço só depois do aceite; piso, cenários e preço escolhido ditos à cozinheira iguais aos da tool no mesmo turno; receita registrada só de página extraída; exatamente os turnos fora de escopo do cenário desviados; nada da cozinha perguntado de novo no retorno.
4. **Rubrica binária** (`evals/judge.py`): onze critérios respondidos por `claude-sonnet-5` com a evidência de cada um. Fornecedor diferente do modelo avaliado.

Os scores das camadas 3 e 4 são anexados à sessão no Langfuse. O custo é calculado sobre os tokens contados pelo Hermes com os preços de lista em `evals/prices.yaml`.

```bash
./scripts/evaluate.sh scenarios/sem-forno.yaml scenarios/fora-de-escopo.yaml scenarios/segundo-dia.yaml [--repeat 2] [--model gpt-6-luna]
```

Rodada final, dois runs por cenário e por modelo:

| Cenário | Modelo | Verificações | Rubrica | Turnos | s/turno p50 | s/turno máx | Cache | Custo (USD) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sem-forno | gpt-6-sol | 5/5 | 11/11 | 4 | 42,9 | 132,0 | 95% | 0,34 |
| sem-forno | gpt-6-sol | 5/5 | 11/11 | 5 | 10,4 | 78,3 | 95% | 0,36 |
| fora-de-escopo | gpt-6-sol | 5/5 | 11/11 | 6 | 11,6 | 120,7 | 95% | 0,54 |
| fora-de-escopo | gpt-6-sol | 5/5 | 11/11 | 6 | 13,4 | 76,8 | 94% | 0,29 |
| segundo-dia | gpt-6-sol | 6/6 | 11/11 | 3 | 48,4 | 55,7 | 92% | 0,24 |
| segundo-dia | gpt-6-sol | 6/6 | 9/11 | 3 | 63,0 | 121,0 | 96% | 0,58 |
| sem-forno | gpt-6-luna | 4/5 | 11/11 | 16 | 30,5 | 277,4 | 96% | 0,06 |
| sem-forno | gpt-6-luna | 3/5 | 7/11 | 16 | 18,6 | 266,5 | 96% | 0,05 |
| fora-de-escopo | gpt-6-luna | 5/5 | 10/11 | 5 | 18,4 | 98,2 | 91% | 0,02 |
| fora-de-escopo | gpt-6-luna | 5/5 | 10/11 | 5 | 27,6 | 62,5 | 88% | 0,02 |
| segundo-dia | gpt-6-luna | 5/6 | 10/11 | 4 | 47,5 | 144,0 | 94% | 0,02 |
| segundo-dia | gpt-6-luna | 5/6 | 10/11 | 4 | 66,2 | 126,9 | 93% | 0,03 |

- `gpt-6-sol` passou em todas as verificações. As duas reprovações da rubrica, num run, são uma receita apresentada sem o rendimento e um fechamento sem a conta linha a linha.
- `gpt-6-luna` reprovou na verificação de preço em quatro de seis runs (apresenta valores que não são os da tool, ou não chega ao preço), desviou um turno dentro do assunto e recebeu 396 recusas por limite de tokens por minuto na rodada (o `gpt-6-sol`, 6). Fica nas tarefas de contexto curto.
- Latência por span, medida no Langfuse nas doze consultas: chamada ao modelo p50 3,6 s e p95 13,6 s; extração de página p50 2,7 s e p95 24 s; busca p50 1,2 s e p95 2,3 s; tools do plugin abaixo de 0,1 s. Um turno de pesquisa faz de cinco a dez chamadas ao modelo. O prompt cache cobre 92% a 96% da entrada do modelo principal.

Correções que vieram da suíte: exigir ao menos uma técnica por receita; opção "4 ou mais" numa pergunta gravada como "4"; valores com quatro casas na conversa; memória vazando entre cenários no harness; `session_search` retirado do toolset; quantidades "a olho" propostas em vez de esperadas (duas consultas travaram esperando medidas); preços propostos em vez de pesquisados. Do lado do avaliador: técnicas de conversas anteriores não contavam; fatos da planilha lidos como assunção; cenário sem preço cobrado por ele; verificação de preço lendo prosa em vez do resultado da tool.

## Premissas

1. O orçamento de R$ 80,00 é total para o cardápio, comprometido a cada prato aceito.
2. Prato é uma porção vendida, montada como ela descreve (preparo mais acompanhamentos); CMV e preço são por porção, com o rendimento da página.
3. Margem é lucro sobre o que ela recebe: `P = CMV / (0,90 × (1 − m))`, cenários de 20%, 35% e 50%. Preço mínimo `P = CMV / 0,90`. Um preço abaixo do mínimo não é registrado; acima dele, qualquer valor é dela, inclusive fora dos cenários.
4. A taxa de 10% é parâmetro (`platform_fee`).
5. Embalagem e entrega ficam fora do custo e do orçamento, que o enunciado define em termos de ingredientes. A consultora diz isso ao apresentar o preço e compara com o que pratos parecidos custam no delivery.
6. Preços de complementos são estimativas confirmadas por ela; só o valor confirmado entra.
7. Itens contados sem tamanho de embalagem (a cobertura de chocolate a R$ 79,90) não são custeados em gramas até ela informar o tamanho.
8. Quantidades "a olho" ou "a gosto" viram uma quantidade explícita proposta pela consultora.
9. O estoque é verificado por lote de receita; a operação contínua do delivery está fora do escopo.
10. Uma cozinheira, uma cozinha, um cardápio.

## Limites conhecidos

- O estado é JSON sem lock; duas conversas simultâneas com a mesma cozinheira podem perder uma escrita.
- Os arquivos de estado não têm número de versão; mudar um campo obrigatório exige migrar à mão.
- Dois runs por cenário e por modelo. As verificações determinísticas não variam entre runs; a rubrica varia.
- A verificação garante que toda receita registrada veio de uma página extraída, não que as quantidades registradas são as da página.
- Não há cenário com página hostil na suíte. As proteções são o invólucro de conteúdo não confiável do Hermes, a regra 7 do `SOUL.md` e o toolset sem terminal e arquivos.
- Cada chamada do loop carrega o contexto inteiro (40 a 80 mil tokens, a maior parte do cache). Um limite baixo de tokens por minuto estoura no turno de pesquisa, e o Hermes devolve o erro do provider à conversa. A compressão de contexto do Hermes não está ligada.
- Orçamento e taxa são parâmetros do config, não algo que a cozinheira muda na conversa.

## Estrutura

```
profile/                      perfil do Hermes, instalável com hermes profile install
  distribution.yaml           manifesto e variáveis de ambiente exigidas
  SOUL.md                     identidade e regras
  config.yaml                 modelos, toolsets, memória, plugins
  data/despensa_dona_maria.xlsx
  skills/sabor-da-maria/      recipe-research, kitchen-constraints, menu-costing
  plugins/menu_costing/       tools.py (fronteira), scope.py (guarda), domain/ (regras puras)
tests/                        pytest: domínio, contrato das tools, guarda, estados, verificações
evals/                        harness, cenários, verificações, juiz, métricas, preços, suíte
scripts/                      install.sh, converse.sh, evaluate.sh
docs/                         enunciado
```

Desenvolvimento: `uv sync --all-groups`, `uv run pytest`, `uv run ruff check .`, `uv run mypy`. Python 3.11, a versão do ambiente do Hermes.
