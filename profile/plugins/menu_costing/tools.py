"""Tool boundary: parse arguments, call the domain, serialize results for the model."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from .domain.errors import DomainError
from .domain.ledger import Store
from .domain.models import (
    KitchenProfile,
    Menu,
    PantryAmendment,
    PantryItem,
    PurchaseInput,
    Recipe,
    RecipeInput,
)
from .domain.money import brl
from .domain.pantry import find_item, load_pantry
from .domain.pricing import cost_breakdown, pricing
from .domain.recipes import (
    carry_purchases,
    check_ingredients,
    evaluate_gate,
    plan_purchases,
    recipe_id,
)
from .domain.units import ConversionTable

TOOLSET = "menu_costing"
Handler = Callable[..., str]


class Settings(BaseModel):
    """Plugin settings as declared in config.yaml; nothing here has a default in code."""

    pantry_path: Path
    conversions_path: Path
    budget_brl: float = Field(ge=0)
    platform_fee: float = Field(ge=0, lt=1)
    margins: list[float] = Field(min_length=1)


@dataclass(frozen=True)
class Tool:
    name: str
    schema: dict[str, Any]
    handler: Handler


class PantryInventoryArgs(BaseModel):
    pass


class RecipeUpdateArgs(BaseModel):
    recipe_id: str
    liked: bool | None = Field(
        default=None, description="Ela gostou da receita e quer seguir com ela"
    )
    purchases: list[PurchaseInput] | None = Field(
        default=None,
        description=(
            "Embalagens confirmadas para o que falta; substitui a lista anterior e desfaz um "
            "aceite anterior, porque o custo mudou"
        ),
    )
    accepted: bool | None = Field(
        default=None,
        description="Ela aceitou o prato. Só é gravado com todos os bloqueios resolvidos",
    )


class DishPriceArgs(BaseModel):
    recipe_id: str
    margins: list[float] | None = Field(
        default=None, description="Margens dos cenários (0 a 1); sem isso, usa as do config"
    )
    chosen_price_brl: float | None = Field(
        default=None, gt=0, description="Preço que ela escolheu, para registrar na consulta"
    )


class ConsultationTools:
    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store
        self.table = ConversionTable.model_validate(
            yaml.safe_load(settings.conversions_path.read_text("utf-8"))
        )

    # -- pantry ---------------------------------------------------------------

    def pantry_inventory(self, args: PantryInventoryArgs, **kwargs: Any) -> dict[str, Any]:
        return {"items": self._pantry(), "budget": _budget(self._menu())}

    def pantry_amend(self, args: PantryAmendment, **kwargs: Any) -> dict[str, Any]:
        if not args.stated_by_cook:
            raise DomainError("Só registre uma correção que a cozinheira informou.")
        # Validated against the spreadsheet as it is, so a size can be corrected after being set.
        item = find_item(args.name, load_pantry(self.settings.pantry_path))
        if item is None:
            raise DomainError(f"Não existe {args.name!r} na despensa.")
        if (args.package_size is None) != (args.package_unit is None):
            raise DomainError("Informe package_size e package_unit juntos.")
        if args.package_size is not None and item.base_unit != "un":
            raise DomainError(
                f"{item.name} já está em {item.base_unit}; não há embalagem a informar."
            )
        others = [a for a in self.store.load_amendments() if a.name != item.name]
        current = next((a for a in self.store.load_amendments() if a.name == item.name), None)
        stated = args.model_dump(exclude_unset=True, exclude={"name"})
        merged = (current or args).model_copy(update={**stated, "name": item.name})
        self.store.save_amendments([*others, merged])
        return {"item": find_item(item.name, self._pantry())}

    # -- kitchen --------------------------------------------------------------

    def kitchen_profile(self, args: KitchenProfile, **kwargs: Any) -> dict[str, Any]:
        current = self._kitchen()
        patch = args.model_dump(exclude_unset=True)
        for facts in ("equipment", "techniques"):
            if facts in patch:
                patch[facts] = {**getattr(current, facts), **patch[facts]}
        profile: KitchenProfile = current.model_copy(update=patch)
        if patch:
            profile = self.store.save_kitchen(profile)
        return {"profile": profile, "missing": profile.missing()}

    # -- recipes --------------------------------------------------------------

    def recipe_register(self, args: RecipeInput, **kwargs: Any) -> dict[str, Any]:
        menu = self._menu()
        checks = check_ingredients(args, self._pantry(), self.table)
        rid = recipe_id(menu.recipes, args.url)
        previous = menu.recipes.get(rid)
        reopened = False
        if previous is None:
            recipe = Recipe(id=rid, session_id=_session_id(kwargs), **args.model_dump())
        else:
            # What she said about the dish survives a re-registration; the package counts are
            # sized again because the quantities may have changed. A different composition
            # reopens an acceptance, since the cost and the money committed changed with it.
            recipe = previous.model_copy(
                update={name: getattr(args, name) for name in RecipeInput.model_fields}
            )
            recipe.purchases = carry_purchases(previous.purchases, checks, self.table)
            reopened = previous.accepted and _recipe_input(previous) != args
            if reopened:
                recipe.accepted = False
                recipe.chosen_price_brl = None
        menu.recipes[rid] = recipe
        self.store.save_menu(menu)
        gate = evaluate_gate(recipe, self._kitchen(), checks)
        result: dict[str, Any] = {"recipe_id": rid, "ingredients": checks, "gate": gate}
        if reopened:
            result["note"] = "A composição mudou; o aceite e o preço anteriores foram desfeitos."
        return result

    def recipe_update(self, args: RecipeUpdateArgs, **kwargs: Any) -> dict[str, Any]:
        menu = self._menu()
        recipe = _recipe(menu, args.recipe_id)
        if args.liked is not None:
            recipe.liked = args.liked
        checks = check_ingredients(recipe, self._pantry(), self.table)
        if args.purchases is not None:
            unconfirmed = [p.ingredient for p in args.purchases if not p.confirmed_by_cook]
            if unconfirmed:
                raise DomainError(
                    "Só entram compras com preço confirmado pela cozinheira: "
                    + ", ".join(unconfirmed)
                )
            recipe.purchases = plan_purchases(args.purchases, checks, self.table)
        # An acceptance covers one list of purchases and her liking the dish; either changing
        # reopens the decision, and with it the money the dish had committed.
        reopened = recipe.accepted and (args.purchases is not None or args.liked is False)
        if reopened:
            recipe.accepted = False
        gate = evaluate_gate(recipe, self._kitchen(), checks)
        if args.accepted is not None:
            if args.accepted and not gate.ready:
                raise DomainError(
                    "O prato não pode ser aceito: " + "; ".join(b.message for b in gate.blockers)
                )
            purchases_brl = sum(p.total_brl for p in recipe.purchases)
            available = menu.remaining_brl() + (purchases_brl if recipe.accepted else 0.0)
            if args.accepted and purchases_brl > available:
                raise DomainError(
                    f"As compras somam {brl(purchases_brl)} "
                    f"e o orçamento restante é {brl(available)}."
                )
            recipe.accepted = args.accepted
        self.store.save_menu(menu)
        result = {
            "recipe_id": recipe.id,
            "gate": gate,
            "accepted": recipe.accepted,
            "budget": _budget(menu),
        }
        if reopened and not recipe.accepted:
            result["note"] = "O aceite anterior foi desfeito; confirme de novo com accepted."
        return result

    # -- pricing --------------------------------------------------------------

    def dish_price(self, args: DishPriceArgs, **kwargs: Any) -> dict[str, Any]:
        menu = self._menu()
        recipe = _recipe(menu, args.recipe_id)
        checks = check_ingredients(recipe, self._pantry(), self.table)
        if not recipe.accepted:
            gate = evaluate_gate(recipe, self._kitchen(), checks)
            pending = "; ".join(b.message for b in gate.blockers) or "falta ela aceitar o prato"
            raise DomainError(f"O prato ainda não foi aceito: {pending}.")
        cost = cost_breakdown(recipe, checks, self._pantry(), self.table)
        margins = args.margins or self.settings.margins
        prices = pricing(cost.cmv_portion_brl, self.settings.platform_fee, margins)
        if args.chosen_price_brl is not None:
            if args.chosen_price_brl < prices.floor_price_brl:
                raise DomainError(
                    f"{brl(args.chosen_price_brl)} fica abaixo do preço mínimo "
                    f"{brl(prices.floor_price_brl)}; ela perderia dinheiro."
                )
            recipe.chosen_price_brl = args.chosen_price_brl
            self.store.save_menu(menu)
        return {
            "recipe_id": recipe.id,
            "cost": cost,
            "pricing": prices,
            "chosen_price_brl": recipe.chosen_price_brl,
            "budget": _budget(menu),
        }

    # -- helpers --------------------------------------------------------------

    def _pantry(self) -> list[PantryItem]:
        return load_pantry(self.settings.pantry_path, self.store.load_amendments())

    def _menu(self) -> Menu:
        return self.store.load_menu(self.settings.budget_brl)

    def _kitchen(self) -> KitchenProfile:
        return self.store.load_kitchen() or KitchenProfile()


def _session_id(kwargs: dict[str, Any]) -> str:
    """Hermes passes the session id to every tool handler; a missing one is a wiring error."""
    return str(kwargs["session_id"])


def _recipe_input(recipe: Recipe) -> RecipeInput:
    return RecipeInput.model_validate(recipe.model_dump(include=set(RecipeInput.model_fields)))


def _recipe(menu: Menu, rid: str) -> Recipe:
    recipe = menu.recipes.get(rid)
    if recipe is None:
        raise DomainError(f"Não há receita {rid!r} no cardápio. Registre-a com recipe_register.")
    return recipe


def _budget(menu: Menu) -> dict[str, float]:
    return {
        "total_brl": menu.budget_brl,
        "committed_brl": menu.committed_brl(),
        "remaining_brl": menu.remaining_brl(),
    }


# ---------------------------------------------------------------------------
# Registration

_DESCRIPTIONS: dict[str, str] = {
    "pantry_inventory": (
        "Lista a despensa da Dona Maria com estoque e custo unitário derivados da planilha "
        "(custo = preço total pago ÷ quantidade comprada) e o orçamento restante para compras. "
        "Chame no início da consulta e sempre que precisar do nome exato de um item."
    ),
    "pantry_amend": (
        "Registra um fato sobre um item da despensa que a planilha não tem e a cozinheira "
        "informou: o tamanho da embalagem de um item contado em unidades, ou a correção do "
        "preço pago."
    ),
    "kitchen_profile": (
        "Lê ou atualiza o perfil da cozinha: bocas do fogão, equipamentos e técnicas (nome e sim "
        "ou não, somados ao que já está gravado), tempo por cozinhada e restrições. Chame sem "
        "argumentos para ler. Devolve em missing o que ainda falta para qualquer prato e em "
        "updated_at quando ela falou da cozinha pela última vez."
    ),
    "recipe_register": (
        "Registra uma receita candidata extraída de uma página real e a compara com a despensa e a "
        "cozinha. Devolve o que ela já tem, o que falta comprar e os bloqueios para aceitação. "
        "Registrar de novo a mesma URL atualiza a receita e mantém o que ela já disse sobre ela; "
        "se a composição de um prato aceito mudar, o aceite é desfeito e precisa ser confirmado "
        "de novo."
    ),
    "recipe_update": (
        "Atualiza uma receita com o que a cozinheira disse: se gostou, compras complementares "
        "com preço confirmado, e a aceitação do prato. A aceitação só é gravada com todos os "
        "bloqueios resolvidos e as compras dentro do orçamento; mudar as compras desfaz um "
        "aceite anterior."
    ),
    "dish_price": (
        "Calcula, para um prato aceito, o CMV por porção linha a linha, o preço mínimo e "
        "cenários de preço por margem, já com a taxa da plataforma. Recusa pratos não aceitos. "
        "Passe chosen_price_brl para registrar o preço que ela escolheu."
    ),
}


def build_tools(settings: Settings, store: Store) -> list[Tool]:
    tools = ConsultationTools(settings, store)
    bound: list[tuple[str, type[BaseModel], Callable[..., dict[str, Any]]]] = [
        ("pantry_inventory", PantryInventoryArgs, tools.pantry_inventory),
        ("pantry_amend", PantryAmendment, tools.pantry_amend),
        ("kitchen_profile", KitchenProfile, tools.kitchen_profile),
        ("recipe_register", RecipeInput, tools.recipe_register),
        ("recipe_update", RecipeUpdateArgs, tools.recipe_update),
        ("dish_price", DishPriceArgs, tools.dish_price),
    ]
    return [
        Tool(
            name=name,
            schema=tool_schema(name, _DESCRIPTIONS[name], model),
            handler=_guard(model, method),
        )
        for name, model, method in bound
    ]


def tool_schema(name: str, description: str, model: type[BaseModel]) -> dict[str, Any]:
    """Function schema with every $ref inlined, so it survives any provider adapter as is."""
    parameters = _inline(model.model_json_schema())
    parameters["additionalProperties"] = False
    return {"name": name, "description": description, "parameters": parameters}


def _inline(schema: dict[str, Any]) -> dict[str, Any]:
    definitions = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = definitions[node["$ref"].rsplit("/", 1)[-1]]
                return walk({**target, **{k: v for k, v in node.items() if k != "$ref"}})
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "title")}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    result: dict[str, Any] = walk(schema)
    return result


def _guard(model: type[BaseModel], method: Callable[..., dict[str, Any]]) -> Handler:
    """Expected failures become a result the model can act on; anything else propagates."""

    def handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            parsed = model.model_validate(args or {})
        except ValidationError as exc:
            return _dumps(
                {
                    "error": "Argumentos inválidos.",
                    "details": exc.errors(include_url=False, include_input=False),
                }
            )
        try:
            result = method(parsed, **kwargs)
        except DomainError as exc:
            return _dumps({"error": str(exc)})
        return _dumps(result)

    return handler


def _dumps(payload: Any) -> str:
    return json.dumps(_plain(payload), ensure_ascii=False)


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {k: _rounded(k, _plain(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def _rounded(key: str, value: Any) -> Any:
    """Amounts in reais are shown in cents and other quantities to four places; a unit cost per
    gram is left exact because rounding it would move the totals it is meant to reproduce."""
    if not isinstance(value, float) or key == "unit_cost_brl":
        return value
    return round(value, 2) if key.endswith("_brl") else round(value, 4)
