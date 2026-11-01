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
that mean), or a dashed line the background with *Fixed value*. Once the PET scan start
is set, the corrected curve shows in kBq/cc on the right axis, over the coincidences,
and follows every change to the settings. Panning and zooming move both axes alike. The
correction is:

.. math::

   C(t) = \mathrm{CF} \cdot \frac{\left(R(t) - B\right) e^{\lambda t}}{\mathrm{BR}}

with *t* the time from the PET scan start, λ = ln 2 / T½, *B* the background (the
mean of all samples before the PET start, or a fixed value) and BR the branching
ratio. A sample's time is when its report arrived, at the end of its counting
interval, both in the plot and in the correction, as in PSAMPLE; a resampled sample is
in the middle of the samples it merges (see below). Samples before
the PET start are not shown, as in PSAMPLE. The raw counts in the acquisition file are
never changed.

Editing the data
----------------

The *Edit* row of the *Data* card changes the loaded data in memory, never the file it
was read from. Edits can follow each other in any order. There is no undo: **Load...**
the file again to start over. Loading other data or closing the app asks before losing
edits that were not saved.

**Cut** replaces artifacts (a flush, a bubble, a spike) by a straight line. Press
**Cut**: every sample gets a marker and a *Cut* row appears. Drag across the plot to
select samples. The selection snaps to midway between samples; drag its edges to widen
or narrow it, or its middle to move it. In this mode the middle mouse button pans the
plot and the wheel still zooms. The selected samples turn yellow, and a dashed line
shows what replaces them: a straight line from the mean of the samples just before the
selection, drawn at the sample next to it, to the mean of those just after it.
*Edges: mean of* sets how many samples each mean takes (1 joins the two neighbours).
With samples on one side only, that
side's mean is held flat. Nothing changes until **Apply cut**. Press **Done** to leave
the mode. All three channels (coincidences and both singles) are replaced, and the
replaced samples are flagged as interpolated in the saved file.

**Resampling** opens a window with one row per section of the data: its start and end
(seconds on the plot's time axis) and its sampling period, in seconds per sample. The
*Samples* column shows how many samples the section will have. At first there is one
section, the whole measurement, at the acquisition's sampling period. **Add section**
splits the selected section (the last one if none is selected) in two halves, and
**Delete section** gives the selected section's time back to the one before it. The
first section cannot be deleted. Double-click a value to change it. Moving the end of a
section moves the start of the next. A sample on a boundary belongs to the earlier
section, and samples outside every section stay as they are. The plot shows the
resampled samples as a dashed line and the section boundaries as dotted lines. Nothing
changes until **Resample**. The window stays open (it then lists the sampling after
resampling), so the plot can be zoomed in the meantime. With nothing to apply the
button says **Done** and closes the window. A section that cannot be applied turns
red, without a sample count, and the line under the table says why. While the window
is open, **Resampling** in the *Data* card says **Done** and closes it too; with
changes not applied, it asks first whether to apply them, discard them, or go back.

Resampling merges consecutive samples, never splits them: a section's period must be a
whole multiple of the data's sampling in it. After resampling to 2 s, that part can go
to 4 or 6 s (half or a third of the samples), but not back to 1 s, nor to 3 s; the
section turns red and **Resample** stays disabled. Each merged sample lasts as long as
its samples together and has their mean rate, weighted by their counting intervals, so
no counts are lost, and sits in the middle of them on the plot and in the correction.
A section's last sample may be shorter, and a gap in the data (a lost connection)
starts a new sample. A typical use is to keep the bolus at the acquisition's rate and
resample the slow tail of a long acquisition to 30 or 60 s, which reduces the noise.

**Save...** in the *Edit* row saves the edited data as a new acquisition file,
``..._edited.csv`` by default, which **Load...** reads like any other. It lists the
edits in its header, and has two more columns: each sample's counting interval
(``duration_s``) and whether it was interpolated by a cut. An acquisition as recorded
is never overwritten; an edited file may be.

Saving
------

The *Save* card on the *Acquisition* page saves the last acquisition:

* **Raw data**: choose the format in the save dialog.

  * *CSV*: the raw counts.
  * *PSAMPLE curve (.crv)*: time stamp, coincidences and singles, tab-separated, as
    PSAMPLE writes it.

* **Events**: the marks and connection events, as CSV.

**Save...** in the *Export* card of the *Correction* page saves the loaded data, edits
included, corrected with the settings on screen; it needs the PET scan start. Choose
the format in the save dialog:

* *PMOD blood (.bld)*: sample time in seconds from the PET start (when its report
  arrived, or the middle of a resampled sample) and kBq/cc, for PKIN.
* *PMOD TAC (.tac)*: frame start and end in seconds and kBq/cc, one frame per sample's
  counting interval (longer after resampling). Provisional until compared with a TAC
  exported by PMOD.
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
