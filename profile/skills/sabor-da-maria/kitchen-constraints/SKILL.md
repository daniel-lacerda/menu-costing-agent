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

1. Perfil da cozinha, em kitchen_profile: bocas do fogão, forno, panela de pressão, air fryer, liquidificador, gás ou elétrico, espaço na geladeira e tempo por cozinhada. Batedeira, micro-ondas e freezer são opcionais. Pergunte tudo isso na primeira conversa, porque orienta que receitas propor; se ela não souber responder algo, siga em frente e volte ao assunto quando uma receita precisar.
2. Por receita: os equipamentos e as técnicas que ela exige, e os ingredientes que faltam. É isso que bloqueia a aceitação, junto com as bocas do fogão e o tempo por cozinhada.

## Procedimento

1. Chame kitchen_profile sem argumentos. O campo missing lista o que ainda não se sabe, e updated_at diz quando ela falou da cozinha pela última vez. Se missing está vazio, ela já contou tudo em outra conversa: recapitule em duas frases o que você sabe e pergunte apenas se algo mudou. Não pergunte de novo o que já está registrado.
2. Pergunte com clarify, no máximo três perguntas por chamada, sempre com opções (bocas: 2, 4, 5 ou 6; geladeira: pequena, média ou grande; tempo por cozinhada: até 1 hora, de 1 a 2 horas, mais de 2 horas). Explique em uma frase por que está perguntando: é para não sugerir um prato que ela não consegue fazer.
3. Grave cada resposta em kitchen_profile assim que ela responder.
4. Ao registrar uma receita, leia gate.blockers no resultado de recipe_register. Para cada técnica ou equipamento desconhecido, pergunte de forma concreta ("você já fez massa fresca em casa?") e grave a resposta: técnicas em recipe_update (techniques), equipamentos em kitchen_profile. Nomeie as técnicas sempre do mesmo jeito: o bloqueio lista as que ela já confirmou; se a receita pede uma delas com outro nome, registre a receita de novo usando o nome que já está no perfil. Só grave uma técnica como dominada quando ela disse isso com essas palavras.
5. Se ela não tem um equipamento ou não domina uma técnica, diga isso com clareza e ofereça outra receita. Não sugira comprar equipamento.
6. Para cada ingrediente com status missing ou short, a compra é a embalagem que ela vai comprar no mercado, não a quantidade usada: uma garrafa de vinagre, uma caixa de creme de leite, um pacote de embalagens. Proponha você a embalagem e um preço estimado de mercado, em uma pergunta de confirmação ("vou considerar a caixa de 200 g a R$ 3,50, pode ser?"). Nunca pergunte "quanto custa" sem propor um valor, e nunca peça a ela que pesquise: ela confirma ou corrige a sua estimativa. Só registre em recipe_update (purchases) depois que ela confirmar, informando o conteúdo de uma embalagem, o preço de uma embalagem e confirmed_by_cook verdadeiro. A tool calcula quantas embalagens cobrem o que falta, rateia o que a receita usa e desconta as embalagens inteiras do orçamento. Nunca multiplique preços por conta própria. Se o total não couber no orçamento restante, diga isso antes de seguir.
7. Quando gate.ready for verdadeiro e ela disser que quer o prato, grave a aceitação com recipe_update (accepted). Só então o prato pode ser precificado.

## Regras

1. Campo desconhecido é pergunta obrigatória. Assumir é proibido.
2. Quando a tool recusa converter uma medida porque um item da despensa é contado em unidades e a receita pede peso ou volume, pergunte a ela o tamanho da embalagem e registre com pantry_amend. Só registre o que ela informou.
3. Se ela contar algo espontaneamente ("meu forno não funciona"), grave na hora.
