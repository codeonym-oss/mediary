# Benchmarks

What mediary adds to a call, measured against doing the same work without it. For a handler that talks to a database or another service, which takes milliseconds, the few microseconds a `send` costs don't show.

## Results

Measured on mediary 0.3.1 (with the changes up to 0.4.0), CPython 3.11.13, Linux 7.0, AMD Ryzen 5 3500U (a 2019 laptop CPU), on asyncio. Each time is per operation, the best of 7 runs.

| Case | mediary | Baseline | Baseline time | Overhead |
|---|--:|---|--:|--:|
| send, 0 behaviors | 2.73 µs | handler called directly | 140 ns | +2.59 µs |
| send, 1 behavior | 4.18 µs | handler called directly | 140 ns | +4.04 µs |
| send, 5 behaviors | 9.58 µs | handler called directly | 140 ns | +9.44 µs |
| send, 10 behaviors | 17.18 µs | handler called directly | 140 ns | +17.04 µs |
| publish, 1 handler, sequential | 5.65 µs | awaited in turn | 281 ns | +5.37 µs |
| publish, 1 handler, concurrent | 38.20 µs | tasks in a TaskGroup | 29.31 µs | +8.89 µs |
| publish, 5 handlers, sequential | 15.46 µs | awaited in turn | 749 ns | +14.71 µs |
| publish, 5 handlers, concurrent | 73.20 µs | tasks in a TaskGroup | 56.26 µs | +16.95 µs |
| publish, 20 handlers, sequential | 45.44 µs | awaited in turn | 2.61 µs | +42.84 µs |
| publish, 20 handlers, concurrent | 178.18 µs | tasks in a TaskGroup | 112.42 µs | +65.76 µs |
| publish, 20 handlers, concurrent, limit 5 | 114.53 µs | tasks in a TaskGroup | 112.33 µs | +2.20 µs |
| stream of 1000 items | 395.17 µs | generator iterated directly | 101.96 µs | +293.21 µs |
| scan of 300 handlers, first | 34.03 ms | importing its modules | 25.53 ms | +8.50 ms |
| scan of 300 handlers, already imported | 10.07 ms | | | |

What the numbers say:

- **`send` costs about 3 µs, plus about 1.4 µs per behavior.** That's the pipeline, whose shape is computed once per message type and then cached.
- **`publish` costs about 2 µs per handler** on top of a fixed cost, sequentially or concurrently. `Concurrent` is dominated by the task group's own cost, which the baseline pays too. With a `limit` of 5 it starts 5 tasks instead of 20, which makes it about as fast as that baseline.
- **A stream adds under 0.3 µs per item.** Each item passes through the `Stream` and the layer that closes the pipeline cleanly.
- **`scan` is a startup cost:** about 30 µs per handler beyond importing its module, once.

## Rerun them

From a clone of the repository:

```sh
uv run python benchmarks/bench.py          # the full suite, about a minute and a half
uv run python benchmarks/bench.py --quick  # every case, briefly: checks they still run
```

It prints the machine and versions, then this table in Markdown. The numbers depend on the machine, so compare runs on the same one: before and after a change, say. CI runs `--quick` on each pull request, which fails only if a case errors, never because of its numbers.
