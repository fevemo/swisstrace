Settings
========

Click **Settings** (the gear at the bottom of the bar on the left). The settings can
only be changed while the app is disconnected. Press **Save** to keep them; they apply
from the next connection.

Connect to your twilite
-----------------------

The app starts with a simulated twilite so you can try it without the device. To use
your twilite:

1. If the app is connected, press **Disconnect**.
2. Open **Settings** and switch **Simulated twilite** off.
3. Enter your twilite's IP address next to **Address**, and click **Save**.
4. Press **Connect** on the **Acquisition** page.

All settings
------------

You do not normally need to change anything other than the address.

.. list-table::
   :widths: 28 72
   :header-rows: 1

   * - Setting
     - What it does
   * - Simulated twilite
     - Connect to a twilite simulated by the app instead of a real one.
   * - Address
     - Your twilite's IP address and port (normally 23).
   * - Timeout (s)
     - How long the app waits for an answer before it treats the connection as lost.
   * - Reconnect attempts
     - How many times the app tries to reconnect if the connection is lost during a
       recording.
   * - Data folder
     - Where measurements are saved. Leave it empty to use the folder shown.
   * - Raw device logs
     - Keep a detailed record of the communication with the twilite. Leave it on: it
       helps to diagnose problems.
   * - Simulator
     - Shown only with *Simulated twilite* on: what the simulated twilite measures.

The app also remembers the values you entered on its pages (sample rate, isotope,
calibration factor and so on) and restores them at the next start.
