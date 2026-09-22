"""Conversation quality as a binary rubric: each criterion is answered yes or no with evidence.

Binary criteria summed are more reliable from a model judge than a single 0 to 5 grade, and each
answer carries the quote that decided it, so a reviewer can disagree with the judge on a fact.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

JUDGE_MODEL = "gpt-5.6-terra"

CRITERIA: dict[str, str] = {
    "max_three_questions": "Nenhuma mensagem da consultora faz mais de três perguntas.",
    "prices_proposed_not_asked": (
        "Para ingredientes que faltam comprar, a consultora propõe uma embalagem e um valor para "
        "a Dona Maria confirmar; nunca pergunta 'quanto custa' sem propor. O preço de venda não "
        "conta aqui: esse ela deve escolher."
    ),
    "plain_language": (
        "A linguagem é de conversa com uma cozinheira: sem termos técnicos sem explicação; "
        "margem e CMV são explicados quando aparecem."
    ),
    "recipes_have_link_and_yield": (
        "Toda receita apresentada traz o link e quantas porções rende."
    ),
    "numbers_are_traced": (
        "Ao dar o preço, a consultora mostra de onde veio cada número: custo por ingrediente, "
        "taxa da plataforma e preço mínimo. Se a conversa não chegou ao preço, responda sim."
    ),
    "no_early_closing": (
        "A consultora não fecha um prato antes de confirmar cozinha, técnicas e compras, mesmo "
        "quando a Dona Maria pede para fechar logo."
    ),
    "off_topic_declined_briefly": (
        "Pedidos fora do assunto são recusados em uma ou duas frases e a conversa volta ao "
        "cardápio. Se não houve pedido fora do assunto, responda sim."
    ),
    "nothing_assumed": (
        "Nada sobre a cozinha, as técnicas ou os gostos dela foi assumido sem perguntar ou "
        "confirmar. Fatos da planilha (despensa, orçamento) e fatos listados como já "
        "registrados em conversas anteriores não contam como assunção."
    ),
    "decision_is_hers": (
        "A escolha do prato e do preço ficou explicitamente com a Dona Maria. Se a conversa "
        "não chegou ao preço, avalie só a escolha do prato."
    ),
    "no_repeated_questions": (
        "A consultora não perguntou de novo algo que a Dona Maria já tinha dito."
    ),
}


class Verdict(BaseModel):
    criterion: str
    passed: bool
    evidence: str = Field(description="Trecho ou fato do transcript que decidiu a resposta")


class RubricResult(BaseModel):
    verdicts: list[Verdict]

    @property
    def score(self) -> float:
        return sum(v.passed for v in self.verdicts) / len(self.verdicts)


def transcript_text(turns: list[dict[str, Any]], cook_transcript: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for entry in cook_transcript:
        lines.append(f"[{entry['role']}] {entry['content']}")
    return "\n\n".join(lines)


def judge(client: OpenAI, transcript: str, known_facts: str = "") -> RubricResult:
    schema = {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "criterion": {"type": "string", "enum": list(CRITERIA)},
                        "passed": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["criterion", "passed", "evidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    }
    rubric = "\n".join(f"- {key}: {text}" for key, text in CRITERIA.items())
    response = client.responses.create(
        model=JUDGE_MODEL,
        instructions=(
            "Você avalia a conversa entre uma consultora de cardápio e a Dona Maria, uma "
            "cozinheira simples. Para cada critério da rubrica responda passed verdadeiro ou "
            "falso, com uma evidência curta tirada do transcript. Seja rigoroso: na dúvida, "
            "falso. Responda com um veredito para cada critério, exatamente uma vez cada."
        ),
        input=(
            f"Rubrica:\n{rubric}\n\nFatos que a consultora já tinha (planilha da despensa e "
            f"conversas anteriores), que não contam como assunção:\n{known_facts or 'nenhum'}"
            f"\n\nTranscript:\n{transcript}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "rubric",
                "schema": schema,
                "strict": True,
            }
        },
    )
    payload = json.loads(response.output_text)
    return RubricResult.model_validate(payload)
