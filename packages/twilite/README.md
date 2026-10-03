# twilite

Driver and simulator for the Swisstrace twilite coincidence counter. Pure Python,
standard library only, no Qt.

```python
from twilite import TwiliteClient

client = TwiliteClient(host="10.0.52.25")
client.connect()
client.set_query_rate(10)          # one report per second
for sample in client.stream():     # sends showc, yields Sample objects
    print(sample.index, sample.coincidences)
```

Run the simulator with `uv run python -m twilite.sim --help`.
