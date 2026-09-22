---
name: recipe-research
description: "Buscar receitas reais na internet a partir da despensa."
version: 1.1.0
metadata:
  hermes:
    tags: [receitas, busca, cardápio]
    category: sabor-da-maria
    requires_tools: [pantry_inventory, web_search, web_extract, recipe_register]
---

# Pesquisa de receitas

## Quando usar

Ao propor receitas para a Dona Maria, e sempre que ela pedir outra opção.

## Procedimento

1. Parta da despensa (pantry_inventory) e do que ela já disse que gosta ou evita. Escolha dois ou três ingredientes que ela tem em quantidade e monte buscas em português, como "receita frango com batata rendimento porções".
2. Use web_search, no máximo quatro buscas por rodada de propostas, e extraia só as páginas que vai apresentar: cada busca e cada extração custam segundos para ela esperar. Escolha páginas de receita que tragam a lista de ingredientes com quantidades e o rendimento em porções. Prefira receitas que rendam quatro porções ou mais; uma receita-base de uma porção não vira marmita. Prefira sites brasileiros de receitas. Descarte vídeos sem texto e páginas sem quantidades.
3. Use web_extract na página escolhida. Extraia: título, URL, rendimento em porções, cada ingrediente com quantidade e unidade como está escrito, quantas bocas do fogão usa ao mesmo tempo (burners_needed, 0 se não usa fogão), os equipamentos além do fogão pelo nome (forno, panela de pressão, air fryer, liquidificador) e as técnicas exigidas. Toda receita tem ao menos uma técnica: o método de preparo (refogar, cozinhar na pressão, assar, fritar, desfiar) entra sempre, e as que uma cozinheira pode não dominar (massa fresca, molho branco, ponto de carne) entram à parte, para serem confirmadas com ela.
4. Apresente sempre duas ou três candidatas por vez, para ela ter escolha. Para cada uma: o link, uma linha sobre por que combina com a despensa dela, e o que faltaria comprar. Pergunte o que ela acha: gosta de cozinhar isso? Vê algum impedimento?
5. Registre com recipe_register apenas as receitas em que ela demonstrou interesse. Mapeie cada ingrediente ao nome exato da despensa em pantry_item, ou deixe nulo quando ela não tem.
6. O que se vende no delivery é a porção montada, não o preparo da página. Se a receita descreve só o componente principal (um refogado, um recheio, um molho), pergunte a ela como monta a marmita e registre os acompanhamentos em per_portion_items, com a quantidade por porção que ela disse. Os temperos dos acompanhamentos não viram pergunta: use as quantidades da regra 3 da skill kitchen-constraints e diga o que assumiu. O rendimento continua sendo o da página. Embalagem e entrega ficam fora do custo; não pergunte sobre elas.

## Regras

1. Ingredientes, quantidades e rendimento vêm da página. Se a página não informa o rendimento, escolha outra receita ou pergunte a ela quantas porções faria com aquelas quantidades.
2. Temperos sem quantidade na página ("a gosto") viram uma quantidade explícita, com os valores da regra 3 da skill kitchen-constraints, dita a ela.
3. Água não é ingrediente registrado.
4. Se você mapear um ingrediente da página a um item parecido da despensa (penne para espaguete, patinho para acém), diga a ela a troca antes de registrar.
5. Não force um item da despensa em uma receita para aproveitá-lo. O que já foi comprado não é motivo para escolher um prato.
6. Nunca invente uma receita ou um link.
