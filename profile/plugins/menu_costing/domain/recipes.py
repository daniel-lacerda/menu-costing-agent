"""Compare a recipe with the pantry and the kitchen, and decide whether it may be accepted."""

from __future__ import annotations

from .errors import DomainError
from .models import (
    Blocker,
    GateReport,
    IngredientCheck,
    KitchenProfile,
    PantryItem,
    Purchase,
    Recipe,
    RecipeInput,
)
from .pantry import find_item
from .units import ConversionTable, convert_measure, fold


def check_ingredients(
    recipe: RecipeInput, pantry: list[PantryItem], table: ConversionTable
) -> list[IngredientCheck]:
    checks: list[IngredientCheck] = []
    for ingredient in recipe.ingredients:
        if ingredient.pantry_item is None:
            checks.append(
                IngredientCheck(
                    name=ingredient.name,
                    pantry_item=None,
                    needed=ingredient.quantity,
                    unit=ingredient.unit,
                    conversion=f"{ingredient.quantity:g} {ingredient.unit}",
                    stock=None,
                    status="missing",
                    shortfall=ingredient.quantity,
                )
            )
            continue
        item = find_item(ingredient.pantry_item, pantry)
        if item is None:
            raise DomainError(
                f"Não existe {ingredient.pantry_item!r} na despensa. Use o nome exato devolvido "
                "por pantry_inventory, ou pantry_item nulo se o ingrediente não está lá."
            )
        converted = convert_measure(
            ingredient.quantity, ingredient.unit, item.base_unit, item.name, table
        )
        shortfall = max(0.0, converted.quantity - item.stock_base)
        checks.append(
            IngredientCheck(
                name=ingredient.name,
                pantry_item=item.name,
                needed=converted.quantity,
                unit=item.base_unit,
                conversion=converted.note,
                stock=item.stock_base,
                status="have" if shortfall == 0 else "short",
                shortfall=shortfall,
            )
        )
    return checks


def purchase_for(ingredient: str, purchases: list[Purchase]) -> Purchase | None:
    key = fold(ingredient)
    return next((p for p in purchases if fold(p.ingredient) == key), None)


def purchase_quantity_in(
    purchase: Purchase, check: IngredientCheck, table: ConversionTable
) -> float:
    """Purchased quantity expressed in the unit the ingredient need is stated in."""
    if fold(purchase.unit) == fold(check.unit):
        return purchase.quantity
    if check.unit not in ("g", "ml", "un"):
        raise DomainError(
            f"A compra de {purchase.ingredient} está em {purchase.unit!r} e a receita em "
            f"{check.unit!r}. Registre a compra na mesma unidade da receita."
        )
    item_name = check.pantry_item or check.name
    return convert_measure(purchase.quantity, purchase.unit, check.unit, item_name, table).quantity  # type: ignore[arg-type]


def evaluate_gate(
    recipe: Recipe, profile: KitchenProfile, checks: list[IngredientCheck], table: ConversionTable
) -> GateReport:
    """Everything the statement requires before the cook commits to a dish."""
    blockers: list[Blocker] = []

    for field in profile.missing():
        blockers.append(Blocker(code=f"kitchen_unknown:{field}", message=f"Falta saber: {field}."))

    if recipe.liked is None:
        blockers.append(Blocker(code="liked_unknown", message="Ela ainda não disse se gostou."))
    elif not recipe.liked:
        blockers.append(Blocker(code="not_liked", message="Ela não gostou desta receita."))

    for equipment in recipe.equipment_required:
        has = profile.has(equipment)
        if has is None:
            blockers.append(
                Blocker(
                    code=f"equipment_unknown:{equipment}",
                    message=f"Falta saber se ela tem {equipment}.",
                )
            )
        elif not has:
            blockers.append(
                Blocker(code=f"equipment_missing:{equipment}", message=f"Ela não tem {equipment}.")
            )
    if profile.burners is not None and recipe.burners_needed > profile.burners:
        blockers.append(
            Blocker(
                code="burners_insufficient",
                message=(
                    f"A receita usa {recipe.burners_needed} bocas e o fogão tem {profile.burners}."
                ),
            )
        )

    known = {fold(name): mastered for name, mastered in profile.techniques.items()}
    for technique in recipe.techniques_required:
        mastered = known.get(fold(technique))
        if mastered is None:
            blockers.append(
                Blocker(
                    code=f"technique_unknown:{technique}",
                    message=f"Falta saber se ela domina: {technique}.",
                )
            )
        elif not mastered:
            blockers.append(
                Blocker(
                    code=f"technique_missing:{technique}", message=f"Ela não domina: {technique}."
                )
            )

    for check in checks:
        if check.shortfall <= 0:
            continue
        purchase = purchase_for(check.name, recipe.purchases)
        if purchase is None:
            blockers.append(
                Blocker(
                    code=f"purchase_needed:{check.name}",
                    message=(
                        f"Falta comprar {check.shortfall:g} {check.unit} de {check.name}, "
                        "com preço confirmado."
                    ),
                )
            )
            continue
        bought = purchase_quantity_in(purchase, check, table)
        if bought < check.shortfall:
            blockers.append(
                Blocker(
                    code=f"purchase_insufficient:{check.name}",
                    message=(
                        f"A compra de {check.name} cobre {bought:g} {check.unit}, "
                        f"mas faltam {check.shortfall:g}."
                    ),
                )
            )

    return GateReport(ready=not blockers, blockers=blockers)


def recipe_id(existing: dict[str, Recipe], url: str) -> str:
    for recipe in existing.values():
        if recipe.url == url:
            return recipe.id
    return f"r{len(existing) + 1}"
