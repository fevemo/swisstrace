Record a measurement
====================

Before you start
----------------

- **Synchronise the computer's clock with the PET scanner.** Every sample is time-stamped
  with the computer's clock, and the correction relies on it.
- **Press the green play button on the twilite's touch screen.** Without it, the
  twilite sends no data.
- The first time, enter your twilite's address in **Settings** (see :doc:`settings`).

Connect
-------

On the **Acquisition** page, press **Connect**. The status light turns green when the
app is connected.

.. note::
   If **Simulated twilite** is switched on in **Settings**, the app connects to a
   simulated twilite instead of yours. This is useful to try the app without the device.

Record
------

1. Choose the **Sample rate**: one sample every 0.1, 1, 2, 5 or 10 seconds. A short
   interval follows fast changes, such as the bolus, but is noisier.
2. Choose how the recording ends with **End by**:

   - *Manual*: it runs until you press **Stop**.
   - *Time*: it stops by itself after the number of minutes you enter.

3. Press **Start**. The plot shows the coincidences and both singles channels as they
   come in. Untick a box under *Show in plot* to hide a curve.
4. Press **Stop** when you are done. A message shows the name of the file.

Every measurement is saved automatically, sample by sample, in your data folder (see
:ref:`Where your files are`). You do not need to save anything yourself.

Mark events
-----------

To note an event, such as the injection or a manual blood sample, type a short note
next to **Add marker** and press **Mark** (or Enter). The marker shows as a vertical
line in the plot and is saved with the measurement.

If the connection drops
-----------------------

If the connection is lost during a recording, the app reconnects by itself and keeps
recording. The interruption shows as a gap in the plot and is noted in the measurement.
If it cannot reconnect, the recording stops and everything up to that point is kept.

If the app or the computer stops unexpectedly during a recording, the data recorded so
far is not lost: at the next start, the app offers to recover it.

Save a copy of the raw data
---------------------------

The **Save** card on the **Acquisition** page saves the last measurement elsewhere,
for example to share it:

- **Raw data**: the counts as a spreadsheet (*CSV*) or as a PSAMPLE curve (*.crv*).
- **Events**: the markers and connection interruptions, as a spreadsheet (*CSV*).

To save the *corrected* curve, see :doc:`export`.
