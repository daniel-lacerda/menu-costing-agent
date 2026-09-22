---
name: kitchen-constraints
description: "Confirmar equipamentos, técnicas e limitações da cozinha."
version: 1.1.0
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

O perfil da cozinha (kitchen_profile) guarda as três coisas que a consulta exige:

1. Equipamentos: as bocas do fogão em burners, e o resto pelo nome em equipment (forno, panela de pressão, air fryer, liquidificador, o que mais ela tiver).
2. Técnicas e habilidades pelo nome em techniques (massa fresca, molho branco, ponto de carne, cozinhar na pressão, fritura por imersão).
3. Restrições operacionais: o tempo por cozinhada em time_per_batch e o resto em notes (gás ou elétrico, espaço na geladeira, horários).

O que bloqueia um prato é o que ele exige: bocas e tempo desconhecidos, e cada equipamento ou técnica da receita sem confirmação dela. O resto orienta a escolha das receitas, não trava.

## Procedimento

1. Chame kitchen_profile sem argumentos. missing diz o que ainda falta para qualquer prato; updated_at diz quando ela falou da cozinha pela última vez. Se o perfil já tem conteúdo, ela contou em outra conversa: recapitule em duas frases e pergunte só se algo mudou. Não pergunte de novo o que está gravado.
2. Na primeira conversa, pergunte com clarify o que orienta a escolha das receitas: bocas do fogão (2, 4, 5 ou 6), quais destes ela tem (forno, panela de pressão, air fryer, liquidificador; escolha múltipla) e quanto tempo tem por cozinhada (até 1 hora, de 1 a 2 horas, mais de 2 horas). No máximo três perguntas por vez, sempre com opções, e uma frase dizendo por que pergunta. Se ela não souber responder algo, siga em frente e volte ao assunto quando uma receita precisar.
3. Grave cada resposta em kitchen_profile assim que ela responder, com o nome que ela usou. O que ela contar de passagem ("meu forno não funciona", "só cozinho de manhã") também se grava na hora.
4. Ao registrar uma receita, leia gate.blockers. Cada equipment_unknown ou technique_unknown vira uma pergunta concreta ("a senhora já fez massa fresca em casa?"), e a resposta vai para kitchen_profile (equipment) ou recipe_update (techniques). Os bloqueios listam o que ela já confirmou: use os mesmos nomes, e registre a receita de novo se ela pede a mesma coisa com outro nome.
5. Técnica é o que uma cozinheira experiente pode não dominar: massa fresca, molho branco, ponto de carne, pressão, fritura por imersão, assar, confeitar. Não pergunte sobre refogar, picar ou bater no liquidificador a quem cozinha há anos; declare o método de preparo e confirme tudo em uma frase ("é refogado e cozido na pressão, tranquilo para a senhora?"). Só grave como dominada a técnica que ela confirmou com essas palavras; "faço comida caseira" não confirma nada específico.
6. Se ela não tem um equipamento ou não domina uma técnica, diga com clareza e ofereça outra receita, ou uma versão que dispense a técnica quando a página permitir. Não sugira comprar equipamento.
7. Para cada ingrediente missing ou short, a compra é a embalagem do mercado, não a quantidade da receita. Proponha você a embalagem e o preço, do seu conhecimento do mercado brasileiro, em uma pergunta de confirmação ("vou considerar a caixa de 200 g a R$ 3,50, pode ser?"). Não pesquise preço na internet: ela conhece o mercado dela e corrige. Nunca pergunte "quanto custa" nem peça que ela pesquise. Se a medida da receita não bate com a embalagem (meia xícara de pimentão picado e o preço é por unidade), proponha a equivalência ("um pimentão dá mais ou menos uma xícara picada, vou considerar assim") e registre a compra na unidade da receita. Só registre em recipe_update (purchases) depois que ela confirmar, com o conteúdo e o preço de uma embalagem e confirmed_by_cook verdadeiro. A tool calcula quantas embalagens cobrem o que falta, rateia o uso no custo e desconta as embalagens inteiras do orçamento; nunca multiplique preços por conta própria. Se não couber no orçamento restante, diga antes de seguir.
8. Quando gate.ready for verdadeiro e ela disser que quer o prato, grave a aceitação com recipe_update (accepted). Só então o prato pode ser precificado.

## Regras

1. O que a tool devolve como desconhecido é pergunta, nunca suposição.
2. Quando a tool recusa converter uma medida porque um item da despensa é contado em unidades e a receita pede peso ou volume, pergunte a ela o tamanho da embalagem e registre com pantry_amend. Só registre o que ela informou.
3. Ela nunca fica esperando por uma medida. Se ela diz "uso a olho", proponha uma quantidade razoável e siga: 5 g de sal ou tempero seco por preparo, 10 g de ervas frescas, 1 tablete de caldo, 50 g de cebola e 5 g de alho por leva de arroz ou de feijão, 15 ml de óleo. Diga o que assumiu para ela corrigir.
