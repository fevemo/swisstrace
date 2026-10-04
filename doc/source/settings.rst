Settings
========

Instrument
----------

``instrumentConfig.yaml``, in the app folder, describes the twilite of this
installation. It travels with the instrument PC, not with the source code.

.. list-table::
   :widths: 26 20 54
   :header-rows: 1

   * - Key
     - Default
     - Meaning
   * - host, port
     - 10.0.52.25, 23
     - Address shown in the *Connection* card at the first start.
   * - timeout_s
     - 5.0
     - Seconds without an answer before the connection counts as lost. While
       streaming, two report periods are added.
   * - reconnectAttempts
     - 3
     - Reconnections tried, one second apart, after a lost connection during an
       acquisition. When they all fail, the file is closed and the acquisition ends.
   * - dataDir
     - data
     - Folder of the acquisition files.
   * - rawLog
     - true
     - Also write every byte exchanged with the device to ``dataDir/rawlogs``. Send
       this file along with any problem report.
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
