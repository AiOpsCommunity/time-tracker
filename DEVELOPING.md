# Developing this app

This is a single-file, no-build app (`time_tracker_json.html`) backed by a
tiny local Python server (`scripts/json_server.py`) that persists to one
JSON file on disk. There's no `npm install`, no dev server config, no test
suite, which means an AI coding agent (Claude Code, Cursor, etc.) has no
automatic signal that a change actually works. This doc is the missing
piece: how to run the app, drive it in a real browser, and verify a change
before calling it done.

**This is the intended workflow for any change to `time_tracker_json.html`
or `scripts/json_server.py`**: a change that "looks right" by reading the
diff but was never actually run is not verified.

## Branch naming

Branches follow `{name}/{type}/branch_name`, e.g. `alex/feat/button`.

`type` is one of:

- `feat`: a new feature or capability
- `bugfix`: fixing broken behavior
- `refactor`: restructuring code, which may also change how something
  behaves (e.g. reworking how a button works, not just its internals)
- `chore`: maintenance that isn't a feature or fix (deps, tooling, docs)

## 1. Run the app

```bash
./start.sh          # defaults to port 8934
./start.sh 8935      # or pick a different port
```

This starts `scripts/json_server.py`, which serves the HTML file and a
JSON REST API from the same origin, backed by `data/time-tracking.json`
(created automatically on first run). Check it's actually serving:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8934/time_tracker_json.html
# expect 200
```

Stop it with Ctrl-C, or if it's running in the background:

```bash
lsof -ti:8934 -sTCP:LISTEN | xargs -r kill
```

Since there's a real server behind this app (unlike a pure static-file
setup), you can also exercise the API directly with `curl` before touching
a browser at all, fast feedback for backend changes:

```bash
curl -s http://localhost:8934/api/clients
curl -s -X POST http://localhost:8934/api/clients -d '{"name":"Test","projects":[]}'
curl -s http://localhost:8934/api/entries
```

## 2. Drive it with Playwright, not a manual browser

An agent in a terminal/container can't open a real browser window. Use
headless Playwright instead, it's the only way to click buttons, fill
inputs, and see what actually rendered.

Install once per environment:

```bash
npm install playwright
npx playwright install chromium --with-deps
```

Then drive the app from a throwaway `.mjs` script (put these in a scratch
directory, not the repo):

```js
import { chromium } from 'playwright'

const browser = await chromium.launch({ args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1100, height: 900 } })

// Always wire these up: a page can render its shell while everything
// underneath silently throws.
page.on('console', (msg) => { if (msg.type() === 'error') console.log('CONSOLE ERROR:', msg.text()) })
page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message))

await page.goto('http://localhost:8934/time_tracker_json.html')
await page.waitForSelector('h1:has-text("Time tracking")')
await page.waitForTimeout(1000) // let the initial fetch() calls settle

// ... click/fill/assert the thing you changed ...

await page.screenshot({ path: 'my-check.png' })
await browser.close()
```

Run it with `node your-script.mjs`.

### Gotchas specific to this app

- **React controlled inputs**: don't `eval el.value = '…'`, it won't fire
  React's `onChange`/`onInput`. Use Playwright's `fill`/`type`/`click`,
  they go through the real input pipeline.
- **Polling isn't instant**: the app polls the server every few seconds
  for entries/clients rather than pushing updates live. After a write,
  the UI also triggers an immediate re-fetch, but if you're asserting on
  data written some other way (e.g. directly via `curl` or editing
  `data/time-tracking.json` by hand), wait for the next poll tick or
  reload the page.
- **Full-screen overlays intercept clicks**: several UI pieces (`.overlay`,
  modals) sit on top of the page. If a click times out with "element
  intercepts pointer events," you're clicking through an overlay: target
  the actual overlay/element, or click an empty corner to close it.
- **This app writes to a real local file** (`data/time-tracking.json`)
  every time you exercise it. Clean up whatever you create during testing:
  delete test clients/entries through the UI, or just delete
  `data/time-tracking.json` and let the server recreate it empty on next
  start.

## 3. Look at the screenshot

Don't just check that Playwright didn't throw, actually read the
screenshot back (most agent tools can view an image file directly). A
blank frame, a popover rendered in the wrong place, or unreadable
low-contrast text in dark mode are all things a passing script can miss
but a screenshot catches immediately. This app supports both light and
dark color schemes (`color-scheme: light dark` in the `<style>` block);
when checking anything involving new UI chrome (popovers, modals, buttons),
check it in dark mode too:

```js
const page = await browser.newPage({ colorScheme: 'dark' })
```

## 4. Sanity-check syntax before opening a browser at all

Since there's no build step, a typo won't be caught until the module fails
to parse in the browser console. Catch it cheaper first:

```bash
node -e "
const fs = require('fs')
const html = fs.readFileSync('time_tracker_json.html', 'utf8')
const match = html.match(/<script type=\"module\">([\s\S]*)<\/script>/)
fs.writeFileSync('/tmp/extracted.mjs', match[1])
"
node --check /tmp/extracted.mjs && echo OK
```

This only catches syntax errors (unbalanced brackets, bad template
literals); it does not run the code or catch logic bugs. It's a fast
pre-check before the slower Playwright step, not a replacement for it.

## 5. Changes to the server (`scripts/json_server.py`)

It's a single file using only the Python standard library
(`http.server`, `json`, `uuid`, `threading`), no dependencies to
install. After any change:

```bash
python3 -m py_compile scripts/json_server.py && echo OK
```

then restart it and re-run the `curl`/Playwright checks above. The whole
data file is read and rewritten on every request (see the module
docstring); if you change the JSON shape, remember `data/time-tracking.json`
from before your change won't automatically migrate; delete it in dev to
start fresh, or write a small migration if this matters for real data.
