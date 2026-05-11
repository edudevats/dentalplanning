# Personal Finance UI Kit

Hi-fi recreation of the **Estado de Resultados Personal** feature for Dental Planning, built with the existing token system (cyan primary, Poppins/Open Sans, slate surfaces, 12 px radii).

## Files

- `index.html` — interactive Dashboard + Add Movement modal (FAB)
- `Atoms.jsx` — Button, Card, StatCard, Badge, Field, TextInput, Select, Icon
- `Shell.jsx` — Sidebar (with new "Finanzas Personales" section), Topbar, PageShell, FAB
- `Charts.jsx` — Donut, BarChart, ProgressArc, CategoryLegend (hand-rolled SVG, no Chart.js dependency)
- `Dashboard.jsx` — MonthSelector, InsightStrip, KPI grid, charts, top categorías, últimos movimientos
- `AddMovementModal.jsx` — TypeToggle (Ingreso/Gasto), big-amount input, CategoryGrid picker, Modal shell
- `data.jsx` — Mock categorías, ingresos, gastos, 6-month history

## Design decisions

- **Not Excel:** zero tables on the dashboard. Categorías shown as horizontal mini bar lists; movements as vertical "bank app" rows with icon chips.
- **Insight strip** at the top (gradient from `primary-50 → accent-100`) — auto-generated takeaway, the "PRO" tier from the user's brief.
- **Modal-first add flow:** FAB opens a single modal that toggles Ingreso/Gasto in-place, big amount input front-and-center, categorías as a tap-grid (not a dropdown).
- **Categorías get icon-based color identity** (`comida` amber, `vivienda` violet, `transporte` cyan, etc.) so users recognize them across pie / list / row.
- **Sparingly colored numbers:** ingresos green, gastos red, balance teal, ahorro % teal.

## What's missing / placeholders

- No real backend wiring — `data.jsx` is static.
- Detail-by-category screen (Nivel 2) and full transaction-list screen (Nivel 3 history) are not yet built — the dashboard's "Ver todas / Ver historial" links are stubs.
- Goal-tracking screen (Metas) is sidebar-stubbed but not implemented.
