# Calendar acquisition

`reterminal calendar-export` reads the Google calendar through the installed `gws`
CLI and atomically writes a JSON source for calendar providers. It never changes
Google Calendar. Select the account with `--config-dir` and the exact calendar
name or ID with `--calendar`; ambiguous names fail without replacing the source.

```bash
env -u VIRTUAL_ENV uv --directory python run reterminal calendar-export \
  --config-dir "$HOME/.config/gws-amadad" \
  --calendar Family \
  --destination "$PWD/artifacts/local/family-calendar.json"
```

The default window contains all of today and the next 20 calendar days in
America/New_York. Raw `calendar events list` requests start at local midnight,
expand recurring instances, and follow every page. This retains today's ended
events, which the upcoming-only `+agenda` helper can omit. Event IDs, actual start
and end times, tentative status, and location are preserved. Times in titles are
never interpreted as appointment times. All-day end dates remain exclusive.

The source includes its timezone, inclusive window dates, successful `checked_at`,
and calendar/account provenance. `checked_at` advances only after a successful,
validated response; render time and file modification time are not source checks.
Failed requests, invalid payloads, and incomplete pagination leave both the last
good file and its modification time unchanged. Cancellation tombstones disappear
from this complete replacement source. The source is private local data and must
remain untracked.

## Recurring operation

`scripts/reterminal-calendar-export.sh` runs the command and defaults to the
repository's ignored `artifacts/local/family-calendar.json`. Its settings can be
overridden with `RETERMINAL_CALENDAR_OUTPUT`, `RETERMINAL_CALENDAR_CONFIG_DIR`,
`RETERMINAL_CALENDAR_NAME`, `RETERMINAL_TIMEZONE`, `GWS_BIN`, and `UV_BIN`.

Use `scripts/sh.reterminal.family-calendar.example.plist` as the system
LaunchDaemon template. It runs at load and every 1,200 seconds under the user's
account, with the existing gws file keyring backend. Replace placeholder paths
and username in a local copy. Create the log directory before loading the job.

To migrate an existing installation, first run the exporter successfully once,
preview a manifest using the JSON destination, and save the existing plist and
manifest. Replace the existing `sh.reterminal.family-calendar` job; do not install
a second calendar refresh job. Installing a changed ProgramArguments list needs
`launchctl bootout` followed by `bootstrap`, rather than only `kickstart`:

```bash
sudo launchctl bootout system/sh.reterminal.family-calendar
sudo install -o root -g wheel -m 644 artifacts/local/family-calendar-next.plist \
  /Library/LaunchDaemons/sh.reterminal.family-calendar.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/sh.reterminal.family-calendar.plist
```

Check the job's exit status, the source's `checked_at`, and a rendered preview
before switching the active manifest. Restore the saved plist and bootstrap it
if the replacement cannot start. Restart the publisher when Python modules have
changed; source-file hot reload alone does not load new code.

The exporter must be able to use gws's existing credential cache. A sandbox that
prevents gws from updating its account directory may block otherwise read-only
Google requests; the scheduled job must run in its normal user environment.
