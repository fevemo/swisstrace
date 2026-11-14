---
name: einstudio-layouts
description: Use when creating or editing an EINstudio app's layouts/*.py or composing its widgets — EINsimpleLayout/EINnavbarLayout, page types and their card wrapping, EINcardWidget, EINcardColumn/EINcardSplitter, EINresponsivePanel, EINoptionRow, EINrow, EINlabeledWidget, the objectName contract.
---

# EINstudio layouts

Paths are relative to the installed `einstudio` package. Code: `layouts/` (base classes,
page types, responsive panel) and `widgets/einFluentWidgets.py` (cards, rows,
containers). Manual: <https://einlab.pages.uzh.ch/eincode/einstudio/architecture/layouts.html>
and the widget and layout reference under
<https://einlab.pages.uzh.ch/eincode/einstudio/reference/index.html>.
Examples: `demo01_hello` (simple), `demo05_sections` (navbar + cards), and the `full`
version of each app template (`uv run ein template <name>`; source in
`scaffold/templates/<name>/full/layouts/`).

## Base class (contract)

| Base | Use for |
|------|---------|
| `EINsimpleLayout` | One page, no navigation bar: build a page, `self.addPage(page)` |
| `EINnavbarLayout` | Several pages behind a navigation bar: `self.addPage(page, FluentIcon.X, "Title")` |

The app's layout class must be named `MainWidget`; the framework instantiates it and
finds `mainLayout.yaml` next to `mainLayout.py` by itself:

```python
class MainWidget(EINnavbarLayout):
    def __init__(self, options=None, instrumentConfig=None):
        super().__init__(options, instrumentConfig)
```

The layout YAML holds only this app's geometry (splitter sizes, column widths); the
framework reads none of its keys. Page margins, card padding and gaps come from the
style tokens, so layouts do not set them.

## Pages and cards

Build pages from `einstudio.layouts`: `EINdocPage`, `EINstackPage` (cards top-down,
1+ columns, footer), `EINcontrolsPage` (fixed controls column + workspace),
`EINcolumnsPage` (three resizable columns, `addLeft`/`addRight`). The last two take
`log=` and `logPosition=`. A custom page starts from `EINpage`.

- **Every page slot wraps**: a widget that is not a card goes into an untitled
  `EINcardWidget` automatically (`workspace=`, `centre=`, `addControl`, `addLeft`,
  `addRight`, `EINstackPage.addWidget`, `addFooterWidget`). Pass plots, rows and tables
  as they are; wrapping them by hand draws a card inside a card. `EINpage.addWidget`
  does **not** wrap.
- **Opting out**: `card=False` on an `add*` slot, `workspaceCard=False` /
  `centreCard=False` on the constructors — for a bare title, a button, or a widget that
  lays out its own cards (a `QStackedWidget` of panels).
- `EINcardWidget(title, collapsible=..., border=...)` is the one card class. `content=w`
  gives an untitled card around `w`. `border=False` = titled section with no border,
  surface or padding, for several sections inside one larger card; slots do not wrap it.
- `EINoptionsWidget(self.options, subset=..., title=..., border=...)` is a card; pass
  `self.options` as it is (it calls `vars()` itself). `border=False` = bare rows.
- Several cards: `EINcardColumn([...], scroll=True)` (stacked, section gap, `(w, stretch)`
  items fill free height), `EINcardSplitter([...], orientation=..., sizes=, stretch=,
  collapsible=)`. Both wrap non-card children and are not wrapped by slots.

## Navigation

- `addPage` uses `page.objectName()` as the route key. **Contract:** every page needs a
  unique name. Symptom if not: only one nav item appears and the other pages are
  unreachable — no error, no log. Page names do not go in `expectedWidgets`.
- The first page added is shown and highlighted.
- Several nav items sharing one page: place a `QStackedWidget` in the page
  (`card=False`), then `self.addPanelPage(page, stack, {key: (panel, icon, text)})`;
  `icon=None` = no entry; `self.showPanel(key)` from code. Click handling stays in the
  View.

## Responsive panels

`EINresponsivePanel(columns=[[cards], ...], standard=[[0], [1, 2]], half=..., full=...,
sizes=..., framed=...)` rearranges groups of cards for snapped and maximised windows;
it watches the window itself. `config.yaml` `responsiveLayout: true` switches it on
(default off = always `standard`). `framed=True` draws one card around the panel, for
groups of `border=False` sections. A widget may appear in several panels of one window
only if no two show it in the same mode (`full=[]` shows nothing). `modeChanged(mode)`
reports switches. Template: `uv run ein template responsive`.

## objectName and building blocks

**Contract:** every widget the View uses gets `setObjectName("name")` in the layout,
matching its entry in `View.makeWidgetsList()` exactly. On an `EINlabeledWidget`, name
the **inner** widget, not the wrapper.

| Need | Widget |
|------|--------|
| Settings row: title left, controls right | `EINoptionRow(title, itemSpacing=None)` |
| Title-less strip of controls | `EINrow(...)` |
| Control with inline label(s) | `EINlabeledWidget(widget, leadingLabel="X:", trailingLabel="mW")` |
| Plain containers | `EINvBoxWidget`, `EINhBoxWidget`, `EINvBoxLayout`, `EINhBoxLayout` |
| Toolbar of actions | `EINcommandBar().addCommands([(text, objectName, icon) \| None, ...])`; `None` = separator |

- `EINoptionRow`: `addLeadingWidget(w, stretch)` places after the title,
  `addTrailingWidget(w)` right-aligned. A full-width field: `setTrailingStretchEnabled(False)`
  then `addLeadingWidget(edit, 1)`. Rows already have the right inset; extra trailing
  spacing is not needed.
- `itemSpacing=None` applies the shared gap between widgets. Pass a number only for a
  different uniform gap (`0` for flush); `addLeadingSpacing(px)` for one-off extra space.
- Size controls with `length=`: `EINbutton("Start", length="med")`,
  `EINspinBox(length="short")` (`vshort`, `short`, `med`, `long`, `vlong`, `stretch`, `auto`).
- These blocks carry the row styling and spacing tokens; a bare `QLabel` next to a
  control or a hand-made `QHBoxLayout` row will not line up with them. A construct the
  app repeats belongs in a small widget class in the app's `widgets/` folder, built from
  these blocks.

## Pitfalls

| Symptom | Cause → Rule |
|---------|--------------|
| A card drawn inside another card | A widget that lays out its own cards passed to a slot → `card=False`, or make it a `border=False` section |
| Gap next to a top-level `QSplitter` in a box layout | A splitter's cross-axis policy is `Preferred` → `setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)` (`EINcardSplitter` does it) |
| Unscoped `setStyleSheet("background: x")` changes widgets inside a container | It reaches every descendant (like `* { }`) → never set one on a container; scope it to the widget's class |
| Widgets added straight to an `EINcardWidget` touch each other | The card body has zero spacing → put them in `EINrow` / `EINoptionRow` rows (`card.addRows([...])`), not `addSpacing(px)` |
| Square image stops tracking column width | `EINimageWidget(squareMode=True)` combined with `setFixedSize()` → drop the fixed size |
| `stateChanged` / `valueChanged` never fires on a switch | `EINswitch` emits `checkedChanged(bool)`; state via `isChecked()` / `setChecked()` |
| The View's discovery misses a spinbox | Discovery type must be `EINspinBox` / `EINdoubleSpinBox` (or Fluent `SpinBox`) |
