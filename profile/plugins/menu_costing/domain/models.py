"""Pydantic models shared by the tools (boundary) and the domain functions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

from .money import per_unit
from .units import BaseUnit, fold

# ---------------------------------------------------------------------------
# Pantry


class PantryItem(BaseModel):
    name: str
    row: int = Field(description="Linha do item nas duas abas da planilha")
    stock: float = Field(ge=0, description="Quantidade em estoque, na unidade da planilha")
    unit_text: str = Field(description="Unidade como escrita na planilha")
    base_unit: BaseUnit
    per_unit: float = Field(gt=0, description="Quantas unidades base tem uma unidade da planilha")
    purchased: float = Field(gt=0, description="Quantidade comprada, na unidade da planilha")
    total_paid_brl: float = Field(ge=0)

    @computed_field(description="Estoque na unidade base")  # type: ignore[prop-decorator]
    @property
    def stock_base(self) -> float:
        return self.stock * self.per_unit

    @computed_field(description="Custo de uma unidade base, em reais")  # type: ignore[prop-decorator]
    @property
    def unit_cost_brl(self) -> float:
        return self.total_paid_brl / (self.purchased * self.per_unit)

    @computed_field(description="Custo unitário legível: por kg, por L ou por un")  # type: ignore[prop-decorator]
    @property
    def unit_cost_display(self) -> str:
        return per_unit(self.unit_cost_brl, self.base_unit)


class PantryAmendment(BaseModel):
    """A fact about a pantry item that the cook stated and the spreadsheet lacks."""

    name: str = Field(description="Nome exato do item na despensa")
    package_size: float | None = Field(
        default=None, gt=0, description="Tamanho de uma unidade da planilha, em package_unit"
    )
    package_unit: Literal["g", "ml"] | None = None
    total_paid_brl: float | None = Field(
        default=None, ge=0, description="Preço total pago corrigido, se a planilha estiver errada"
    )
    stated_by_cook: bool = Field(
        description="Deve ser verdadeiro: só a cozinheira corrige a despensa"
    )


# ---------------------------------------------------------------------------
# Kitchen


class KitchenProfile(BaseModel):
    """What the statement asks the consultant to find out before proposing a dish.

    Three groups, as in the statement: equipment, skills, operational constraints. Names are
    free text the model chooses, matched case- and accent-insensitively. The stove is the one
    piece of equipment kept as a number, because it is the only one a recipe needs a quantity
    of (burners at the same time) and the only one the code compares.
    """

    burners: int | None = Field(default=None, ge=0, description="Bocas do fogão; 0 se não tem")
    equipment: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Equipamento além do fogão e se ela tem: forno, panela de pressão, air fryer, "
            "liquidificador..."
        ),
    )
    techniques: dict[str, bool] = Field(
        default_factory=dict, description="Técnica ou habilidade e se ela domina"
    )
    time_per_batch: str | None = Field(
        default=None, description="Tempo que ela tem para cada cozinhada, como ela disse"
    )
    notes: str | None = Field(
        default=None, description="Restrições operacionais: gás ou elétrico, geladeira, horários"
    )

    def missing(self) -> list[str]:
        """What the code itself needs to judge any dish; the rest is for the model to weigh."""
        return ["burners"] if self.burners is None else []

    def has(self, equipment: str) -> bool | None:
        return _lookup(self.equipment, equipment)

    def masters(self, technique: str) -> bool | None:
        return _lookup(self.techniques, technique)

    def owned(self) -> list[str]:
        return sorted(name for name, yes in self.equipment.items() if yes)

    def mastered(self) -> list[str]:
        return sorted(name for name, yes in self.techniques.items() if yes)


def _lookup(facts: dict[str, bool], name: str) -> bool | None:
    key = fold(name)
    return next((value for known, value in facts.items() if fold(known) == key), None)


# ---------------------------------------------------------------------------
# Recipes


class IngredientInput(BaseModel):
    name: str = Field(description="Nome do ingrediente como está na receita")
    quantity: float = Field(gt=0)
    unit: str = Field(description="Unidade como está na receita (g, ml, xícara, dente, un...)")
    pantry_item: str | None = Field(
        default=None, description="Nome exato do item correspondente na despensa, ou nulo se não há"
    )


class RecipeInput(BaseModel):
    title: str
    url: str = Field(description="Página de onde a receita foi extraída")
    yield_portions: int = Field(gt=0, description="Porções que a receita rende")
    ingredients: list[IngredientInput] = Field(min_length=1)
    equipment_required: list[str] = Field(
        default_factory=list,
        description=(
            "Equipamentos que o preparo usa além do fogão (forno, panela de pressão, air fryer, "
            "liquidificador...). O fogão entra em burners_needed."
        ),
    )
    burners_needed: int = Field(
        default=1, ge=0, description="Bocas do fogão usadas ao mesmo tempo; 0 para prato sem fogão"
    )
    techniques_required: list[str] = Field(
        min_length=1,
        description=(
            "Técnicas que o preparo exige, sempre ao menos o método de cocção "
            "(refogar, cozinhar na pressão, assar, fritar, desfiar, massa fresca...)"
        ),
    )
    per_portion_items: list[IngredientInput] = Field(
        default_factory=list,
        description=(
            "O que entra em cada porção vendida além do preparo da página: acompanhamentos, "
            "em quantidade por porção. A tool multiplica pelo rendimento."
        ),
    )

    @model_validator(mode="after")
    def _names_are_unique(self) -> RecipeInput:
        """Purchases and blockers refer to ingredients by name, so a name must mean one line."""
        seen: set[str] = set()
        for ingredient in [*self.ingredients, *self.per_portion_items]:
            key = fold(ingredient.name)
            if key in seen:
                raise ValueError(f"ingrediente repetido: {ingredient.name!r}")
            seen.add(key)
        return self


class PurchaseInput(BaseModel):
    """One package as sold at the market. The tool works out how many packages are needed."""

    ingredient: str = Field(description="Nome do ingrediente na receita")
    quantity: float = Field(gt=0, description="Conteúdo de uma embalagem")
    unit: str = Field(description="Unidade do conteúdo (g, ml, un, xícara...)")
    price_brl: float = Field(ge=0, description="Preço de uma embalagem")
    confirmed_by_cook: bool = Field(description="Deve ser verdadeiro: só entra preço confirmado")


class Purchase(PurchaseInput):
    packages: int = Field(ge=1, description="Embalagens necessárias para um lote, calculado")

    @computed_field(description="Gasto total com este item")  # type: ignore[prop-decorator]
    @property
    def total_brl(self) -> float:
        return self.packages * self.price_brl


class Recipe(RecipeInput):
    id: str
    session_id: str = Field(description="Sessão em que a receita foi registrada")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    liked: bool | None = None
    purchases: list[Purchase] = Field(default_factory=list)
    accepted: bool = False
    chosen_price_brl: float | None = None


class Menu(BaseModel):
    """The launch menu: one ledger for the cook, shared by every conversation about it."""

    budget_brl: float = Field(ge=0)
    recipes: dict[str, Recipe] = Field(default_factory=dict)

    def committed_brl(self) -> float:
        return sum(p.total_brl for r in self.recipes.values() if r.accepted for p in r.purchases)

    def remaining_brl(self) -> float:
        return self.budget_brl - self.committed_brl()


# ---------------------------------------------------------------------------
# Reports returned to the model


class IngredientCheck(BaseModel):
    name: str
    pantry_item: str | None
    scope: Literal["receita", "porcao"] = Field(
        default="receita", description="Da receita da página ou adicionado a cada porção"
    )
    needed: float = Field(
        description=(
            "Quantidade necessária para um lote, na unidade base do item da despensa; na "
            "unidade da receita quando ela não tem o item"
        )
    )
    unit: str
    conversion: str
    stock: float | None = Field(
        description="Estoque na unidade base, ou nulo se não está na despensa"
    )
    status: Literal["suficiente", "insuficiente", "ausente"]
    shortfall: float = Field(description="Quanto falta comprar para um lote")


class Blocker(BaseModel):
    code: str
    message: str


class GateReport(BaseModel):
    ready: bool
    blockers: list[Blocker]
    purchases: list[Purchase] = Field(
        default_factory=list, description="Compras com o número de embalagens para um lote"
    )


class CostLine(BaseModel):
    ingredient: str
    source: Literal["despensa", "compra"]
    quantity: float
    unit: str
    unit_cost_brl: float = Field(description="Por unidade base, sem arredondar; para conferência")
    unit_cost_display: str = Field(description="Custo unitário legível, para dizer a ela")
    cost_brl: float
    reference: str = Field(description="Linha da planilha ou compra que originou o custo")


class CostBreakdown(BaseModel):
    yield_portions: int
    lines: list[CostLine]
    cmv_batch_brl: float
    cmv_portion_brl: float
    purchases_brl: float = Field(description="Gasto real nas embalagens compradas para o lote")


class PriceScenario(BaseModel):
    margin: float = Field(description="Margem sobre o que a cozinheira recebe")
    price_brl: float
    fee_brl: float
    net_brl: float
    profit_brl: float


class Pricing(BaseModel):
    platform_fee: float
    cmv_portion_brl: float
    floor_price_brl: float = Field(description="Abaixo disso ela perde dinheiro")
    scenarios: list[PriceScenario]
