Twilite
#######

**Twilite** records the blood activity measured by a Swisstrace twilite blood sampler
and turns it into an activity concentration curve for your PET analysis. It replaces
the acquisition and correction functions of PMOD PSAMPLE.

A typical study goes like this:

1. :doc:`acquire`: connect to the twilite and record the blood activity during the scan.
2. :doc:`calibrate`: compute the calibration factor from a phantom measurement. You
   only need to do this when you calibrate the twilite, not for every study.
3. :doc:`correct`: subtract the background, correct for decay and apply the
   calibration, and clean up the curve if needed.
4. :doc:`export`: save the corrected curve for PMOD or for your own analysis.

The app has one page for each step in the bar on the left: **Acquisition**,
**Correction** and **Calibration**. **Settings** (the gear) holds the connection
settings, and **Docs** shows this manual.

.. toctree::
   :maxdepth: 2

   installation
   acquire
   calibrate
   correct
   export
   settings
   troubleshooting
