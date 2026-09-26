# Validation

Check requests before their handler runs, in one behavior, instead of at the top of every handler.

## Requests that validate themselves

A `Protocol` makes validation opt-in by shape: every request with a `validate` method is checked, and no other.

```python
from dataclasses import dataclass
from typing import Protocol

from mediary import Mediator, Next, Returns, behavior, request


class Validates(Protocol):
    def validate(self) -> list[str]:
        """Return what is wrong with this request, if anything."""
        ...


class Invalid(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@behavior(order=-20)  # outside transactions, so nothing is opened for a bad request
async def validate(request: Validates, next: Next[object]) -> object:
    problems = request.validate()
    if problems:
        raise Invalid(problems)
    return await next()


@request
@dataclass
class PlaceOrder(Returns[int]):
    item: str
    quantity: int

    def validate(self) -> list[str]:
        problems = []
        if not self.item:
            problems.append("item is required")
        if self.quantity < 1:
            problems.append("quantity must be at least 1")
        return problems


async def place_order(request: PlaceOrder) -> int:
    return 42


mediator = Mediator()
mediator.register(PlaceOrder, place_order)
mediator.use(validate)

assert await mediator.send(PlaceOrder("book", 2)) == 42
try:
    await mediator.send(PlaceOrder("", 0))
except Invalid as error:
    problems = error.problems
assert problems == ["item is required", "quantity must be at least 1"]
```

Map `Invalid` to a 422 response once, in your web framework's exception handler.

## Checks that need dependencies

Pydantic models validate their fields when they are built, so a request that exists has valid fields. Checks against the world — is the item sold here? may this user do it? — still belong in a behavior, often one with dependencies:

```python
class Catalog:
    items = {"book", "pen"}


class InCatalog(Protocol):
    item: str


@behavior(order=-20)
async def check_catalog(request: InCatalog, next: Next[object], catalog: Catalog) -> object:
    if request.item not in catalog.items:
        raise Invalid([f"{request.item} isn't sold here"])
    return await next()


mediator = Mediator()
mediator.register(PlaceOrder, place_order)
mediator.use(check_catalog)

try:
    await mediator.send(PlaceOrder("lamp", 1))
except Invalid as error:
    problems = error.problems
assert problems == ["lamp isn't sold here"]
```

`Catalog` comes from the mediator's [resolver](../guide/dependency-injection.md), like any dependency.
