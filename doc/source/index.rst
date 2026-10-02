swisstrace
########################################

.. note::
   This manual comes with the ``pages`` app template. Replace its pages with the
   documentation of your application. To add a page, create an ``.rst`` file next to
   these and list its name in the table of contents below. Rebuild the HTML from the
   app folder with ``uv run --group docs python -m sphinx doc/source doc/build/html``.

**swisstrace** is a live signal monitor built with EINstudio. It reads a simulated
detector at a fixed interval and plots the latest readings. Its screens are separate
pages in the navigation bar on the left: *Acquisition* to run a measurement,
*Settings* for the display and the log, and *Results* for the statistics of the last
run.

.. toctree::
   :maxdepth: 2

   usage
   settings
   code
