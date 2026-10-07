=================
 plausible-stats
=================

Fetch daily statistics from https://analytics.python.org/.

Run ``uv run fetch_stats.py`` to fetch yesterday's reports. The script saves
CSV exports and their JSON equivalents under ``stats/<site>_<date>/``.

Page reports in dashboard ZIP exports contain only the top 100 pages. The
``*.pages.json`` files instead use the public dashboard's ``/api/stats/<site>/pages``
endpoint, requesting batches of 1000 and following ``page=1,2,...`` until an empty
batch is returned. They retain the existing column names and string-valued metrics.
Other reports still come from the ZIP export; the ZIP itself remains limited.

URL prefixes match the beginning of the path: ``3`` includes ``/3/bugs.html``
and excludes ``/pl/3/bugs.html``. Dots in version prefixes are matched literally.
The dashboard endpoint currently works without an API key for these public sites,
but it is an internal API and its format may change.

Existing snapshots remain unchanged.

Run regression tests with
``uv run --with 'urllib3>=2' python -m unittest discover -v``.
