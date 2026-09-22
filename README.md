# Sabor da Maria

Consultora de cardápio e precificação para a Dona Maria, construída sobre o [Hermes Agent](https://github.com/NousResearch/hermes-agent). Ela acompanha a cozinheira da despensa ao cardápio de lançamento: encontra receitas reais na internet, confirma que a Dona Maria consegue produzi-las na cozinha que tem, compara os ingredientes com a despensa, e calcula o CMV e o preço de venda com a taxa da plataforma, deixando a decisão com ela.

Este repositório é uma *profile distribution* do Hermes: tudo que customiza o agente vive em `profile/` e se instala com um comando. O Hermes em si não tem uma linha alterada e fica fixado em uma versão.

| Item | Valor |
|---|---|
| Hermes Agent | v0.21.3 (2026.9.14), commit `6a627e6e` |
| Modelo principal | `gpt-6-sol`, OpenAI direto, Responses API |
| Modelo auxiliar | `gpt-6-luna` (título de sessão, compressão, triagem de escopo, recusa fora de escopo) |
| Juiz da avaliação | `claude-sonnet-5`, Anthropic, só na suíte |
| Busca e extração | Firecrawl |
| Tracing | Langfuse, opcional, SDK v4 |

## Como rodar

Pré-requisitos: Linux, macOS ou WSL2, `curl`, `git`, uma chave da OpenAI e uma do Firecrawl. A suíte de avaliação pede ainda uma chave da Anthropic, para o juiz.

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

Para desenvolver dentro do repositório, aponte o Hermes direto para a pasta do profile: `HERMES_HOME=$PWD/profile hermes`, com um `profile/.env` próprio (o mesmo `.env.example`). O estado de runtime que o Hermes grava ali (banco de sessões, logs, caches) está no `.gitignore`. Os scripts da suíte usam esse `HERMES_HOME` por padrão e apagam a consulta e a memória antes de cada cenário; eles se recusam a rodar contra um profile instalado em `~/.hermes`.

Uma observação sobre o início de sessão: o CLI imprime `Warning: Unknown toolsets: menu_costing`. É uma ordem de inicialização do Hermes (`cli.py` valida os nomes de toolset antes de descobrir os plugins, que só carregam na primeira importação de `model_tools`). As tools funcionam normalmente; o log registra cada chamada.

## Como a consulta funciona

A conversa não é linear, mas cada etapa do enunciado tem um procedimento (uma skill) e uma tool que a torna verificável.

| Etapa do enunciado | Skill que a consultora carrega | Tools |
|---|---|---|
| 2.2 Elicitação de restrições | `kitchen-constraints` | `kitchen_profile`, `clarify` (nativa do Hermes) |
| 2.1 Pesquisa de receitas | `recipe-research` | `web_search`, `web_extract`, `recipe_register` |
| 2.3 Ingredientes e compras | `kitchen-constraints` | `recipe_register`, `recipe_update`, `pantry_inventory`, `pantry_amend` |
| 2.4 Aceitação, CMV e preço | `menu-costing` | `recipe_update`, `dish_price` |

O ponto central do enunciado, "não pode deixar ela comprar ingredientes e descobrir depois que não consegue cozinhar", é um *gate* em código, não uma instrução de prompt. `recipe_register` devolve a lista de bloqueios de uma receita: bocas do fogão desconhecidas (se a receita usa fogão), equipamento que a receita usa e ela não tem ou ainda não disse se tem, técnica que a receita exige e não está confirmada no perfil, ingrediente que falta sem compra confirmada. `recipe_update` só grava a aceitação quando essa lista está vazia e as compras cabem no orçamento. `dish_price` recusa qualquer prato não aceito. A consultora conduz a conversa; a garantia não depende dela.

O perfil da cozinha tem a forma do enunciado: equipamentos (as bocas do fogão como número, o resto como nomes que o modelo escolhe: forno, panela de pressão, air fryer, churrasqueira), técnicas e habilidades (também por nome), e restrições operacionais (tempo por cozinhada e o resto em texto). Nada disso é enumeração fechada em código. O que bloqueia um prato é o que ele exige e o código consegue comparar: uma receita de fogão não espera a resposta sobre a air fryer, e o tempo por cozinhada, que só o modelo sabe pesar contra uma receita, é perguntado pela skill mas não trava nada. O fogão é o único equipamento guardado como número porque é o único de que uma receita precisa em quantidade (bocas ao mesmo tempo) e o único que o código compara.

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
3. `kitchen_profile` lê ou atualiza o perfil da cozinha (os fatos novos se somam aos gravados) e devolve o que ainda falta para qualquer prato e quando ela falou da cozinha pela última vez.
4. `recipe_register` registra uma receita extraída de uma página real, converte as medidas, compara com a despensa e a cozinha, e devolve o que ela tem, o que falta e os bloqueios.
5. `recipe_update` grava o que ela disse sobre a receita: se gostou, compras confirmadas (como embalagens) e a aceitação. Mudar as compras ou deixar de gostar desfaz um aceite anterior, porque o custo mudou.
6. `dish_price` calcula o CMV por porção linha a linha, o preço mínimo e cenários por margem, e registra o preço escolhido.

## Decisões de arquitetura

**Modelo e provider.** OpenAI direto, sem intermediário no caminho dos dados. `gpt-6-sol` no loop da conversa, onde a consultora precisa raciocinar, lembrar restrições e usar juízo (a OpenAI o posiciona para workflows agênticos); `gpt-6-luna`, vinte vezes mais barato, nas tarefas mecânicas: triagem de escopo, recusa fora de escopo, título de sessão, compressão. Os dois foram lançados em 22 de setembro de 2026 e substituíram `gpt-5.6-terra` e `gpt-5.6-luna` no mesmo dia, com a suíte rodada nos quatro (tabela abaixo). O Hermes é agnóstico de provider (a troca é o bloco `model:` do config e uma variável no `.env`). As chamadas do modelo principal vão com `store: false`, por isso não aparecem no console de logs da OpenAI. Limite a observar: na organização usada, `gpt-6-luna` tem 200 mil tokens por minuto e cada chamada do loop carrega 40 a 80 mil tokens de contexto; por isso ele não fica no loop, apenas nas tarefas de contexto curto.

**Busca.** Firecrawl como backend único de busca e extração. O que importa aqui não é ranking, é fidelidade da extração: as quantidades da página alimentam o CMV. Toda receita apresentada carrega o link e o rendimento da página; a consultora não inventa receitas nem links. Preços de compras não são pesquisados: a consultora propõe do próprio conhecimento do mercado e a Dona Maria confirma ou corrige, que é como se faz com quem conhece o mercado dela. Uma rodada anterior gastava dezoito buscas por consulta procurando preço de pimentão.

**Tools em plugin, não em skill nem em MCP.** O guia do próprio Hermes diz: skill quando cabe em instruções mais tools existentes; tool quando a lógica precisa executar de forma precisa toda vez. O gate, a matemática e o estado precisam. Plugin em vez de MCP porque são funções Python em processo, e um servidor a mais não compraria nada. Plugin em vez de editar o core porque fork não se revisa.

**Estado explícito.** A cozinha (`kitchen.json`), as correções da despensa e o cardápio de lançamento (`menu.json`) ficam em JSON no profile e atravessam sessões. Uma receita registrada e abandonada não consome orçamento e fica no arquivo como histórico. A memória nativa do Hermes (`USER.md`) fica reservada a preferências duráveis da Dona Maria. Cada fato tem um lugar só. Quando ela volta em outro dia, a consultora recapitula o que sabe, com a data, e pergunta apenas se algo mudou.

**Tool Search desligado.** O Hermes esconde tools de plugin atrás de três tools de descoberta quando há tools diferíveis, um mecanismo pensado para catálogos com centenas de tools. Seis tools com 3,4 KB de schema ficam visíveis por inteiro (`tools.tool_search.enabled: "off"`). Com ele ligado, as skills que declaram `requires_tools` também sumiam do índice.

**Toolset fechado.** `platform_toolsets.cli` é uma lista explícita: `web`, `clarify`, `skills`, `memory`. A toolset do plugin entra por ele estar habilitado. A busca em sessões antigas (`session_search`) ficou de fora depois que a suíte a pegou em flagrante: a consultora encontrou a transcrição de outra consulta e deu um prato como fechado sem confirmar nada. Os fatos da consulta têm um lugar só, o ledger das tools, e o modelo não deve reconstruí-los a partir de conversas antigas. Terminal, arquivos, browser, execução de código, delegação e cron ficam fora. Escritas de skill pelo agente exigem aprovação humana (`skills.write_approval`), e a revisão automática pós-turno, que grava memória e skills sem pedir, está desligada.

**Profile autoral.** `config.yaml` é escrito à mão, comentado, com `_config_version` fixado para o Hermes não migrar e reescrever o arquivo. O marcador `.no-bundled-skills` impede a semeadura das skills de fábrica; a única que entra mesmo assim é `hermes-agent`, o manual do próprio framework, que ele trata como essencial (`agent/skill_utils.py`).

**Compras são embalagens.** Ninguém compra duas colheres de vinagre. A consultora propõe a embalagem e um preço de mercado ("vou considerar a caixa de 200 g a R$ 3,50, pode ser?"); a tool calcula quantas embalagens cobrem o que falta, rateia o uso no CMV e desconta as embalagens inteiras do orçamento. Só entra compra marcada como confirmada por ela.

**O modelo decide onde o código não deve.** Nomes de equipamento e técnica, equivalências que a tabela de conversões não cobre ("um pimentão dá uma xícara picada"), temperos usados "a olho", e o olhar de mercado sobre o preço são decisões do modelo, propostas a ela para confirmar. O código guarda o que precisa ser garantido: a matemática, o gate, o dinheiro comprometido, e o registro de cada confirmação dela. Vale dizer com precisão o que isso garante: que o modelo registrou uma confirmação (`liked`, `confirmed_by_cook`, `stated_by_cook`, a técnica no perfil) antes de qualquer passo que dependa dela. Que a confirmação corresponde ao que ela disse é o que a suíte e o transcript verificam, não o código.

**Escopo e custo.** Antes do primeiro chamado ao modelo em cada turno de usuário, um middleware `llm_request` tria a última mensagem com o modelo barato (cerca de 180 tokens, pelo `ctx.llm` do Hermes, com credenciais do host). Se ela é claramente alheia à consulta, a requisição é reescrita: modelo barato, instrução mínima de recusa, sem tools e sem os 8 mil tokens de prompt. Um hook `post_api_request` grava no log qual modelo o provider reporta ter servido. Respostas a perguntas de `clarify` não passam pelo middleware; para elas vale a regra de escopo do `SOUL.md`. A triagem falha aberta: se quebrar, o turno segue pelo caminho normal, com aviso no log.

## Garantias, controle e auditoria

| Pergunta | Resposta | Evidência |
|---|---|---|
| De onde vem cada número do preço? | De `dish_price`, linha a linha, com a linha da planilha ou a compra que originou o custo. O modelo explica; não calcula. | Resultado da tool na sessão; testes em `tests/test_pricing.py`; verificação `prices_told_match_tool`, que exige que o piso e cada cenário ditos à Dona Maria sejam os que a tool devolveu naquele turno |
| O que impede aceitar um prato cedo demais? | O gate em `recipe_update`, que recusa aceitação com bloqueios abertos ou compras acima do orçamento. Um prato aceito não muda de composição sem desfazer o aceite. | `tests/test_tools.py`, `tests/test_recipes.py` |
| Onde está a trilha da conversa? | No banco de sessões do Hermes (`state.db`), com cada turno, tool call, argumento e resultado; exportável com `hermes sessions export`. | `hermes sessions export --format md --session-id <id>` |
| E o tracing? | Langfuse, opcional: um trace por turno, uma geração por chamada de modelo, um span por tool call, agrupados pelo id de sessão do Hermes, com tokens e custo. | Plugin bundled `observability/langfuse` |
| O que o agente pode fazer? | Só o toolset acima. Sem terminal, arquivos, browser ou código. | `profile/config.yaml` |
| E segredos e injeção? | Redação de segredos ligada por padrão no Hermes, forçada de novo pelo plugin do Langfuse antes de exportar (`capture_mode: sanitized`). SOUL e context files passam pelo scanner de injeção do Hermes; conteúdo de página é tratado como dado, por regra do `SOUL.md`. | Config do Hermes; `profile/SOUL.md` |
| Como se sabe que uma mensagem fora de escopo não gastou o modelo principal? | Duas linhas de log por turno: `rerouted to gpt-6-luna` (nossa decisão) e `served by gpt-6-luna` (o provider). | `logs/agent.log`; verificação `off_topic_turns_rerouted` na suíte |

Limitações conhecidas do tracing: o plugin bundled do Hermes fala a API do SDK v3 do Langfuse; organizações novas do Langfuse só ingerem pelo caminho do v4, então o profile instala o v4. Com isso, a prévia de entrada e saída no nível do trace fica vazia (o span raiz de cada turno tem as duas), e o `userId` não é preenchido porque o Hermes não carrega identidade de usuário em sessões de CLI.

## Avaliação

Quatro camadas, da mais barata à mais cara:

1. **Testes de unidade** (`tests/`, 85 testes): os oito formatos de unidade da planilha, a derivação do custo unitário como o enunciado define, as conversões e suas recusas, cada condição do gate nomeando seu bloqueio, as fórmulas de preço, as recusas do contrato das tools (preço abaixo do piso, compra do que não falta, aceite com bloqueio, orçamento partilhado entre pratos, re-registro de prato aceito, aceite desfeito quando as compras mudam, correção da despensa), o guarda de escopo, os estados semeados dos cenários e as verificações da própria suíte. Nenhum teste de getter.
2. **Cenários simulados** (`evals/scenarios/`): uma Dona Maria interpretada pelo modelo barato do profile, com fatos escondidos que ela só revela se perguntada, rodada contra o agente real (mesmo runtime, tools, skills e banco de sessões do CLI). Três cenários: sem forno e sem saber selar carne; pedidos fora de escopo no meio da consulta; retorno no dia seguinte com o cardápio de ontem e uma mudança na cozinha. O harness encerra a conversa quando a cozinheira se despede ou quando repete a mesma mensagem duas vezes, que é o sinal de que os dois lados ficaram esperando o outro.
3. **Verificações determinísticas** (`evals/checks.py`): lidas do que as tools gravaram, dos resultados que devolveram e do log. Aceite só depois de gostar e com as técnicas confirmadas no perfil; preço só depois do aceite; piso e cenários ditos à Dona Maria iguais aos da tool no mesmo turno, e o preço escolhido repetido quando ela decide (a única verificação que lê a prosa, justamente para compará-la com o dado); receita registrada só de página extraída; exatamente os turnos fora de escopo do cenário servidos pelo modelo barato; nenhum fato da cozinha perguntado de novo no retorno. Um preço abaixo do piso não precisa de verificação: a tool o recusa, e o teste de unidade cobre a recusa.
4. **Rubrica binária** (`evals/judge.py`): onze critérios de qualidade da conversa para uma pessoa simples, cada um respondido sim ou não por um juiz com a evidência do transcript; a nota é a fração. O juiz é o `claude-sonnet-5`, de outro fornecedor que o da consultora, de propósito: um modelo avaliando a própria família tende a perdoar o próprio estilo, e o custo do juiz não escala com clientes, então ele pode ser mais forte que o modelo do loop. O juiz vê a conversa como a Dona Maria a viu e, entre as falas, as tool calls que a consultora fez, para distinguir fato confirmado de fato assumido. Critérios: no máximo três perguntas por mensagem, preço proposto em vez de perguntado, linguagem simples, link e rendimento em toda receita, números rastreados, nada fechado cedo, fora de escopo recusado em uma frase, nada assumido, decisão dela, nada perguntado duas vezes, fala de pessoa e não de sistema.

Os scores das camadas 3 e 4 são anexados à sessão correspondente no Langfuse, para que trace e avaliação fiquem juntos.

```bash
./scripts/evaluate.sh scenarios/sem-forno.yaml scenarios/fora-de-escopo.yaml scenarios/segundo-dia.yaml
```

Cada rodada da suíte reseta o estado da consulta e a memória do Hermes antes de cada cenário, para que nada de uma Dona Maria simulada vaze para a próxima. O modelo principal e o barato (que serve os turnos fora de escopo e interpreta a Dona Maria) vêm do `config.yaml` do profile; cada um se troca por argumento (`--model`, `--cook-model`, `--judge-model`) sem tocar no config. O custo é calculado sobre os tokens que o Hermes contou, com os preços de lista da OpenAI em `evals/prices.yaml` (com a fonte e a data), porque a tabela interna do Hermes é de julho e cobrava o luna 5.6 a cinco vezes o preço atual.

Rodada final, com a suíte na forma atual (cinco verificações, seis no retorno; onze critérios; juiz `claude-sonnet-5`), dois runs por cenário e por modelo:

| Cenário | Modelo | Verificações | Rubrica | Turnos | s/turno p50 | s/turno máx | Cache | Custo (USD) |
|---|---|---|---|---|---|---|---|---|
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

Como ler a tabela:

1. Com o `gpt-6-sol`, as verificações determinísticas passaram nos seis runs e a rubrica ficou em 11/11 em cinco deles. As duas reprovações do sexto são de conversa: uma receita apresentada sem o rendimento e um fechamento que repetiu só a taxa e a sobra, sem a conta linha a linha que a mesma consultora tinha mostrado no turno anterior. Estão anotadas com a evidência do juiz nos scores da sessão no Langfuse.
2. Com o `gpt-6-luna`, quatro dos seis runs reprovam na verificação que compara o preço dito com o preço da tool: ele apresenta um valor que não é o dos cenários, ou nem chega a apresentá-los. Um run desviou para a recusa de escopo um turno que estava dentro do assunto, e as duas consultas sem-forno levaram dezesseis turnos e mais de quatro minutos num turno, com 396 recusas por limite de tokens por minuto do provider no dia (contra 6 do sol). Custa vinte vezes menos e não serve para o loop desta consulta; serve para o que faz aqui: triagem, recusa, títulos, compressão e a Dona Maria simulada.
3. O turno mais longo (até 132 s no sol) é o de pesquisa: buscas, extração de páginas e o registro, com várias chamadas ao modelo. O Hermes executa em paralelo as tool calls emitidas numa mesma resposta; o que não paraleliza é buscar, extrair, registrar. O gargalo medido é o backend de busca (Firecrawl: p50 de 1,2 s, p95 de 27 s por busca). O prompt cache cobre 92% a 96% da entrada do modelo principal.
4. Uma consulta inteira custa de 0,24 a 0,58 USD no sol, pelos preços de lista, e depende mais do número de pesquisas do que do número de turnos.

O que a suíte encontrou e virou correção, na ordem em que apareceu (a parte final desta lista é do último dia): receitas registradas sem técnica declarada deixavam o gate sem o que confirmar (hoje o modelo exige ao menos um método de cocção por receita); uma opção "4 ou mais" numa pergunta sobre bocas do fogão fazia a consultora gravar "4" como certeza; valores com quatro casas decimais chegavam à conversa; a memória de preferências de um cenário vazava para o seguinte no harness; e, na última rodada, a consultora achou a transcrição de outra consulta pelo `session_search` e deu um segundo prato como fechado sem confirmar nada, o que tirou essa tool do toolset. Do lado do avaliador: técnicas confirmadas em conversas anteriores não contavam, fatos da planilha eram lidos como assunção, um cenário que termina antes do preço era cobrado por ele, e a verificação de preço lia a prosa com uma expressão regular em vez de comparar com o resultado da tool. Com os modelos novos: o `gpt-6-sol` travou duas consultas esperando a Dona Maria medir os temperos que ela usa "a olho" (a rubrica deu 100% e 91% para essas conversas; a verificação determinística de preço as reprovou, que é o motivo de existirem as duas camadas), e a consultora gastava dezoito buscas por consulta procurando preço de pimentão. As duas viraram regra de skill: quantidade proposta em vez de esperada, preço proposto em vez de pesquisado.

## Premissas

1. O orçamento de R$ 80,00 é total para o cardápio, consumido a cada prato aceito.
2. "Prato" é uma porção vendida; o CMV e o preço são por porção, com o rendimento da página.
3. Margem é o lucro sobre o que a Dona Maria recebe: `P = CMV / (0,90 × (1 − m))`, cenários de 20%, 35% e 50%, configuráveis. Preço mínimo `P = CMV / 0,90`.
4. A taxa de 10% é parâmetro (`platform_fee`), fixada como no enunciado.
5. Embalagem e entrega ficam fora do custo e do orçamento, porque o enunciado define os dois em termos de ingredientes. A consultora diz isso ao apresentar o preço.
6. Medidas de receita (colher, xícara, dente, unidade de tomate) convertem por uma tabela versionada em `profile/plugins/menu_costing/data/conversions.yaml`, com densidades e pesos por peça aproximados e restritos aos 37 itens da despensa. Toda conversão aplicada é devolvida à cozinheira para conferência.
7. Preços de complementos são estimativas da consultora confirmadas ou corrigidas pela Dona Maria; só o valor confirmado entra.
8. Itens contados em unidades sem tamanho de embalagem na planilha (a cobertura de chocolate a R$ 79,90) não podem ser custeados em gramas: a conversão recusa, a consultora pergunta o tamanho e registra com `pantry_amend`. Ovos são contados e não precisam de tamanho.
9. O estoque é verificado para um lote da receita; a operação contínua do delivery está fora do escopo.
10. Uma cozinheira, uma cozinha, um cardápio: o estado não é multiusuário.
11. Um preço abaixo do custo não é registrado. Ela decide entre preços a partir do piso; a tool recusa o resto e a consultora explica o motivo. Os cenários de margem são uma referência, não um teto: a consultora diz quanto pratos parecidos custam no delivery, porque a conta cobre só ingredientes e um prato barato de ingrediente sairia a R$ 4,00.
12. As compras confirmadas de uma receita substituem a lista anterior a cada `recipe_update`, por desenho: a lista é a que ela confirmou por último, sem restos de uma tentativa anterior.
13. Quantidades ditas "a olho" ou "a gosto" viram uma quantidade explícita proposta pela consultora e dita a ela, para corrigir; ninguém espera a próxima leva para custear.

## Limites conhecidos

O que um leitor com tempo encontraria, dito antes:

1. **Concorrência.** O estado é JSON com escrita atômica, sem lock. Duas conversas com a mesma cozinheira ao mesmo tempo poderiam perder uma escrita. O enunciado tem uma cozinheira; em produção, isso viraria um banco com transação por consulta.
2. **Versão do estado.** `kitchen.json` e `menu.json` são validados pelos modelos Pydantic ao carregar, mas não carregam número de versão. Mudar um campo obrigatório exige migrar o arquivo à mão.
3. **Amostra.** Poucos runs por cenário e por modelo. A rubrica varia entre rodadas iguais; as verificações determinísticas não. O juiz é de outro fornecedor, mas continua sendo um modelo lendo uma conversa: a evidência que ele cita em cada veredito está nos scores da sessão para quem quiser discordar dele.
4. **Fidelidade da extração.** A verificação garante que toda receita registrada veio de uma página extraída, não que as quantidades registradas são as da página. Isso pediria um conjunto de páginas com gabarito.
5. **Injeção por página.** A regra do `SOUL.md` e o scanner do Hermes cobrem o caso; não há cenário com uma página hostil na suíte.
6. **Latência de pesquisa.** O turno de pesquisa leva até dois minutos, limitado pelo backend de busca. No dashboard as tool calls aparecem enquanto acontecem; no CLI, a consultora avisa que vai pesquisar e a espera fica sem sinal.
7. **Orçamento e taxa são parâmetros do config**, não algo que a Dona Maria muda na conversa. O enunciado os fixa.
8. **Limite de tokens por minuto.** Cada chamada do loop carrega o contexto inteiro (40 a 80 mil tokens, a maior parte servida do cache, mas contada no limite). Um modelo com limite baixo na organização (o `gpt-6-luna` no dia do lançamento: 200 mil por minuto) estoura no turno de pesquisa, e o Hermes devolve à conversa o texto do erro do provider, em inglês. Em produção isso pede ou limite maior ou compressão de contexto (`compression.threshold_tokens`), ainda não ligada aqui porque o ledger já guarda os fatos e a compressão traria um resumo automático para o meio da consulta.

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
evals/                        harness com cozinheira simulada, verificações, juiz, métricas, preços, suíte
scripts/                      install.sh, converse.sh, evaluate.sh
docs/                         enunciado do case
```

Ferramentas de desenvolvimento: `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run mypy`. O código roda dentro do ambiente do Hermes (Python 3.11); o repositório espelha essa versão.
