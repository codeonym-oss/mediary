# Caching queries

Cache the results of expensive queries in a behavior, keyed by the query itself. Frozen dataclasses are hashable and compare by value, so equal queries share an entry.

Which queries are cached, and for how long, is declared on the query, by a `cache_for` attribute that a `Protocol` matches:

```python
import time
from dataclasses import dataclass
from typing import ClassVar, Protocol

from mediary import Mediator, Next
from mediary.cqrs import Query, query


class Cached(Protocol):
    cache_for: ClassVar[float]  # seconds


class QueryCache:
    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.entries: dict[object, tuple[float, object]] = {}

    async def handle(self, query: Cached, next: Next[object]) -> object:
        now = self.clock()
        hit = self.entries.get(query)
        if hit is not None and hit[0] > now:
            return hit[1]
        result = await next()
        self.entries[query] = (now + query.cache_for, result)
        return result

    def invalidate(self, query_type: type) -> None:
        self.entries = {q: e for q, e in self.entries.items() if type(q) is not query_type}


@query
@dataclass(frozen=True)
class GetExchangeRate(Query[float]):
    currency: str
    cache_for: ClassVar[float] = 60


calls = []


async def get_exchange_rate(query: GetExchangeRate) -> float:
    calls.append(query.currency)
    return 1.08


now = 0.0
cache = QueryCache(clock=lambda: now)

mediator = Mediator()
mediator.register(GetExchangeRate, get_exchange_rate)
mediator.use(cache, kinds={"query"})  # one instance, shared by every send

await mediator.send(GetExchangeRate("EUR"))
await mediator.send(GetExchangeRate("EUR"))  # from the cache
assert calls == ["EUR"]

now = 61.0  # a minute later, the entry has expired
await mediator.send(GetExchangeRate("EUR"))
assert calls == ["EUR", "EUR"]
```

Notes:

- `use(cache)` adds the configured instance, so the cache lives as long as the mediator. A class behavior would be resolved — and emptied — on every send.
- Commands that change what a query reads should invalidate it: call `cache.invalidate(GetExchangeRate)` from their handler, or from a behavior on `kinds={"command"}`.
- In production, back the cache with Redis or similar, and bound its size; the logic stays in this one behavior.
- Only cache queries: `kinds={"query"}` keeps the behavior off commands, whatever attributes they have.
