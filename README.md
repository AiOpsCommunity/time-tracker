# time-tracker

Thanks for checking the timetracker out! I would love if you would give it a try, and adapt to your own needs. If you make usefull things, please add them through a pull request!

This is a single-file, no-build personal time tracker: start/stop a timer, log past
entries, edit existing ones, see everything grouped by week. The whole app
is one `time_tracker_json.html` (React, loaded from a CDN, no
`npm install`, no build step) talking to a tiny local Python server that
persists everything to one JSON file on disk.

It's a single HTML file on purpose: that makes it trivial to pin as a
bookmark in Chrome (or any browser) and open like any other app, with no
install step.

## Quick start

Requires Python 3 (standard library only, no dependencies to install).

```bash
./start.sh
```

Then open the printed URL (defaults to `http://localhost:8934/time_tracker_json.html`).

Pass a different port if 8934 is taken: `./start.sh 8935`.

All data lives in `data/time-tracking.json`, created automatically on
first run. That file is gitignored, back it up yourself if you care
about the history (it's just JSON, easy to copy/version elsewhere).

## Data model

Two record types: a **client** (with its projects) and a **time entry**. A
time entry's `client`/`project` are picked from a dropdown backed by the
`clients` list, not free text, while `firstName`/`lastName` remain
free-text fields. The last-used client/project/name are remembered in the
browser's `localStorage` (key `timeTrackingDefaults`) so the running-timer
form and a freshly opened "log past entry" modal default to whatever was
used last, instead of resetting every time.

### `clients`: the list of clients and their projects

| Field      | Type     | Example                        | Notes                                    |
|------------|----------|---------------------------------|-------------------------------------------|
| `id`       | string   | (auto)                         | Primary key.                               |
| `name`     | string   | `"Acme"`                       | Unique-in-practice display name.           |
| `projects` | string[] | `["Website", "Mobile app"]`     | Plain array of project names on the client, no separate `projects` table. |

Managed from **Edit clients** in the UI: add a client, add a project
under a client, rename either in place, or delete either. **Deleting
cascades**: deleting a client deletes every time entry with that
`client`, and deleting a single project deletes every time entry with
that `client`+`project`, both gated behind a confirmation dialog that
states how many entries will be lost before committing (see
`deleteClient`/`deleteProject` in `time_tracker_json.html` and the
matching routes in `scripts/json_server.py`). There's no soft-delete/undo;
the confirmation is the only safety net.

On first server start, if `clients` is empty but `timeEntries` already has
data, the server derives client/project records from whatever
client/project strings already exist on past entries, so existing history
stays selectable without manual re-entry.

### `timeEntries`: one record per logged block of time

| Field          | Type    | Example                | Notes                                              |
|----------------|---------|-------------------------|-----------------------------------------------------|
| `id`           | string  | (auto)                 | Primary key.                                        |
| `date`         | string  | `"2026-07-30"`          | ISO `YYYY-MM-DD`, **local calendar date**, not UTC. |
| `task`         | string  | `"Hour logging"`        | Free-standing label, see [Tasks](#tasks) below.     |
| `notes`        | string  | `"Definitions, prompts"`| Optional free text.                                 |
| `startedAt`    | string  | `"09:00"`               | `HH:MM`, 24h, local time.                            |
| `endedAt`      | string  | `"17:31"`                | `HH:MM`, 24h, local time.                            |
| `hours`        | number  | `8.52`                  | Decimal hours, derived from start/end.               |
| `hoursRounded` | number  | `9.0`                   | Same as `hours` in this app (kept for parity with the original schema this project was seeded from; not otherwise used).|
| `client`       | string  | `"Acme"`                | Picked from `clients`, defaults to the last value used. |
| `project`      | string  | `"Website"`             | Picked from the chosen client's `projects`, defaults to the last value used. |
| `firstName`    | string  | `"Jane"`                | Editable text field, defaults to the last value used. |
| `lastName`     | string  | `"Doe"`                 | Editable text field, defaults to the last value used. |
| `source`       | string  | `"app"`                 | Where the entry came from. Not read by the UI, just handy for auditing/debugging. |

`hours` is always `(endedAt - startedAt)` in decimal hours, rounded to 2
decimal places. It is computed client-side when an entry is saved, not
recomputed on read; if you edit `startedAt`/`endedAt` you must recompute
and re-save `hours` too.

### `activeTimer`: at most one record, the in-progress timer

A single well-known record that exists only while a timer is running.
This is what lets you close the tab and reopen it without losing the
running timer.

| Field       | Type   | Notes                                             |
|-------------|--------|-----------------------------------------------------|
| `task`      | string | Same task list as `timeEntries.task`.              |
| `notes`     | string | Editable while the timer runs (synced on blur).    |
| `startedAt` | string | ISO 8601 instant (`Date.toISOString()`), when the timer was started, a real point in time, not a `HH:MM` string. |

Lifecycle:
1. **Start**: write this record with `startedAt = now` (or a backdated
   time if you typed an override).
2. **While running**: the UI reads this record once on load to resume the
   timer after a refresh, and re-derives elapsed time as `now - startedAt`
   every second.
3. **Stop**: read `startedAt` from this record, compute `hours` against
   `now`, write a new `timeEntries` record, then delete this record.

### Tasks

The task list is a plain hardcoded array in the app (`TASKS` in
`time_tracker_json.html`), not a database table. Edit that array to
change the dropdown options. There's no referential integrity: an entry's
`task` is just whatever string was selected at save time, so renaming an
entry in `TASKS` does not retroactively rename past entries.

## Behavior

- **Timer start**: capture `now` (or a typed override time), persist it
  as the active timer, start a 1-second UI tick.
- **Timer stop**: compute `hours` from the persisted start time to `now`,
  write a `timeEntries` record, clear the active timer.
- **Resume on reload**: on app load, check for an active timer; if one
  exists, resume the running clock from its `startedAt` instead of
  starting fresh.
- **Log a past entry**: a modal, pre-filled with a target date (either
  today, or the date of whichever calendar row you clicked), with a
  client/project picker, first/last name fields, a task picker, notes,
  and start/end time fields.
- **Edit an existing entry**: clicking any already-logged entry opens the
  same modal, pre-filled with its current values; saving updates that
  record in place (same ID) rather than creating a new one.
- **Delete an entry**: the edit modal has a "Delete entry" action, gated
  by a plain-language confirm step before the record is actually removed.
- **Bulk-select and delete entries**: each row has a checkbox; shift-click
  extends the selection to a contiguous range from the last checked row.
  A bar above the table shows "Delete N selected" once anything is
  checked, gated by the same kind of confirm step as a single delete.
- **Filter by client/project**: a dropdown above the table, built from the
  distinct client and client+project combinations seen across all entries,
  narrows both the visible rows and each week's total to just that
  client (or client+project).
- **Manage clients**: add, rename, or delete clients and their projects,
  see the [`clients`](#clients-the-list-of-clients-and-their-projects)
  section above for cascade-delete behavior.
- **Remembered client/project/name defaults**: the running-timer form and
  a freshly opened "log past entry" modal (not an edit of an existing
  entry) default `client`/`project`/`firstName`/`lastName` to whatever was
  last used, persisted in the browser's `localStorage`.
- **Loose time entry**: start/end time fields accept `9`, `900`, `9:00`,
  or `9.30` and normalize to `HH:MM` on blur, the goal is to never make
  you type a `:` or a leading zero.
- **Calendar view, not a flat list**: the entries table is built from a
  continuous date range (earliest entry through today), not just the
  dates that have entries. Days with no entry render as a greyed,
  clickable placeholder row (clicking opens the "log a past entry" modal
  pre-filled with that date).
- **Grouped by week**: rows are grouped under a header showing the ISO
  week number and that week's total hours.
- **Local time throughout**: every date/time in this app is your
  browser's local calendar date/time, never UTC.
- **Live-updating table**: the browser polls the server every few seconds
  for changes, so edits made from another tab/window eventually show up
  without a manual refresh.

## How it's built

`time_tracker_json.html` is a React app (no JSX build step, it uses the
[`htm`](https://github.com/developit/htm) tagged-template library instead)
loaded entirely from CDN imports. All backend calls are plain `fetch()`
requests against `/api/...`, served by `scripts/json_server.py`:

| Operation                          | Route                                  |
|-------------------------------------|------------------------------------------|
| List time entries                   | `GET /api/entries`                       |
| Create a time entry                 | `POST /api/entries`                      |
| Update a time entry                 | `PUT /api/entries/<id>`                  |
| Delete a time entry                 | `DELETE /api/entries/<id>`               |
| Bulk-delete time entries            | `POST /api/entries/bulk-delete`          |
| Get / set / clear the active timer  | `GET` / `PUT` / `DELETE /api/timer`      |
| List clients                        | `GET /api/clients`                       |
| Create a client                     | `POST /api/clients`                      |
| Rename / update a client's projects | `PUT /api/clients/<id>`                  |
| Delete a client (or one project)    | `DELETE /api/clients/<id>[?project=...]` |

The server (`scripts/json_server.py`) is a single Python file using only
the standard library (`http.server`, `json`), no dependencies to
install. It reads the whole `data/time-tracking.json` file, mutates it in
memory, and writes it back whole on every request, guarded by a lock so
concurrent requests don't corrupt the file. This is intentionally simple:
fine for one person using the app from a browser or two, not meant for
concurrent multi-writer use.

See [DEVELOPING.md](DEVELOPING.md) for how to run, test, and verify
changes to this app.
