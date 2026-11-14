Correct a measurement
=====================

The **Correction** page turns the measured count rate into an activity concentration
in kBq/cc, the curve you use for your PET analysis. The file of the measurement itself
is never changed.

Choose the data
---------------

In the **Data** card, press **Current** to use the measurement you are recording or
just recorded, or **Load...** to open a measurement file. The app opens its own files
(``.csv``) and curves recorded with PMOD PSAMPLE (``.crv``).

The plot shows the coincidences in counts per second.

Set up the correction
---------------------

1. **Isotope**: choose your tracer, or *Custom* to enter a half-life and branching
   ratio yourself.
2. **PET scan start**: type the time of day the scan started (``HH:MM:SS``, computer
   clock), or press **Select** and click the start in the plot. Time 0 in the plot is
   now the scan start.
3. **Background**: choose how to subtract the background:

   - *Mean before PET*: the average of everything recorded before the scan start (shown
     as a grey area in the plot). Use this when you recorded a few minutes before the
     injection.
   - *Fixed value*: a value you enter, in counts per second (shown as a dashed line).

4. **Calibration factor**: the one from :doc:`calibrate`, or a value you know.

Once the scan start is set, the corrected curve appears in kBq/cc on the right-hand
axis and follows every change you make. Only the part after the scan start is
corrected.

.. admonition:: What the correction does

   For each sample, the app subtracts the background, corrects for radioactive decay
   back to the scan start, divides by the isotope's branching ratio and multiplies by
   the calibration factor:

   .. math::

      C(t) = \mathrm{CF} \cdot \frac{\left(R(t) - B\right) e^{\lambda t}}{\mathrm{BR}}

   with *R* the coincidence rate, *B* the background, *t* the time since the scan
   start, λ = ln 2 / half-life and BR the branching ratio. This is the same correction
   as PSAMPLE.

Clean up the curve
------------------

The **Edit** row of the **Data** card changes the loaded data, never the file it came
from. There is no undo: to start over, load the file again. The app asks before
discarding changes you have not saved.

Remove artifacts (Cut)
~~~~~~~~~~~~~~~~~~~~~~

Use **Cut** to replace a flush, a bubble or a spike with a straight line.

1. Press **Cut**. Each sample gets a marker.
2. Drag across the plot over the samples to remove. Drag the edges of the selection to
   adjust it. They turn yellow, and a dashed line shows what replaces them.
3. **Edges: mean of** sets how many samples on each side the line starts and ends on.
   1 joins the two neighbouring samples; more smooths out noise.
4. Press **Apply cut**. Repeat for other artifacts, then press **Done**.

While cutting, pan the plot with the middle mouse button; the wheel still zooms.

Reduce the noise (Resampling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Resampling** merges samples into longer ones, which reduces the noise. A typical use
is to keep the bolus at full rate and merge the slow tail of a long measurement into 30
or 60 second samples. No counts are lost.

1. Press **Resampling**. A window lists the *sections* of the measurement: at first one
   section, the whole measurement.
2. Press **Add section** to split the selected section in two, and double-click a start,
   end or period to change it. **Delete section** merges a section into the one before.
3. Set the period of each section, in seconds per sample. The plot previews the result.
4. Press **Resample**.

Samples can only be merged, not split: a section's new period must be a whole multiple
of its current one. From 1 s you can go to 2, 5 or 30 s; after going to 2 s, you can go
to 4 or 6 s, but not back to 1 s or to 3 s. A section that cannot be applied turns red,
with the reason below the table.

Save the cleaned-up data
~~~~~~~~~~~~~~~~~~~~~~~~

Press **Save...** in the **Edit** row to save the edited measurement as a new file
(``..._edited.csv``), which you can load again later. The original measurement is
never overwritten.

To save the corrected curve, see :doc:`export`.
