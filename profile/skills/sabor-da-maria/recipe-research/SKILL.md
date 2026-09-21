---
name: recipe-research
description: "Buscar receitas reais na internet a partir da despensa."
version: 1.0.0
metadata:
  hermes:
    tags: [receitas, busca, cardápio]
    category: sabor-da-maria
    requires_tools: [web_search, web_extract, recipe_register]
---

# Pesquisa de receitas

## Quando usar

Ao propor receitas para a Dona Maria, e sempre que ela pedir outra opção.

## Procedimento

1. Parta da despensa (pantry_inventory) e do que ela já disse que gosta ou evita. Escolha dois ou três ingredientes que ela tem em quantidade e monte buscas em português, como "receita frango com batata rendimento porções".
2. Use web_search e escolha páginas de receita que tragam a lista de ingredientes com quantidades e o rendimento em porções. Prefira sites brasileiros de receitas. Descarte vídeos sem texto e páginas sem quantidades.
3. Use web_extract na página escolhida. Extraia: título, URL, rendimento em porções, cada ingrediente com quantidade e unidade como está escrito, equipamentos necessários (fogao, forno, panela_de_pressao, air_fryer, liquidificador, batedeira, micro_ondas, freezer), quantas bocas usa ao mesmo tempo e as técnicas exigidas.
4. Apresente sempre duas ou três candidatas por vez, para ela ter escolha. Para cada uma: o link, uma linha sobre por que combina com a despensa dela, e o que faltaria comprar. Pergunte o que ela acha: gosta de cozinhar isso? Vê algum impedimento?
5. Registre com recipe_register apenas as receitas em que ela demonstrou interesse. Mapeie cada ingrediente ao nome exato da despensa em pantry_item, ou deixe nulo quando ela não tem.
6. O que se vende no delivery é a porção montada, não o preparo da página. Se a receita descreve só o componente principal (um refogado, um recheio, um molho), pergunte a ela como monta a marmita e registre os acompanhamentos em per_portion_items, com a quantidade por porção que ela disse. O rendimento continua sendo o da página. Embalagem e entrega ficam fora do custo, como no enunciado da consulta; não pergunte sobre elas.

## Regras

1. Ingredientes, quantidades e rendimento vêm da página. Se a página não informa o rendimento, escolha outra receita ou pergunte a ela quantas porções faria com aquelas quantidades.
2. Temperos sem quantidade na página viram uma quantidade explícita que você diz a ela: 5 g para sal e temperos secos, 10 g para ervas frescas, 1 tablete para caldos.
3. Água não é ingrediente registrado.
4. Se você mapear um ingrediente da página a um item parecido da despensa (penne para espaguete, patinho para acém), diga a ela a troca antes de registrar.
5. Não force um item da despensa em uma receita para aproveitá-lo. O que já foi comprado não é motivo para escolher um prato.
6. Nunca invente uma receita ou um link.
