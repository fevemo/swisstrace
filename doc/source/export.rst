Export the corrected curve
==========================

On the **Correction** page, once the correction is set up (see :doc:`correct`), press
**Save...** in the **Export** card and choose a format:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Format
     - Use it for
   * - **PMOD blood (.bld)**
     - Kinetic modelling in PMOD PKIN: the time of each sample from the scan start and
       its activity concentration.
   * - **PMOD TAC (.tac)**
     - PMOD tools that expect time frames: each sample as a frame with a start, an end
       and its activity concentration.
   * - **CSV with corrected values**
     - Your own analysis in a spreadsheet or script: the raw counts plus the time from
       the scan start and the activity concentration.

The export uses the settings on screen and includes any cuts or resampling you made.
It needs the **PET scan start** to be set.

.. note::
   The PMOD formats have not yet been checked against files exported by PMOD itself.
   Check the first export in PMOD before relying on it.

To save the raw counts or the markers instead, see :ref:`Save a copy of the raw data`.
