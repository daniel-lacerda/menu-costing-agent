---
name: kitchen-constraints
description: "Confirmar equipamentos, técnicas e limitações da cozinha."
version: 1.0.0
metadata:
  hermes:
    tags: [elicitação, cozinha, viabilidade]
    category: sabor-da-maria
    requires_tools: [clarify, kitchen_profile, recipe_register, recipe_update]
---

# Restrições da cozinha

## Quando usar

No início da consulta, antes da primeira receita, e em cada receita candidata antes de ela ser aceita.

## O que precisa estar confirmado

1. Perfil da cozinha, em kitchen_profile: bocas do fogão, forno, panela de pressão, air fryer, liquidificador, gás ou elétrico, espaço na geladeira e tempo por cozinhada. Batedeira, micro-ondas e freezer são opcionais.
2. Por receita: os equipamentos e as técnicas que ela exige, e os ingredientes que faltam.

## Procedimento

1. Chame kitchen_profile sem argumentos. O campo missing lista o que ainda não se sabe.
2. Pergunte com clarify, agrupando até cinco perguntas em uma chamada e oferecendo opções quando fizer sentido (bocas: 2, 4 ou mais; geladeira: pequena, média ou grande; tempo por cozinhada: até 1 hora, de 1 a 2 horas, mais de 2 horas). Explique em uma frase por que está perguntando: é para não sugerir um prato que ela não consegue fazer.
3. Grave cada resposta em kitchen_profile assim que ela responder.
4. Ao registrar uma receita, leia gate.blockers no resultado de recipe_register. Para cada técnica ou equipamento desconhecido, pergunte de forma concreta ("você já fez massa fresca em casa?") e grave a resposta: técnicas em recipe_update (techniques), equipamentos em kitchen_profile.
5. Se ela não tem um equipamento ou não domina uma técnica, diga isso com clareza e ofereça outra receita. Não sugira comprar equipamento.
6. Para cada ingrediente com status missing ou short, a compra é a embalagem que ela vai comprar no mercado, não a quantidade usada: uma garrafa de vinagre, uma caixa de creme de leite, um pacote de embalagens. Proponha a embalagem e um preço estimado, diga que é estimativa e pergunte quanto ela pagaria. Só registre em recipe_update (purchases) depois que ela confirmar, informando o conteúdo de uma embalagem, o preço de uma embalagem e confirmed_by_cook verdadeiro. A tool calcula quantas embalagens cobrem o que falta, rateia o que a receita usa e desconta as embalagens inteiras do orçamento. Nunca multiplique preços por conta própria. Se o total não couber no orçamento restante, diga isso antes de seguir.
7. Quando gate.ready for verdadeiro e ela disser que quer o prato, grave a aceitação com recipe_update (accepted). Só então o prato pode ser precificado.

## Regras

1. Campo desconhecido é pergunta obrigatória. Assumir é proibido.
2. Item da despensa contado em unidades e sem tamanho de embalagem: pergunte o tamanho e confirme o preço pago, e registre com pantry_amend. Só registre o que ela informou.
3. Se ela contar algo espontaneamente ("meu forno não funciona"), grave na hora.
