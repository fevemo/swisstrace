Settings
========

Every setting is declared in ``options.yaml``, which sets its label, default and
allowed values. The window shows them in groups; each group is listed below with
where to find it.

Acquisition
-----------

On the *Acquisition* page. They are read when you press **Start**, so a change applies
to the next run.

.. list-table::
   :widths: 26 16 22 36
   :header-rows: 1

   * - Setting
     - Default
     - Allowed
     - Meaning
   * - Sample interval (ms)
     - 100
     - 20 to 2000
     - Time between two readings.
   * - Samples shown
     - 300
     - 20 to 5000
     - Number of most recent readings the plot shows.
   * - Signal shape
     - Random walk
     - Random walk, Sine, Square
     - Shape of the simulated signal.
   * - Noise level
     - 1.0
     - 0.0 to 10.0
     - Standard deviation of the random noise added to each reading.

Display
-------

In the *Display* card of the *Settings* page. *Show grid* and *Autoscale axes* apply at
once, also during a run; *Units* applies from the next run.

.. list-table::
   :widths: 26 16 22 36
   :header-rows: 1

   * - Setting
     - Default
     - Allowed
     - Meaning
   * - Units
     - mV
     - any text
     - Unit shown on the vertical axis and in the log.
   * - Show grid
     - on
     - on, off
     - Grid lines in the plot.
   * - Autoscale axes
     - on
     - on, off
     - Rescale the axes to the data on every reading.

Logging
-------

In the *Logging* card of the *Settings* page. They are read when you press **Start**, so
a change applies to the next run.

.. list-table::
   :widths: 26 16 22 36
   :header-rows: 1

   * - Setting
     - Default
     - Allowed
     - Meaning
   * - Log readings
     - off
     - on, off
     - Write readings to the log.
   * - Log every n-th reading
     - 10
     - 1 to 1000
     - With *Log readings* on, write only every n-th reading.
