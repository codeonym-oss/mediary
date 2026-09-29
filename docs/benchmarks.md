# Benchmarks

What mediary adds to a call, measured against doing the same work without it. For a handler that talks to a database or another service, which takes milliseconds, the few microseconds a `send` costs don't show.

## Results

Measured on mediary 0.2.1 (with the changes up to 0.3.0), CPython 3.11.13, Linux 7.0, AMD Ryzen 5 3500U (a 2019 laptop CPU), on asyncio. Each time is per operation, the best of 7 runs.

| Case | mediary | Baseline | Baseline time | Overhead |
|---|--:|---|--:|--:|
| send, 0 behaviors | 2.81 µs | handler called directly | 140 ns | +2.67 µs |
| send, 1 behavior | 4.33 µs | handler called directly | 140 ns | +4.19 µs |
| send, 5 behaviors | 9.68 µs | handler called directly | 140 ns | +9.54 µs |
| send, 10 behaviors | 16.44 µs | handler called directly | 140 ns | +16.30 µs |
| publish, 1 handler, sequential | 5.76 µs | awaited in turn | 263 ns | +5.50 µs |
| publish, 1 handler, concurrent | 37.11 µs | tasks in a TaskGroup | 25.51 µs | +11.60 µs |
| publish, 5 handlers, sequential | 14.49 µs | awaited in turn | 762 ns | +13.72 µs |
| publish, 5 handlers, concurrent | 66.25 µs | tasks in a TaskGroup | 41.72 µs | +24.53 µs |
| publish, 20 handlers, sequential | 44.82 µs | awaited in turn | 2.40 µs | +42.41 µs |
| publish, 20 handlers, concurrent | 171.70 µs | tasks in a TaskGroup | 100.96 µs | +70.74 µs |
| stream of 1000 items | 362.71 µs | generator iterated directly | 92.59 µs | +270.11 µs |
| scan of 300 handlers, first | 30.09 ms | importing its modules | 20.94 ms | +9.15 ms |
| scan of 300 handlers, already imported | 8.26 ms | | | |

What the numbers say:

- **`send` costs about 3 µs, plus about 1.4 µs per behavior.** That's the pipeline, whose shape is computed once per message type and then cached.
- **`publish` costs about 2 µs per handler** on top of a fixed cost, sequentially or concurrently. `Concurrent` is dominated by the task group's own cost, which the baseline pays too.
- **A stream adds under 0.3 µs per item.** Each item passes through the `Stream` and the layer that closes the pipeline cleanly.
- **`scan` is a startup cost:** about 30 µs per handler beyond importing its module, once.

## Rerun them

From a clone of the repository:

```sh
uv run python benchmarks/bench.py          # the full suite, about a minute and a half
uv run python benchmarks/bench.py --quick  # every case, briefly: checks they still run
```

It prints the machine and versions, then this table in Markdown. The numbers depend on the machine, so compare runs on the same one: before and after a change, say. CI runs `--quick` on each pull request, which fails only if a case errors, never because of its numbers.
