"""Pydantic models shared by the tools (boundary) and the domain functions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, computed_field

from .units import BaseUnit

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
        scale, label = {"g": (1000, "kg"), "ml": (1000, "L"), "un": (1, "un")}[self.base_unit]
        return f"R$ {self.unit_cost_brl * scale:.2f}/{label}"

    @computed_field(  # type: ignore[prop-decorator]
        description="Verdadeiro quando o item é contado e o tamanho da embalagem é desconhecido"
    )
    @property
    def package_size_unknown(self) -> bool:
        return self.base_unit == "un"


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

Equipment = Literal[
    "fogao",
    "forno",
    "panela_de_pressao",
    "air_fryer",
    "liquidificador",
    "batedeira",
    "micro_ondas",
    "freezer",
]


class KitchenProfile(BaseModel):
    burners: int | None = Field(default=None, ge=0, description="Bocas do fogão (0 = sem fogão)")
    oven: bool | None = Field(default=None, description="Tem forno")
    pressure_cooker: bool | None = Field(default=None, description="Tem panela de pressão")
    air_fryer: bool | None = Field(default=None, description="Tem air fryer")
    blender: bool | None = Field(default=None, description="Tem liquidificador")
    mixer: bool | None = Field(default=None, description="Tem batedeira")
    microwave: bool | None = Field(default=None, description="Tem micro-ondas")
    freezer: bool | None = Field(default=None, description="Tem freezer")
    fuel: Literal["gas", "eletrico", "ambos"] | None = Field(
        default=None, description="Fogão a gás, elétrico ou ambos"
    )
    fridge_space: Literal["pequeno", "medio", "grande"] | None = Field(
        default=None, description="Espaço livre na geladeira"
    )
    time_per_batch: Literal["ate_1h", "de_1h_a_2h", "mais_de_2h"] | None = Field(
        default=None, description="Tempo que ela tem para cada cozinhada"
    )
    techniques: dict[str, bool] = Field(
        default_factory=dict, description="Técnica culinária e se ela domina"
    )
    notes: str | None = Field(default=None, description="Outras limitações ditas por ela")

    REQUIRED: ClassVar[frozenset[str]] = frozenset(
        {
            "burners",
            "oven",
            "pressure_cooker",
            "air_fryer",
            "blender",
            "fuel",
            "fridge_space",
            "time_per_batch",
        }
    )

    def missing(self) -> list[str]:
        return sorted(name for name in self.REQUIRED if getattr(self, name) is None)

    def has(self, equipment: Equipment) -> bool | None:
        if equipment == "fogao":
            return None if self.burners is None else self.burners > 0
        value: bool | None = getattr(self, _EQUIPMENT_FIELD[equipment])
        return value


_EQUIPMENT_FIELD: dict[Equipment, str] = {
    "fogao": "burners",
    "forno": "oven",
    "panela_de_pressao": "pressure_cooker",
    "air_fryer": "air_fryer",
    "liquidificador": "blender",
    "batedeira": "mixer",
    "micro_ondas": "microwave",
    "freezer": "freezer",
}


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
    equipment_required: list[Equipment] = Field(default_factory=list)
    burners_needed: int = Field(default=1, ge=0, description="Bocas usadas ao mesmo tempo")
    techniques_required: list[str] = Field(
        default_factory=list, description="Técnicas que a receita exige (ex.: massa fresca)"
    )
    per_portion_items: list[IngredientInput] = Field(
        default_factory=list,
        description=(
            "O que entra em cada porção vendida além do preparo da página: acompanhamentos e "
            "embalagem, em quantidade por porção. A tool multiplica pelo rendimento."
        ),
    )


class Purchase(BaseModel):
    ingredient: str = Field(description="Nome do ingrediente na receita")
    quantity: float = Field(gt=0, description="Quantidade comprada")
    unit: str = Field(description="Unidade da compra, na mesma dimensão da receita")
    price_brl: float = Field(ge=0, description="Preço da compra")
    confirmed_by_cook: bool = Field(description="Deve ser verdadeiro: só entra preço confirmado")


class Recipe(RecipeInput):
    id: str
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    liked: bool | None = None
    purchases: list[Purchase] = Field(default_factory=list)
    accepted: bool = False
    chosen_price_brl: float | None = None


class Consultation(BaseModel):
    session_id: str
    budget_brl: float = Field(ge=0)
    recipes: dict[str, Recipe] = Field(default_factory=dict)

    def committed_brl(self) -> float:
        return sum(p.price_brl for r in self.recipes.values() if r.accepted for p in r.purchases)

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
    needed: float = Field(description="Quantidade necessária para um lote, na unidade base")
    unit: str
    conversion: str
    stock: float | None = Field(
        description="Estoque na unidade base, ou nulo se não está na despensa"
    )
    status: Literal["have", "short", "missing"]
    shortfall: float = Field(description="Quanto falta comprar para um lote")


class Blocker(BaseModel):
    code: str
    message: str


class GateReport(BaseModel):
    ready: bool
    blockers: list[Blocker]


class CostLine(BaseModel):
    ingredient: str
    source: Literal["despensa", "compra"]
    quantity: float
    unit: str
    unit_cost_brl: float
    cost_brl: float
    reference: str = Field(description="Linha da planilha ou compra que originou o custo")


class CostBreakdown(BaseModel):
    yield_portions: int
    lines: list[CostLine]
    cmv_batch_brl: float
    cmv_portion_brl: float


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
