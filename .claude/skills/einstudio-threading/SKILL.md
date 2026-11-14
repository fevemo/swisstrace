---
name: einstudio-threading
description: Use when an EINstudio app runs work in the background — runFuncInThread / prepareFuncInThread, the (result, error) callback, timers in worker threads, or debugging thread crashes and deadlocks.
---

# EINstudio threading

Code: `tools/threads.py` in the installed `einstudio` package. Example:
`uv run ein demo 4` (`demos/demo04_threading/`).

## Running background work

```python
runFuncInThread(self.model.runTask, params, callbackFunc=self.onTaskFinished)
```

- Call it from the **ViewModel**. The callback receives one tuple `(result, error)`;
  unpack it, handle `error is not None` (log or surface it), then emit a signal.
- Pass the callback as `callbackFunc`; connecting it after the call returns can miss a
  job that already finished.
- Need extra connections before start? `worker, thread = prepareFuncInThread(...)`,
  connect, then `thread.start()`.
- The module's `JobRegistry` keeps `(worker, thread)` alive until the thread has fully
  finished. Callers may discard the return value; no attributes are needed to keep them.

## Contract

- Never add `deleteLater` to a job's worker or thread. The registry owns them; a
  `deleteLater` posted into the worker thread drags Python into `QThread` finish and
  deadlocks on the GIL.
- Never touch a widget from a worker thread — emit a signal from the ViewModel instead.
- A `QTimer` used by a worker is created inside the worker's `run()` (after
  `moveToThread`), not in `__init__`.
- With Qt's automatic connection type, delivery to a QObject receiver in another thread
  is queued. Use a ViewModel QObject method as the callback; arbitrary Python callables
  do not get GUI-thread affinity by themselves. Use `threading.Event` /
  `QWaitCondition` when explicit synchronisation is needed.
- Blocking calls (hardware reads and waits, long computations) never run on the GUI
  thread.
