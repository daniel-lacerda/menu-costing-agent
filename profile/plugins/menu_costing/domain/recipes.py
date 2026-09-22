"""Compare a recipe with the pantry and the kitchen, and decide whether it may be accepted."""

from __future__ import annotations

import math

from .errors import DomainError
from .models import (
    Blocker,
    GateReport,
    IngredientCheck,
    IngredientInput,
    KitchenProfile,
    PantryItem,
    Purchase,
    PurchaseInput,
    Recipe,
    RecipeInput,
)
from .pantry import find_item
from .units import ConversionTable, convert_between, convert_measure, fold


def check_ingredients(
    recipe: RecipeInput, pantry: list[PantryItem], table: ConversionTable
) -> list[IngredientCheck]:
    lines = [(ingredient, 1, "receita") for ingredient in recipe.ingredients]
    lines += [(item, recipe.yield_portions, "porcao") for item in recipe.per_portion_items]
    checks: list[IngredientCheck] = []
    for ingredient, batches, scope in lines:
        scaled = ingredient.quantity * batches
        if ingredient.pantry_item is None:
            checks.append(
                IngredientCheck(
                    name=ingredient.name,
                    pantry_item=None,
                    scope=scope,
                    needed=scaled,
                    unit=ingredient.unit,
                    conversion=_scaled_note(ingredient, batches, f"{scaled:g} {ingredient.unit}"),
                    stock=None,
                    status="missing",
                    shortfall=scaled,
                )
            )
            continue
        item = find_item(ingredient.pantry_item, pantry)
        if item is None:
            raise DomainError(
                f"Não existe {ingredient.pantry_item!r} na despensa. Use o nome exato devolvido "
                "por pantry_inventory, ou pantry_item nulo se o ingrediente não está lá."
            )
        converted = convert_measure(scaled, ingredient.unit, item.base_unit, item.name, table)
        shortfall = max(0.0, converted.quantity - item.stock_base)
        checks.append(
            IngredientCheck(
                name=ingredient.name,
                pantry_item=item.name,
                scope=scope,
                needed=converted.quantity,
                unit=item.base_unit,
                conversion=_scaled_note(ingredient, batches, converted.note),
                stock=item.stock_base,
                status="have" if shortfall == 0 else "short",
                shortfall=shortfall,
            )
        )
    return checks


def _scaled_note(ingredient: IngredientInput, portions: int, converted_note: str) -> str:
    """Show the cook the per-portion quantity that produced a batch total."""
    if portions == 1:
        return converted_note
    per_portion = f"{ingredient.quantity:g} {ingredient.unit} por porção"
    return f"{per_portion} x {portions} porções: {converted_note}"


def purchase_for(ingredient: str, purchases: list[Purchase]) -> Purchase | None:
    key = fold(ingredient)
    return next((p for p in purchases if fold(p.ingredient) == key), None)


def package_in(purchase: PurchaseInput, check: IngredientCheck, table: ConversionTable) -> float:
    """One package's content expressed in the unit the ingredient need is stated in."""
    if fold(purchase.unit) == fold(check.unit):
        return purchase.quantity
    if check.pantry_item is not None:
        return convert_measure(
            purchase.quantity,
            purchase.unit,
            check.unit,  # type: ignore[arg-type]
            check.pantry_item,
            table,
        ).quantity
    return convert_between(purchase.quantity, purchase.unit, check.unit, table)


def plan_purchases(
    purchases: list[PurchaseInput], checks: list[IngredientCheck], table: ConversionTable
) -> list[Purchase]:
    """Attach to each purchase the number of packages that covers the batch shortfall."""
    planned: list[Purchase] = []
    for purchase in purchases:
        check = next((c for c in checks if fold(c.name) == fold(purchase.ingredient)), None)
        if check is None:
            raise DomainError(f"{purchase.ingredient!r} não é um ingrediente desta receita.")
        if check.shortfall == 0:
            raise DomainError(
                f"Não falta {purchase.ingredient!r} para um lote; não há o que comprar."
            )
        packages = math.ceil(check.shortfall / package_in(purchase, check, table))
        planned.append(Purchase(**purchase.model_dump(), packages=packages))
    return planned


def carry_purchases(
    previous: list[Purchase], checks: list[IngredientCheck], table: ConversionTable
) -> list[Purchase]:
    """Keep confirmed packages that the re-registered recipe still needs, sized for it again."""
    still_short = {fold(c.name) for c in checks if c.shortfall > 0}
    kept = [
        PurchaseInput(**p.model_dump(exclude={"packages", "total_brl"}))
        for p in previous
        if fold(p.ingredient) in still_short
    ]
    return plan_purchases(kept, checks, table)


def evaluate_gate(
    recipe: Recipe, profile: KitchenProfile, checks: list[IngredientCheck], table: ConversionTable
) -> GateReport:
    """Everything the statement requires before the cook commits to a dish."""
    blockers: list[Blocker] = []

    for field in profile.missing_required():
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
    on_file = ", ".join(profile.mastered()) or "nenhuma"
    for technique in recipe.techniques_required:
        mastered = known.get(fold(technique))
        if mastered is None:
            blockers.append(
                Blocker(
                    code=f"technique_unknown:{technique}",
                    message=(
                        f"Falta saber se ela domina: {technique}. "
                        f"Técnicas já confirmadas por ela: {on_file}."
                    ),
                )
            )
        elif not mastered:
            blockers.append(
                Blocker(
                    code=f"technique_missing:{technique}", message=f"Ela não domina: {technique}."
                )
            )

    for check in checks:
        if check.shortfall > 0 and purchase_for(check.name, recipe.purchases) is None:
            blockers.append(
                Blocker(
                    code=f"purchase_needed:{check.name}",
                    message=(
                        f"Falta comprar {check.shortfall:g} {check.unit} de {check.name}, "
                        "com a embalagem e o preço confirmados."
                    ),
                )
            )

    return GateReport(ready=not blockers, blockers=blockers, purchases=recipe.purchases)


def recipe_id(existing: dict[str, Recipe], url: str) -> str:
    for recipe in existing.values():
        if recipe.url == url:
            return recipe.id
    return f"r{len(existing) + 1}"
