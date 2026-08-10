# Vendored browser dependencies

## Chart.js

- **Package:** `chart.js`
- **Pinned release:** `4.5.1`
- **Distribution:** `dist/chart.umd.min.js`
- **Source URL:** `https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js`
- **SHA-256:** `48444a82d4edcb5bec0f1965faacdde18d9c17db3063d042abada2f705c9f54a`
- **License:** MIT

The production dashboard serves the checked-in local copy at
`/static/vendor/chart.umd.min.js`; it does not request Chart.js from a CDN at runtime.

When upgrading, download an explicit upstream release, replace the local distribution,
recalculate the SHA-256, update this file, run the dashboard checks, and review the
Chart.js migration notes before committing.
