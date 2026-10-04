How the app works
=================

The repository is a uv workspace with two parts. Only the app depends on Qt.

``packages/twilite``
    The driver, with no Qt and no dependencies outside the standard library.
    ``protocol.py`` holds the device facts and parses lines, ``driver.py`` holds
    ``TwiliteClient``, ``storage.py`` writes, recovers and exports acquisition files,
    ``correction.py`` and ``isotopes.py`` do the correction maths. ``twilite.sim`` is
    a simulated twilite speaking the same protocol: run ``python -m twilite.sim --help``.

``apps/twiliteacq``
    This EINstudio app.

    ``model.py``
        Owns the ``TwiliteClient`` (and the simulator with ``simulate: true``), the
        open acquisition file, the live trace and the correction settings. Its
        ``acquire()`` blocks until the acquisition ends, so it also runs from a script.
        It never imports Qt.

    ``viewmodel.py``
        Runs ``connect()`` and ``acquire()`` in worker threads, checks prerequisites
        before every call and turns results and errors into signals. A timer sends the
        trace to the plot at most ten times a second.

    ``view.py``
        Wires the controls to the ViewModel and its signals to the plots and labels;
        saves the settings and disconnects when the window closes.

    ``layouts/mainLayout.py``
        Builds the *Acquisition*, *Correction*, *Calibration* and *Docs* pages.

``tests``
    ``uv run pytest`` runs the unit, integration (against the simulator) and app
    tests. ``uv run pytest --hardware --host <ip>`` repeats the integration tests on a
    real twilite and adds the long-run, cable-pull and power-cycle tests.
