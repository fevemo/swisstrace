How the app works
=================

Which file of swisstrace does what, and where to start when a real instrument
replaces the simulated one.

``model.py``
    The simulated detector and the rolling window of readings. Replace
    ``Model.acquire()`` with a call to your instrument.

``viewmodel.py``
    The acquisition timer. On every tick it asks the Model for a reading and emits
    ``traceUpdated`` for the plot.

``view.py``
    Reads the options when a run starts and redraws the plot on every signal.

``layouts/mainLayout.py``
    Builds the window: one ``EINstackPage`` per screen, added to the navigation bar
    with ``addPage()``, and an ``EINdocPage`` for this manual.

``options.yaml``
    Every setting, grouped into the subsets that the layout places in separate cards.

``instrumentConfig.yaml``
    The parameters of the (simulated) detector.
