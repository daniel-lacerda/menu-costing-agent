# Sabor da Maria

Consultora de cardápio e precificação para a Dona Maria, construída sobre o [Hermes Agent](https://github.com/NousResearch/hermes-agent). Ela acompanha a cozinheira da despensa ao cardápio de lançamento: encontra receitas reais na internet, confirma que a Dona Maria consegue produzi-las na cozinha que tem, compara os ingredientes com a despensa, e calcula o CMV e o preço de venda com a taxa da plataforma, deixando a decisão com ela.

Este repositório é uma *profile distribution* do Hermes: tudo que customiza o agente vive em `profile/` e se instala com um comando. O Hermes em si não tem uma linha alterada e fica fixado em uma versão.

| Item | Valor |
|---|---|
| Hermes Agent | v0.21.3 (2026.9.14), commit `6a627e6e` |
| Modelo principal | `gpt-5.6-terra`, OpenAI direto, Responses API |
| Modelo auxiliar | `gpt-5.6-luna` (título de sessão, compressão, triagem de escopo, recusa fora de escopo) |
| Busca e extração | Firecrawl |
| Tracing | Langfuse, opcional, SDK v4 |

## Como rodar

Pré-requisitos: Linux, macOS ou WSL2, `curl`, `git`, uma chave da OpenAI e uma do Firecrawl.

```bash
git clone https://github.com/daniel-lacerda/menu-costing-agent.git
cd menu-costing-agent
./scripts/install.sh
cp profile/.env.example ~/.hermes/profiles/sabor-da-maria/.env   # preencha as chaves
sabor-da-maria chat        # ou: hermes -p sabor-da-maria chat
```

O script instala o Hermes na versão fixada (se ainda não existir), instala este profile como `sabor-da-maria` com um comando de atalho, habilita o plugin de custeio (o que instala `openpyxl` no ambiente do Hermes pelo mecanismo oficial de dependências de plugin) e instala o SDK do Langfuse. As chaves do Langfuse são opcionais: sem elas o plugin não faz nada.

Para conversar pelo navegador, com os cards de pergunta e as chamadas de tool visíveis:

```bash
HERMES_HOME=~/.hermes/profiles/sabor-da-maria hermes dashboard
```

Para desenvolver dentro do repositório, aponte o Hermes direto para a pasta do profile: `HERMES_HOME=$PWD/profile hermes`. O estado de runtime que o Hermes grava ali (banco de sessões, logs, caches) está no `.gitignore`.

Uma observação sobre o início de sessão: o CLI imprime `Warning: Unknown toolsets: menu_costing`. É uma ordem de inicialização do Hermes (`cli.py` valida os nomes de toolset antes de descobrir os plugins, que só carregam na primeira importação de `model_tools`). As tools funcionam normalmente; o log registra cada chamada.

## Como a consulta funciona

A conversa não é linear, mas cada etapa do enunciado tem um procedimento (uma skill) e uma tool que a torna verificável.

| Etapa do enunciado | Skill que a consultora carrega | Tools |
|---|---|---|
| 2.2 Elicitação de restrições | `kitchen-constraints` | `kitchen_profile`, `clarify` (nativa do Hermes) |
| 2.1 Pesquisa de receitas | `recipe-research` | `web_search`, `web_extract`, `recipe_register` |
| 2.3 Ingredientes e compras | `kitchen-constraints` | `recipe_register`, `recipe_update`, `pantry_inventory`, `pantry_amend` |
| 2.4 Aceitação, CMV e preço | `menu-costing` | `recipe_update`, `dish_price` |

O ponto central do enunciado, "não pode deixar ela comprar ingredientes e descobrir depois que não consegue cozinhar", é um *gate* em código, não uma instrução de prompt. `recipe_register` devolve a lista de bloqueios de uma receita (campo da cozinha desconhecido, equipamento que ela não tem, técnica não confirmada, ingrediente sem compra confirmada). `recipe_update` só grava a aceitação quando essa lista está vazia e as compras cabem no orçamento. `dish_price` recusa qualquer prato não aceito. A consultora conduz a conversa; a garantia não depende dela.

O que se vende no delivery é a porção montada. Quando a página descreve só o preparo principal, a consultora pergunta como a Dona Maria monta a marmita e registra os acompanhamentos da despensa por porção (`per_portion_items`); a tool multiplica pelo rendimento da receita.

## O que é nosso e o que é do Hermes

O Hermes fornece o runtime: o loop do agente, a montagem do prompt, a busca na web, as perguntas ao usuário, a memória, o banco de sessões, o sistema de skills, o mecanismo de plugins e middleware, e a integração com o Langfuse. Nada disso foi alterado. Nossa customização usa cinco primitivos dele.

| Primitivo do Hermes | O que colocamos nele | Onde |
|---|---|---|
| `SOUL.md` | Identidade, voz para uma cozinheira que mal usa o celular, e sete regras invioláveis | `profile/SOUL.md` |
| Skills (padrão agentskills.io) | Três procedimentos, um por etapa, carregados sob demanda com `skill_view` | `profile/skills/sabor-da-maria/` |
| Plugin com tools | Seis tools determinísticas, Pydantic na fronteira, domínio puro por baixo | `profile/plugins/menu_costing/` |
| Middleware e hook | Guarda de escopo: triagem no modelo barato e recusa sem o modelo principal | `profile/plugins/menu_costing/scope.py` |
| Configuração de profile | Modelo, auxiliares, toolsets permitidos, memória, plugins, manifesto de distribuição | `profile/config.yaml`, `profile/distribution.yaml` |

As seis tools:

1. `pantry_inventory` lê a planilha, cruza as duas abas por nome, converte cada item para unidade base (g, ml ou un) e devolve estoque e custo unitário derivado (`preço total pago ÷ quantidade comprada`), com a linha de origem.
2. `pantry_amend` registra um fato que a planilha não tem e a cozinheira informou: tamanho da embalagem de um item contado em unidades, ou correção de preço.
3. `kitchen_profile` lê ou atualiza o perfil da cozinha e devolve os campos ainda desconhecidos e a data da última atualização.
4. `recipe_register` registra uma receita extraída de uma página real, converte as medidas, compara com a despensa e a cozinha, e devolve o que ela tem, o que falta e os bloqueios.
5. `recipe_update` grava o que ela disse: se gostou, técnicas confirmadas, compras confirmadas (como embalagens) e a aceitação.
6. `dish_price` calcula o CMV por porção linha a linha, o preço mínimo e cenários por margem, e registra o preço escolhido.

## Decisões de arquitetura

**Modelo e provider.** OpenAI direto, sem intermediário no caminho dos dados. `gpt-5.6-terra` no loop da conversa, onde a consultora precisa raciocinar e lembrar restrições; `gpt-5.6-luna`, da mesma geração e dez vezes mais barato, nas tarefas mecânicas. O Hermes é agnóstico de provider (a troca é o bloco `model:` do config e uma variável no `.env`), então a escolha foi por aderência ao que a página de vaga cita e por manter um vendor só, como se faria em produção. As chamadas do modelo principal vão com `store: false`, por isso não aparecem no console de logs da OpenAI.

**Busca.** Firecrawl como backend único de busca e extração. O que importa aqui não é ranking, é fidelidade da extração: as quantidades da página alimentam o CMV. Toda receita apresentada carrega o link e o rendimento da página; a consultora não inventa receitas nem links.

**Tools em plugin, não em skill nem em MCP.** O guia do próprio Hermes diz: skill quando cabe em instruções mais tools existentes; tool quando a lógica precisa executar de forma precisa toda vez. O gate, a matemática e o estado precisam. Plugin em vez de MCP porque são funções Python em processo, e um servidor a mais não compraria nada. Plugin em vez de editar o core porque fork não se revisa.

**Estado explícito.** A cozinha (`kitchen.json`), as correções da despensa e o cardápio de lançamento (`menu.json`) ficam em JSON no profile e atravessam sessões. Uma receita registrada e abandonada não consome orçamento e fica no arquivo como histórico. A memória nativa do Hermes (`USER.md`) fica reservada a preferências duráveis da Dona Maria. Cada fato tem um lugar só. Quando ela volta em outro dia, a consultora recapitula o que sabe, com a data, e pergunta apenas se algo mudou.

**Tool Search desligado.** O Hermes esconde tools de plugin atrás de três tools de descoberta quando há tools diferíveis, um mecanismo pensado para catálogos com centenas de tools. Seis tools com 3,4 KB de schema ficam visíveis por inteiro (`tools.tool_search.enabled: "off"`). Com ele ligado, as skills que declaram `requires_tools` também sumiam do índice.

**Toolset fechado.** `platform_toolsets.cli` é uma lista explícita: `web`, `clarify`, `skills`, `memory`, `session_search`. A toolset do plugin entra por ele estar habilitado. Terminal, arquivos, browser, execução de código, delegação e cron ficam fora. Escritas de skill pelo agente exigem aprovação humana (`skills.write_approval`), e a revisão automática pós-turno, que grava memória e skills sem pedir, está desligada.

**Profile autoral.** `config.yaml` é escrito à mão, comentado, com `_config_version` fixado para o Hermes não migrar e reescrever o arquivo. O marcador `.no-bundled-skills` impede a semeadura das skills de fábrica; a única que entra mesmo assim é `hermes-agent`, o manual do próprio framework, que ele trata como essencial (`agent/skill_utils.py`).

**Compras são embalagens.** Ninguém compra duas colheres de vinagre. A consultora propõe a embalagem e um preço de mercado ("vou considerar a caixa de 200 g a R$ 3,50, pode ser?"); a tool calcula quantas embalagens cobrem o que falta, rateia o uso no CMV e desconta as embalagens inteiras do orçamento. Só entra preço que a Dona Maria confirmou.

**Escopo e custo.** Antes do primeiro chamado ao modelo em cada turno de usuário, um middleware `llm_request` tria a última mensagem com o modelo barato (cerca de 180 tokens, pelo `ctx.llm` do Hermes, com credenciais do host). Se ela é claramente alheia à consulta, a requisição é reescrita: modelo barato, instrução mínima de recusa, sem tools e sem os 8 mil tokens de prompt. Um hook `post_api_request` grava no log qual modelo o provider reporta ter servido. Respostas a perguntas de `clarify` não passam pelo middleware; para elas vale a regra de escopo do `SOUL.md`. A triagem falha aberta: se quebrar, o turno segue pelo caminho normal, com aviso no log.

## Garantias, controle e auditoria

| Pergunta | Resposta | Evidência |
|---|---|---|
| De onde vem cada número do preço? | De `dish_price`, linha a linha, com a linha da planilha ou a compra que originou o custo. O modelo explica; não calcula. | Resultado da tool na sessão; testes em `tests/test_pricing.py` |
| O que impede aceitar um prato cedo demais? | O gate em `recipe_update`, que recusa aceitação com bloqueios abertos ou compras acima do orçamento. | `tests/test_tools.py`, `tests/test_recipes.py` |
| Onde está a trilha da conversa? | No banco de sessões do Hermes (`state.db`), com cada turno, tool call, argumento e resultado; exportável com `hermes sessions export`. | `hermes sessions export --format md --session-id <id>` |
| E o tracing? | Langfuse, opcional: um trace por turno, uma geração por chamada de modelo, um span por tool call, agrupados pelo id de sessão do Hermes, com tokens e custo. | Plugin bundled `observability/langfuse` |
| O que o agente pode fazer? | Só o toolset acima. Sem terminal, arquivos, browser ou código. | `profile/config.yaml` |
| E segredos e injeção? | Redação de segredos ligada por padrão no Hermes, forçada de novo pelo plugin do Langfuse antes de exportar (`capture_mode: sanitized`). SOUL e context files passam pelo scanner de injeção do Hermes; conteúdo de página é tratado como dado, por regra do `SOUL.md`. | Config do Hermes; `profile/SOUL.md` |
| Como se sabe que uma mensagem fora de escopo não gastou o modelo principal? | Duas linhas de log por turno: `rerouted to gpt-5.6-luna` (nossa decisão) e `served by gpt-5.6-luna` (o provider). | `logs/agent.log`; verificação `off_topic_turns_rerouted` na suíte |

Limitações conhecidas do tracing: o plugin bundled do Hermes fala a API do SDK v3 do Langfuse; organizações novas do Langfuse só ingerem pelo caminho do v4, então o profile instala o v4. Com isso, a prévia de entrada e saída no nível do trace fica vazia (o span raiz de cada turno tem as duas), e o `userId` não é preenchido porque o Hermes não carrega identidade de usuário em sessões de CLI.

## Avaliação

Quatro camadas, da mais barata à mais cara:

1. **Testes de unidade** (`tests/`, 61 testes): os oito formatos de unidade da planilha, a derivação do custo unitário como o enunciado define, as conversões e suas recusas, cada condição do gate nomeando seu bloqueio, as fórmulas de preço, as recusas do contrato das tools, e o guarda de escopo. Nenhum teste de getter.
2. **Cenários simulados** (`evals/scenarios/`): uma Dona Maria interpretada por um modelo barato, com fatos escondidos que ela só revela se perguntada, rodada contra o agente real (mesmo runtime, tools, skills e banco de sessões do CLI). Três cenários: sem forno e sem saber selar carne; pedidos fora de escopo no meio da consulta; retorno no dia seguinte com o cardápio de ontem e uma mudança na cozinha.
3. **Verificações determinísticas** (`evals/checks.py`): lidas do que as tools gravaram e do log, nunca da prosa do modelo. Aceite só depois de gostar e confirmar técnicas; preço só depois do aceite; preço escolhido acima do piso; receita registrada só de página extraída; turnos fora de escopo servidos pelo modelo barato; nenhuma pergunta de cozinha repetida no retorno.
4. **Rubrica binária** (`evals/judge.py`): dez critérios de qualidade da conversa para uma pessoa simples, cada um respondido sim ou não por um juiz com a evidência do transcript; a nota é a soma. Critérios: no máximo três perguntas por mensagem, preço proposto em vez de perguntado, linguagem simples, link e rendimento em toda receita, números rastreados, nada fechado cedo, fora de escopo recusado em uma frase, nada assumido, decisão dela, nada perguntado duas vezes.

Os scores das camadas 3 e 4 são anexados à sessão correspondente no Langfuse, para que trace e avaliação fiquem juntos.

```bash
./scripts/evaluate.sh scenarios/sem-forno.yaml scenarios/fora-de-escopo.yaml scenarios/segundo-dia.yaml
```

Cada rodada da suíte reseta o estado da consulta e a memória do Hermes antes de cada cenário, para que nada de uma Dona Maria simulada vaze para a próxima. A mesma suíte roda com outro modelo principal por argumento (`--model`), sem tocar no config.

Última rodada com o modelo entregue e a rodada de comparação com o modelo barato, um run por cenário:

| Cenário | Modelo | Verificações | Rubrica | Turnos | s/turno p50 | s/turno máx | Cache | Custo (USD) |
|---|---|---|---|---|---|---|---|---|
| sem-forno | gpt-5.6-terra | 5/5 | 8/10 | 7 | 13,2 | 111,8 | 96% | 0,73 |
| fora-de-escopo | gpt-5.6-terra | 5/5 | 7/10 | 7 | 9,6 | 111,1 | 92% | 0,42 |
| segundo-dia | gpt-5.6-terra | 6/6 | 8/10 | 10 | 4,7 | 31,9 | 93% | 0,28 |
| sem-forno | gpt-5.6-luna | 5/5 | 9/10 | 5 | 8,1 | 58,1 | 94% | 0,16 |
| fora-de-escopo | gpt-5.6-luna | 5/5 | 9/10 | 6 | 7,8 | 61,5 | 94% | 0,14 |
| segundo-dia | gpt-5.6-luna | 6/6 | 8/10 | 4 | 28,2 | 53,6 | 93% | 0,16 |

Como ler a tabela:

1. As verificações determinísticas passaram em todas as rodadas, com os dois modelos. São invariantes que o código impõe; se uma falhar, é bug, não variância.
2. A rubrica varia entre rodadas do mesmo modelo: a rodada anterior do terra marcou 10/10, 9/10 e 8/10 nos mesmos cenários. Com um run por cenário, terra e luna são indistinguíveis na conversa; o custo é de três a seis vezes menor no luna. Em produção, a troca seria decidida com várias repetições por cenário, não com esta amostra.
3. As reprovações recorrentes, nos dois modelos, são duas: perguntar o preço de uma compra sem propor embalagem e valor, apesar da regra no `SOUL.md` e na skill; e insistir num dado quando a Dona Maria adia a resposta. São os próximos alvos de iteração, registrados com a evidência do juiz nos scores da sessão no Langfuse.
4. O turno mais longo (até 112 s) é sempre o de pesquisa: três buscas, extração de duas ou três páginas e o registro, com cinco a sete chamadas ao modelo. O Hermes executa em paralelo as tool calls emitidas numa mesma resposta; o que não paraleliza é buscar, extrair, registrar. O gargalo medido é o backend de busca (Firecrawl: p50 de 1,2 s, p95 de 27 s por busca). O prompt cache da OpenAI cobre 92% a 97% da entrada do modelo principal, o que faz o system prompt grande (identidade, guia do Hermes, schemas das tools, cerca de 8 mil tokens) custar 0,2 centavo de dólar por chamada depois da primeira.

O modelo entregue continua sendo o terra: no cenário que é o coração do case, a elicitação, ele foi o único a marcar 10/10 em uma rodada, e o custo por consulta fica abaixo de um dólar. O luna fica documentado como a opção de custo, com os números acima.

O que a suíte encontrou nas rodadas anteriores, e que virou correção: receitas registradas sem técnica declarada deixavam o gate sem o que confirmar (hoje o modelo exige ao menos um método de cocção por receita); uma opção "4 ou mais" numa pergunta sobre bocas do fogão fazia a consultora gravar "4" como certeza; valores com quatro casas decimais chegavam à conversa; a memória de preferências de um cenário vazava para o seguinte no harness. Do lado do avaliador: técnicas confirmadas em conversas anteriores não contavam, fatos da planilha eram lidos como assunção, e um cenário que termina antes do preço era cobrado por ele.

## Premissas

1. O orçamento de R$ 80,00 é total para o cardápio, consumido a cada prato aceito.
2. "Prato" é uma porção vendida; o CMV e o preço são por porção, com o rendimento da página.
3. Margem é o lucro sobre o que a Dona Maria recebe: `P = CMV / (0,90 × (1 − m))`, cenários de 20%, 35% e 50%, configuráveis. Preço mínimo `P = CMV / 0,90`.
4. A taxa de 10% é parâmetro (`platform_fee`), fixada como no enunciado.
5. Embalagem e entrega ficam fora do custo e do orçamento, porque o enunciado define os dois em termos de ingredientes. A consultora diz isso ao apresentar o preço.
6. Medidas de receita (colher, xícara, dente, unidade de tomate) convertem por uma tabela versionada em `profile/plugins/menu_costing/data/conversions.yaml`, com densidades e pesos por peça aproximados e restritos aos 37 itens da despensa. Toda conversão aplicada é devolvida à cozinheira para conferência.
7. Preços de complementos são estimativas da consultora confirmadas ou corrigidas pela Dona Maria; só o valor confirmado entra.
8. Itens contados em unidades sem tamanho de embalagem na planilha (a cobertura de chocolate a R$ 79,90) não podem ser custeados em gramas até a Dona Maria informar o tamanho, que a consultora pergunta e registra com `pantry_amend`.
9. O estoque é verificado para um lote da receita; a operação contínua do delivery está fora do escopo.
10. Uma cozinheira, uma cozinha, um cardápio: o estado não é multiusuário.

## O que ficou de fora

Servidor MCP, hooks de auditoria próprios (redundantes com o banco de sessões e o Langfuse), subagentes e execução de código (uma conversa de um usuário não paraleliza nada), memória externa, cron, Postgres, filas, API HTTP e qualquer alteração no core do Hermes. Cada um desses seria uma linha a justificar sem uma pergunta do enunciado que o pedisse.

## Estrutura do repositório

```
profile/                      o profile do Hermes: instalável com hermes profile install
  distribution.yaml           manifesto e variáveis de ambiente exigidas
  SOUL.md                     identidade e regras da consultora
  config.yaml                 modelo, auxiliares, toolsets, memória, plugins
  data/despensa_dona_maria.xlsx
  skills/sabor-da-maria/      recipe-research, kitchen-constraints, menu-costing
  plugins/menu_costing/       tools.py (fronteira), scope.py (guarda), domain/ (regras puras)
tests/                        pytest sobre o domínio, o contrato das tools e o guarda
evals/                        harness com cozinheira simulada, verificações, juiz, suíte
scripts/                      install.sh, converse.sh, evaluate.sh
docs/                         enunciado do case
```

Ferramentas de desenvolvimento: `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run mypy`. O código roda dentro do ambiente do Hermes (Python 3.11); o repositório espelha essa versão.
