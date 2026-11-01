Settings
========

Instrument
----------

The *Settings* window (the gear at the bottom of the navigation bar) shows and changes
these settings; it can be opened only while disconnected, and they apply from the next
connection. **Save** writes them to ``instrumentConfig.yaml``, keeping its comments.

``instrumentConfig.yaml`` describes the twilite of this installation. It travels with
the instrument PC, not with the source code. Run from the repository, it is the one in
the app folder. Installed, the app copies it at its first start to the settings folder
(see :doc:`installation`) and then uses that copy, which updates of the app leave
alone.

.. list-table::
   :widths: 26 20 54
   :header-rows: 1

   * - Key
     - Default
     - Meaning
   * - host, port
     - 10.0.52.25, 23
     - Address shown in the *Connection* card at the first start; after that, the app
       remembers the last one connected to.
   * - timeout_s
     - 5.0
     - Seconds without an answer before the connection counts as lost. While
       streaming, two report periods are added.
   * - reconnectAttempts
     - 3
     - Reconnections tried, one second apart, after a lost connection during an
       acquisition. When they all fail, the file is closed and the acquisition ends.
   * - dataDir
     - empty
     - Folder of the acquisition files; ``~`` is the home folder. Empty: ``data`` in
       the app folder when run from the repository, ``~/Twilite Acquisition`` when
       installed.
   * - rawLog
     - true
     - Also write every byte exchanged with the device to ``rawlogs``: in ``dataDir``
       when run from the repository, beside the log when installed. Send this folder
       along with any problem report.
   * - simulate
     - true
     - Start a simulated twilite inside the app and connect to it instead.
   * - simulator
     - see the file
     - Scenario, isotope and idle timeout of the simulator.

Window
------

The app saves the values of the controls in ``state.yaml`` when the window closes and
restores them at the next start.
