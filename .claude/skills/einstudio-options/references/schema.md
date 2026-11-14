# options.yaml schema

Options are declared here and never changed at run time: no code may rewrite an option's
`type`, `options` or `default`. The code that reads this file is
`widgets/einOptionsWidget.py` in the installed `einstudio` package; the human reference is
<https://einlab.pages.uzh.ch/eincode/einstudio/reference/config/options_yaml.html>.

## Every option

```yaml
myOption:
  type: "<type>"          # required, see below
  label: "<shown text>"   # required
  subset: "<groupName>"   # required when an EINoptionsWidget filters by subset (KeyError otherwise)
  width: "med"            # optional: vshort | short | med | long | vlong | stretch | auto
  default: ...            # required for text, switch, intNumber, floatNumber, slider
```

## Types

| `type` | Widget | Required fields | Optional |
|--------|--------|-----------------|----------|
| `text` | `EINlineEdit` | `default` | `width` (default `long`) |
| `multiChoice` | `EINdropDown` | `options: [...]`, `defaultIndex` | `width` (default `short`) |
| `switch` | `EINswitch` | `default: true/false` | — |
| `intNumber` | `EINspinBox` | `default`, `minVal`, `maxVal` (**not** `min`/`max`) | `width` (default `short`) |
| `floatNumber` | `EINdoubleSpinBox` | `default`, `minVal`, `maxVal`, `decimals` | `singleStep`, `width` (default `short`) |
| `slider` | `EINslider` + `<name>_value` readout | `minVal`, `maxVal`, `default` | `unit` (readout suffix); always fills the row |
| `folderSelector` | `EINlineEdit` + browse button | — | `default`; always fills the row |
| `fileSelector` | `EINlineEdit` + browse button | — | `default`, `fileFilter` (Qt filter string); always fills the row |
| `multiSwitch` | one `EINswitch` per key (`<name>_<key>`) | `switches: {key: bool}` | `switchLabels`; value is one bool per key |
| `table` | `EINconfigTable` | `rowLabels`, `rowConfigNames`, `colLabels` | `defaults[row][col]`; value is `{rowConfigName: "v1,v2,..."}` |

`width: "stretch"` makes a plain control fill the space between label and right edge
(used for file-name fields).

## Generated widget names

For option `myOption`, `EINview` adds `myOption_label` and `myOption_edit` to
`self.widgets`. There is **no** auto-generated `myOption_help`. Access controls as
`self.widgets.myOption_edit`, not through `findChild()`.

The `_label` is a hidden discovery stub, not the visible row title. Slider readouts,
browse buttons and individual multi-switch controls exist in the widget tree but are
not automatically added to `self.widgets`; list them in `makeWidgetsList()` if needed.
Options in `MANUAL_OPTION_NAMES` skip automatic discovery entirely.

## Example

```yaml
sampleRate:
  type: "intNumber"
  label: "Sample rate (Hz)"
  default: 1000
  minVal: 1
  maxVal: 100000
  subset: "acquisition"

refDeviceType:
  type: "multiChoice"
  label: "Reference device"
  options: ["Photodiode", "ThorPM100D"]
  defaultIndex: 0
  subset: "powerCalib"
```

A text option holding a Python list is stored as text; parse it with
`ast.literal_eval(...)` where it is read.
