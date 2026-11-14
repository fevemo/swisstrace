---
name: einstudio-options
description: Use when editing an EINstudio app's options.yaml, EINoptionsWidget, the generated <name>_edit option widgets, MANUAL_OPTION_NAMES, or reading option values.
---

# EINstudio options

Before editing option declarations, read the [field and type reference](references/schema.md).
Paths are relative to the installed `einstudio` package. Code:
`widgets/einOptionsWidget.py`, `EINview.addOptionsToWidgetList` in `tools/einview.py`.
Runnable example: `uv run ein demo 3` (`demos/demo03_options/`). Manual:
<https://einlab.pages.uzh.ch/eincode/einstudio/reference/config/options_yaml.html>.

## How the pieces connect (contract)

- Options load only when `config.yaml` has `useOptions: true` (plus `optionsFile`).
  Then `configManager.options` is a `SimpleNamespace` of every option; otherwise it is
  `None` and no option widgets are added — silently.
- Options are declared in `options.yaml` and never changed in code: no code rewrites an
  option's `type`, `options` or `default`.
- `EINview.addOptionsToWidgetList()` adds `<name>_label` / `<name>_edit` to the expected
  widgets for every non-manual option. The layout must render every such option in an
  `EINoptionsWidget`; adding YAML alone otherwise fails widget discovery at startup.
- `EINoptionsWidget(self.options, subset=..., ...)` (from `einstudio.widgets`) renders one
  subset as rows. Pass the options namespace as it is. API: `getOptions()` → dict,
  `setOptions(dict)`, signal `someOptionChanged`, `setOptionEnabled`, `hideOptions`.

## Custom widgets for some options: `MANUAL_OPTION_NAMES`

Set the class attribute on the View; do not override `addOptionsToWidgetList()`:

```python
class View(EINview):
    MANUAL_OPTION_NAMES = frozenset({"myComplexOption"})
```

Those options still load into `configManager.options`, but get no auto `_label`/`_edit`.
The layout builds and names their widgets, and the View lists them in
`makeWidgetsList()`.

## Pitfalls

| Symptom | Cause → Rule |
|---------|--------------|
| No option widgets at all, no error | `useOptions: true` missing from `config.yaml` → add it |
| `KeyError: 'minVal'` in `_buildRows` | Spinbox uses `min`/`max` → use `minVal`/`maxVal` |
| `KeyError: 'subset'` in `_filterOptions` | An option lacks `subset` while a widget filters by subset → give every option a `subset` |
| `KeyError: 'defaultIndex'` for a dropdown | `multiChoice` without `defaultIndex` → always set it |
| `TypeError: vars() argument must have __dict__` | Passed `vars(options)` or a dict → pass the options namespace itself |
| A `width: "stretch"` control only gets half the row | Added as a *trailing* widget → disable trailing stretch and use `addLeadingWidget(w, 1)` |
| Widget named `<name>_help` not found | `_help` is never auto-generated → add it yourself in `makeWidgetsList()` |
