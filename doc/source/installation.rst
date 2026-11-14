Installation
============

You need a Mac with Apple Silicon (M1 or later) and macOS 13 (Ventura) or later, or a
Windows 10 or 11 PC. You do not need to install Python or anything else first:
everything the app needs is inside the installer.

.. note::
   This test version is not yet signed with an Apple or Microsoft certificate. Your
   computer therefore warns you the first time you open it, and asks you to confirm
   that you trust it. The steps below show you how. The release version will not ask.

macOS
-----

Install
~~~~~~~

1. Double-click the file you received, ``Twilite-<version>.dmg``. A window
   opens with the app in it.
2. Drag **Twilite** onto the **Applications** folder in that window. The
   app is large, so copying it takes a minute or two: wait until the Finder's progress
   bar is gone. It can take a moment longer before the app shows in Launchpad and
   Spotlight.
3. Close the window and eject the disk image (the *Twilite* drive in the
   Finder sidebar).

Open it the first time
~~~~~~~~~~~~~~~~~~~~~~

macOS blocks apps from developers it does not know yet, so the first start takes a few
extra clicks. You only do this once for each version.

1. Open **Applications** in the Finder and double-click **Twilite**.
2. A message says that *"Twilite" Not Opened* (or *cannot be opened
   because the developer cannot be verified*). Click **Done** (or **Cancel**).
   **Do not** click *Move to Trash* (or *Move to Bin*).
3. Open the **Apple menu** > **System Settings** > **Privacy & Security**.
4. Scroll down to the **Security** section. It says that *"Twilite" was
   blocked to protect your Mac*. Click **Open Anyway** next to it. (This line only
   shows for about an hour after step 2. If it is missing, do steps 1 and 2 again.)

5. Enter your Mac password (or use Touch ID), then click **Open Anyway** once more.

The app starts. From now on it opens with a double-click, like any other app.

.. tip::
   On macOS 13 or 14 there is a shortcut: in **Applications**, hold the **Control** key,
   click **Twilite**, choose **Open**, then **Open** again in the message.
   This shortcut no longer works on macOS 15 and later; use the steps above there.

Allow the connection to the twilite
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The first time the app connects to the twilite, macOS asks: *Allow "Twilite"
to find devices on local networks?* Click **Allow**. The app talks to the twilite over
the network, so without this it cannot connect.

If you clicked *Don't Allow* by mistake: open **System Settings** > **Privacy &
Security** > **Local Network** and switch **Twilite** on, then quit and
reopen the app.

.. note::
   Until the app is signed, macOS treats each new version as a new app. After an update
   you may see both the *Open Anyway* steps and the network question again.

Windows
-------

1. Double-click the file you received, ``Twilite-<version>.msi``.
2. Windows may show *Windows protected your PC*. Click **More info**, then **Run
   anyway**.
3. Follow the installer: click **Next** and **Install**, and **Yes** if Windows asks
   whether to allow changes.
4. Start the app from the **Start** menu: **Twilite**.

Where your files are
--------------------

.. list-table::
   :widths: 22 39 39
   :header-rows: 1

   * -
     - macOS
     - Windows
   * - Measurements
     - ``Twilite`` in your home folder
     - ``C:\Users\<you>\Twilite``
   * - Settings
     - ``~/Library/Application Support/Twilite``
     - ``%LOCALAPPDATA%\Twilite``
   * - Logs (``log.txt``, ``rawlogs``), for problem reports
     - ``~/Library/Logs/Twilite``
     - ``%LOCALAPPDATA%\Twilite\Logs``

You can choose another folder for the measurements in :doc:`settings`.

To open one of the other folders:

- **macOS**: in the Finder, choose **Go** > **Go to Folder...**, paste the path from the
  table (with the ``~``) and press Return. ``~/Library`` is hidden in the Finder
  otherwise.
- **Windows**: press **Windows key + R**, paste the path from the table and press Enter.

Next step
---------

The app starts with a simulated twilite so you can try it. To connect it to your
twilite, see :ref:`Connect to your twilite`.

Update
------

Install the new version as you installed the first one. On macOS, drag it to
**Applications** and choose **Replace**. Your measurements and settings are kept.

Uninstall
---------

- **macOS**: drag **Twilite** from **Applications** to the **Trash** (or **Bin**).
- **Windows**: **Settings** > **Apps** > **Installed apps**, then **Twilite
  Acquisition** > **Uninstall**.

This removes the app only. Your measurements, settings and logs stay in the folders
listed above; delete those folders too if you no longer need them.

If macOS says the app is damaged
--------------------------------

If macOS says *"Twilite" is damaged and can't be opened*, the download was flagged in a
way that the *Open Anyway* steps do not clear. Ask the person who gave you the app for
help. They can fix it with one Terminal command,
``xattr -dr com.apple.quarantine "/Applications/Twilite.app"``.
