# MMFP UI Prototype

A non-production design reference for the Model Fitness Platform UI, generated using Claude Design.

## What this is

A working in-browser prototype of the three primary MMFP pages:

- **Scoreboard** — tier cards with candidate ranking, trend strips, drill-down detail
- **Editor** — rubric editing with live impact preview
- **Curator** — dataset examples + judge sample queue

It also includes the History panel, promotion modal, and a `tweaks-panel` for live design adjustments.

## What this is NOT

- This is **not production code**. Don't import from these files into the real `ui/` Next.js app.
- This is **not a build target**. The Slice 1 walking skeleton replaces this with a real Next.js app served from a Container App.
- The .jsx files use **Babel-in-browser via CDN** (suitable for prototyping only). The production app uses TypeScript and a real bundler.

## How to view

The prototype must be served via a local HTTP server, **not** opened directly via `file://`. Browsers block cross-origin XHR for `file://` URLs, which breaks Babel-in-browser script loading.

From this directory:

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000/index.html`.

Alternatively `npx serve` works the same way.

No build step, no `npm install` of project dependencies. Just a basic HTTP server.

## How this informs the production UI

When the production UI is built (Slices 2-6), each page lifts:

- **Visual style** (colours, type, spacing, layout) from the .jsx files and `assets/colors_and_type.css`
- **Component primitives** (buttons, inputs, cards, modals) from `primitives.jsx`
- **Page structure** (which elements appear where) from `shell.jsx` + the per-page `.jsx` files

The TypeScript components in `ui/components/` should match the prototype's visual style as closely as possible. Discrepancies indicate either a deliberate evolution (document it) or a regression (fix it).

## Files

| File | Purpose |
|---|---|
| `index.html` | Entry point, loads all .jsx files |
| `shell.jsx` | App shell — top nav, layout |
| `scoreboard.jsx` | Scoreboard page |
| `editor.jsx` | Editor page |
| `curator.jsx` | Curator page |
| `history.jsx` | History panel (drawer) |
| `primitives.jsx` | Shared design primitives |
| `tweaks-panel.jsx` | Live design tweaks panel (dev tool) |
| `data.jsx` | Mock data for the prototype |
| `assets/colors_and_type.css` | Design tokens |
| `assets/*.svg` | Logos |

A static print-friendly snapshot is at `docs/ui/prototype-print.html`.