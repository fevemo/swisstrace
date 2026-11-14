Calibrate
=========

The calibration factor converts what the twilite counts into an activity concentration
(kBq/cc) that matches your PET scanner. You compute it from a phantom measurement, and
the app remembers it until you change it.

If you already know your calibration factor, type it in **Calibration factor** on the
**Correction** page and skip this page.

Record the phantom measurement
------------------------------

Record a measurement as described in :doc:`acquire`:

1. Start with the twilite empty for a few minutes, to measure the background.
2. Insert the phantom source and leave it until the count rate is stable.
3. Measure the same source on the PET to know its activity concentration.

Compute the factor
------------------

1. On the **Correction** page, choose the **Isotope** of the phantom.
2. On the **Calibration** page, press **Current** to use the measurement you just
   recorded, or **Load...** to open an earlier one (from this app or from PSAMPLE).
3. In the plot, drag the **grey** region over the background, before the source went in.
4. Drag the **coloured** region over the stable part after the source went in.
5. Check the **PET reference time**: the time of day (``HH:MM:SS``) the PET activity
   refers to. It starts at the beginning of the measurement; change it if your PET
   reports the activity at another time.
6. Enter the **PET activity**, in kBq/cc.

The **Result** shows the calibration factor and updates with every change. If it cannot
be computed, the reason is shown below it.

7. Press **Apply** to use this factor on the **Correction** page.
