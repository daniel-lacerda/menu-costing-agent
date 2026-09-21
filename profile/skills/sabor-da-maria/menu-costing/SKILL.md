---
name: menu-costing
description: "Explicar o CMV e propor preços de venda de um prato aceito."
version: 1.0.0
metadata:
  hermes:
    tags: [cmv, preço, margem, delivery]
    category: sabor-da-maria
    requires_tools: [dish_price]
---

# Custo e preço

## Quando usar

Depois que a Dona Maria aceitou um prato (recipe_update com accepted verdadeiro).

## Procedimento

1. Chame dish_price com o recipe_id. Não calcule nada por conta própria.
2. Explique o CMV por porção a partir de cost.lines: ingrediente, quantidade usada, de onde veio o custo (linha da planilha ou compra confirmada) e o valor. Mostre o total do lote e a divisão pelas porções.
3. Explique a taxa: a plataforma fica com a fração platform_fee do preço, então ela recebe o restante. Preço mínimo é floor_price_brl: abaixo dele ela perde dinheiro. Mostre a conta com os números dela.
4. Apresente os cenários de pricing.scenarios: para cada margem, o preço, o que a plataforma leva, o que ela recebe e o lucro por porção. A margem é o lucro sobre o que ela recebe.
5. Pergunte qual preço ela quer adotar. Ela pode escolher um valor fora dos cenários. Registre com dish_price passando chosen_price_brl.
6. Se o preço escolhido ficar abaixo do mínimo, a tool recusa. Explique o motivo e peça outro valor.

## Regras

1. Valores em reais com duas casas e formato brasileiro (R$ 12,50).
2. Para custo unitário, use unit_cost_display (por quilo, por litro ou por unidade). Não converta valores por conta própria.
3. Preço e lucro são por porção vendida.
