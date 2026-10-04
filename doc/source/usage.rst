Usage
=====

Acquisition
-----------

1. Check that the PC clock is synchronised with the PET scanner: every sample is
   timestamped with it, as in PSAMPLE.
2. On the *Acquisition* page, enter the twilite's IP address and port and press
   **Connect**. The status light turns green.
3. Choose how often the device reports (**Report every**, in units of 100 ms). Each
   sample counts over that period and is given in counts per second, so a short period
   follows fast changes but is noisier: at 100 ms the counts come in steps of 10 cps.
4. Choose **End by** *Manual* (press **Stop**) or *Time* (a duration in minutes), then
   press **Start**. The plot shows coincidences and both singles against time; tick
   the boxes under *Display* to hide a curve.
5. To mark an event, such as the injection or a manual blood sample, type a note and
   press **Mark** (or Enter). It appears as a vertical line in the plot and is stored
   with the acquisition.
6. Press **Stop**. The file name appears in a message and on the *Correction* page.

Each acquisition is written to ``data/YYYYMMDD_HHMMSS_twilite.csv`` as it runs, one
line per sample, so a crash loses nothing. A file that did not end cleanly keeps the
name ``*.partial.csv``; the app offers to recover it at the next start.

If the connection drops during an acquisition, the app reconnects by itself (see
*reconnectAttempts* in :doc:`settings`) and stores the loss and the reconnection as
events. Each loss shows as a break in the plot.

Correction
----------

On the *Correction* page, choose the isotope (or *Custom* to enter a half-life and
branching ratio), the PET scan start, the background and the calibration factor, and
press **Apply**. The *Corrected* switch on the *Acquisition* page then shows the
coincidences as activity concentration:

.. math::

   C(t) = \mathrm{CF} \cdot \frac{\left(R(t) - B\right) e^{\lambda t}}{\mathrm{BR}}

with *t* the time from the PET scan start, λ = ln 2 / T½, *B* the background (the
mean of all samples before the PET start, or a fixed value) and BR the branching
ratio. Samples before the PET start are not shown, as in PSAMPLE. The raw counts in
the acquisition file are never changed.

Export
------

The *Export* card works on the last acquisition, or on any file chosen with
**Choose...**:

* **CSV**: raw counts, plus the time from the PET start and the activity concentration
  when the PET start is set.
* **PSAMPLE .crv**: date, time, coincidences and singles, tab-separated. Provisional
  until compared with a real PSAMPLE file.
* **PMOD blood**: the corrected curve in seconds and kBq/cc, for PKIN.
* **Events**: the marks and connection events.

Calibration
-----------

1. Record a phantom run: background first, then insert the source and leave it until
   the rate is stable.
2. On the *Calibration* page, press **Load...** and choose the run.
3. Drag the grey region over the background before the step and the coloured region
   over the plateau.
4. Enter the PET reference time (the time the PET activity is decay-corrected to) and
   the phantom activity concentration measured by the PET, in kBq/cc.
5. Press **Compute**, then **Use** to apply the factor on the *Correction* page.

The isotope is the one selected on the *Correction* page.
