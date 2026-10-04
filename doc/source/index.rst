Twilite acquisition
########################################

**Twilite acquisition** records the count rates of a Swisstrace twilite blood sampler
over its telnet connection and turns them into an activity concentration curve, in
place of PMOD PSAMPLE's acquisition and correction functions. Its screens are pages
in the navigation bar on the left: *Acquisition* to connect and record, *Correction*
for the decay correction and the exports, and *Calibration* to compute the
calibration factor from a phantom run.

.. note::
   The device's report format is not confirmed yet (see ``doc/protocol.md`` in the
   repository). Until it is, the app runs against a built-in simulated twilite when
   ``simulate: true`` is set in ``instrumentConfig.yaml``.

.. toctree::
   :maxdepth: 2

   usage
   settings
   code
