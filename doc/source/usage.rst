Usage
=====

Acquisition
-----------

1. Check that the PC clock is synchronised with the PET scanner: every sample is
   timestamped with it, as in PSAMPLE.
2. On the *Acquisition* page, enter the twilite's IP address and port and press
   **Connect**. The status light turns green.
3. Choose the **Sample rate**: one sample every 0.1, 1, 2, 5 or 10 s. Each sample counts
   over that period and is given in counts per second, so a short period follows fast
   changes but is noisier: at 0.1 s the counts come in steps of 10 cps.
4. Choose **End by** *Manual* (press **Stop**) or *Time* (a duration in minutes), then
   press **Start**, which becomes **Stop** while the acquisition runs. The plot shows
   coincidences and both singles against time; untick a box next to *Show in plot* to
   hide a curve.
5. To mark an event, such as the injection or a manual blood sample, type a note next
   to *Add marker* and press **Mark** (or Enter). It appears as a vertical line in the
   plot and is stored with the acquisition.
6. Press **Stop**. The file name appears in a message.

Each acquisition is written to ``data/YYYYMMDD_HHMMSS_twilite.csv`` as it runs, one
line per sample, so a crash loses nothing. A file that did not end cleanly keeps the
name ``*.partial.csv``; the app offers to recover it at the next start.

If the connection drops during an acquisition, the app reconnects by itself (see
*reconnectAttempts* in :doc:`settings`) and stores the loss and the reconnection as
events. Each loss shows as a break in the plot.

Correction
----------

On the *Correction* page, choose the data to correct: **Current** takes the running
or last acquisition, **Load...** any acquisition file. The plot shows its coincidences
in counts per second, from the start to the end of the measurement.

Choose the isotope (or *Custom* to enter a half-life and branching ratio), the PET scan
start, the background and the calibration factor. Enter the PET scan start as a time of
day (``HH:MM:SS``, PC clock); its date is the one of the data. Or press **Select** and
click the plot where the scan starts (press **Cancel** to stop selecting). Time 0 of
the plot is then the PET start, so the samples before it have negative times.

The plot follows the settings: a vertical line marks the PET start, a grey region the
samples averaged for the background with *Mean before PET* (the field next to it shows
that mean), or a dashed line the background with *Fixed value*. Press **Apply** to add the corrected curve, in kBq/cc on the
right axis; changing a setting removes it until the next **Apply**. The correction is:

.. math::

   C(t) = \mathrm{CF} \cdot \frac{\left(R(t) - B\right) e^{\lambda t}}{\mathrm{BR}}

with *t* the time from the PET scan start, λ = ln 2 / T½, *B* the background (the
mean of all samples before the PET start, or a fixed value) and BR the branching
ratio. Samples before the PET start are not shown, as in PSAMPLE. The raw counts in
the acquisition file are never changed.

Saving
------

The *Save* card on the *Acquisition* page saves the last acquisition:

* **Raw data**: choose the format in the save dialog.

  * *CSV*: the raw counts.
  * *PSAMPLE curve (.crv)*: time stamp, coincidences and singles, tab-separated, as
    PSAMPLE writes it.

* **Events**: the marks and connection events, as CSV.

**Save...** under *Corrected data* on the *Correction* page saves the loaded data,
corrected with the settings on screen; it needs the PET scan start. Choose the format
in the save dialog:

* *PMOD blood (.bld)*: sample time in seconds from the PET start and kBq/cc, for PKIN.
* *PMOD TAC (.tac)*: frame start and end in seconds and kBq/cc, one frame per report
  period. Provisional until compared with a TAC exported by PMOD.
* *CSV with corrected values*: the raw counts plus the time from the PET start and the
  activity concentration.

Calibration
-----------

1. Record a phantom run: background first, then insert the source and leave it until
   the rate is stable.
2. On the *Calibration* page, press **Current** to use the running or last acquisition,
   or **Load...** to choose the run.
3. Drag the grey region over the background before the step and the coloured region
   over the plateau.
4. Check the PET reference time: the time of day (``HH:MM:SS``) the PET activity is
   decay-corrected to. Loading a run sets it to the run's start; change it if the PET
   reports the activity at another time. Enter the phantom activity concentration
   measured by the PET, in kBq/cc.
5. The *Result* follows every change; while it cannot be computed, the reason is shown
   under it. Press **Apply** to use the factor on the *Correction* page.

The isotope is the one selected on the *Correction* page.
