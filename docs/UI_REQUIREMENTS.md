# Route Viewer — UI Requirements

**Status:** Draft for review  
**Audience:** Solo developer (Daniel) building FinishLine route-viewer  
**Last updated:** June 2026  
**Branch context:** `feat/catalog-tiles-multi-customer-ingest` — catalog ingest, tile build, catalog map-match, and `activity_segment_usage` exist; segment aggregation and segment-centric map are not built yet.

---

## 1. Purpose

This document defines UI and workflow requirements so day-to-day work does **not** depend on memorizing API URLs, deep links, Swagger, or pytest fixtures. The interface should support:

1. **Browsing** a customer's activities with useful metadata (date, distance, type, place).
2. **Inspecting** one activity at a time — raw GPS vs catalog-matched geometry — with fast prev/next navigation.
3. **Operating** the catalog pipeline (coverage → build tiles → match) from the same context as the map.
4. **Evolving** toward segment-centric visualization without throwing away the activity browser.

The current map panel grew organically around multi-select export and legacy GraphHopper controls. **A ground-up panel redesign is expected**; this doc describes what the new experience must do, not how to preserve today's layout.

---

## 2. Goals & Success Criteria

| Goal | Success looks like |
|------|-------------------|
| Single-activity review | Pick any activity; see raw and matched on the map in &lt;2 s without re-loading the whole customer batch. |
| Customer context | Switch customers in one action; UI remembers last customer per session. |
| Find activities | Filter/sort by date, distance, type, region/place; locate "that 10 km run in Allentown last March" without scrolling 200 rows. |
| Match workflow | See catalog readiness, run match, see result status — without leaving the map. |
| Shareable state | URL encodes customer + activity + layer toggles so bookmarks and Slack links work. |
| Honest metadata | Location shows human place (city/state) when possible, not only lat/lon. |

**Non-goal for this phase:** Polished production design system, auth/multi-user, or mobile-first layout. Desktop-first local dev tool is fine.

---

## 3. Users & Primary Workflows

### 3.1 Persona: Developer / operator (you)

You ingest Garmin exports for named customers, build catalog tiles for geography you care about, map-match activities to validate matcher quality, and eventually inspect segment usage heatmaps.

### 3.2 Workflow A — Review one matched activity

```
Select customer → Filter/browse activities → Select one activity
  → Map shows raw (optional) + matched (default)
  → Prev/Next through filtered list
  → Optional: open segment list for activity
```

Today this requires: ingest on Home → open Map → type customer ID → find row in checkbox list → toggle layers → maybe deep link `?customer=&activity=`. Too many steps; loading all GeoJSON upfront is slow.

### 3.3 Workflow B — Onboard a new customer export

```
Enter customer + source path → Ingest (progress visible)
  → Redirect/switch to Map with that customer active
  → See activity count + catalog coverage summary
  → Build pending tiles (batch or per-region)
  → Match selected or all ready activities
```

Today ingest lives on a separate page with raw JSON output; catalog build has no UI.

### 3.4 Workflow C — Compare matcher changes

```
Same customer + activity pinned in URL
  → Re-run catalog match
  → Map refreshes matched layer; segment count / confidence visible
  → Toggle raw vs matched without losing selection
```

### 3.5 Workflow D — Future: segment usage (out of scope for v1 UI, in scope for architecture)

```
Select customer + region or bbox
  → Map shows network_segments colored by segment_stats
  → Click segment → usage count, sample activities
```

The v1 UI should **not block** this (e.g. avoid hard-coding "activity polyline only" as the only map mode).

---

## 4. Current State & Pain Points

### 4.1 What exists

| Area | Today |
|------|--------|
| Routes | `/` (Home ingest), `/map` (map + drawer) |
| Customer filter | Free-text field on map; not synced with Home |
| Activity list | Checkbox multi-select table in bottom drawer |
| Layers | Raw GPS, Matched, Basemap, selected-only toggles |
| Actions | Catalog Match, Export SVG, rectangle select |
| Deep link | `?customer=&activity=` partially supported |
| APIs unused in UI | `GET /catalog/coverage`, `POST /catalog/build`, `GET /activities/{id}/segments`, `GET /regions`, customer list (no list endpoint yet) |

### 4.2 Pain points (why rebuild the panel)

1. **No single-activity focus** — Checkbox model optimizes bulk export, not "click this run and look at it."
2. **No prev/next** — Cannot walk through chronological activities while staring at the map.
3. **Heavy loading** — Changing customer or filter re-fetches GeoJSON for *every* activity in the list.
4. **Disconnected pages** — Home ingest and Map are separate; customer ID re-entered manually.
5. **Weak location** — "Start" column is `lat, lon` from first coordinate, not city/state.
6. **Toolbar overload** — Many checkboxes (raw selected-only, matched selected-only, snap debug, GPS accuracy) without grouping; legacy GraphHopper-era controls mixed with catalog match.
7. **No catalog visibility** — Cannot see pending vs ready tiles or kick off build without API/Swagger.
8. **Match feedback** — `alert()` dialogs; `match_status` buried in list row text.
9. **No ingest on map** — Must context-switch to Home to add data.
10. **Hard to test visually** — Relying on deep links and backend scripts instead of a guided UI.

---

## 5. Design Principles

1. **Customer is global context** — Almost every view is scoped to one customer; switching customer is always one click away and updates URL.
2. **One active activity** — Primary interaction is a single *focused* activity; multi-select becomes a secondary/bulk mode.
3. **Lazy map data** — Load GeoJSON for the focused activity (and optionally a small preview set), not the full fleet.
4. **Progressive disclosure** — Default view is simple (customer, list, map, raw/matched toggle); advanced tools (catalog build, snap debug, export) in expandable sections.
5. **URL is state** — Bookmarkable: customer, activity, filters, layer mode.
6. **Pipeline visible** — Show ingest → catalog coverage → match as a status strip, not hidden backend steps.
7. **Prepare for segments** — Activity detail should link to segment list; map component should accept a future "segment layer" mode.

---

## 6. Information Architecture

Proposed top-level navigation (desktop):

```
┌─────────────────────────────────────────────────────────────┐
│  Route Viewer    [Customer ▼]    Activities | Catalog | …  │  ← app chrome
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  Activity    │              Map                             │
│  browser     │         (primary canvas)                     │
│  panel       │                                              │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### 6.1 Views / routes (recommended)

| Route | Purpose |
|-------|---------|
| `/` or `/activities` | Default workspace: customer + activity browser + map (single page). |
| `/catalog` | Optional dedicated catalog tile map/table; may be a tab on main workspace instead. |
| `/ingest` | Ingest form; may be modal/drawer from main workspace rather than separate home page. |

**Recommendation:** Collapse Home into the main workspace as an **Ingest drawer** so you never leave the map context after ingest.

### 6.2 Layout regions (main workspace)

| Region | Responsibility |
|--------|----------------|
| **App header** | Customer selector, global search, ingest entry, health indicator. |
| **Left sidebar** | Activity browser (filters, sort, list, focus + prev/next). Resizable; collapsible. |
| **Map** | Basemap + geometry layers + optional segment layer (future). |
| **Activity detail strip** | Below header or above map: name, date, distance, type, place, match status, segment count. |
| **Footer / status bar** | Catalog coverage summary, loading indicators, last action result. |

---

## 7. Customer Context

### 7.1 Requirements

| ID | Requirement |
|----|-------------|
| CUST-1 | Display active `customer_id` and optional display name everywhere in the workspace. |
| CUST-2 | Customer switcher: dropdown of known customers **plus** "type new ID" option. |
| CUST-3 | Persist last-selected customer in `sessionStorage` (and URL query `?customer=`). |
| CUST-4 | Switching customer clears focused activity, resets filters, updates activity list. |
| CUST-5 | Show per-customer summary: activity count, date range, catalog complete yes/no. |
| CUST-6 | After ingest, auto-select that customer and refresh list. |

### 7.2 Backend gaps (UI depends on)

- **`GET /customers`** — List customers with `customer_id`, `name`, `activity_count`, `first_activity_at`, `last_activity_at`. Required for dropdown; today only implicit via activities table.
- Optional: **`GET /customers/{id}/summary`** — Coverage %, regions count, matched count.

---

## 8. Activity Browser

The activity browser replaces the current checkbox drawer as the **primary navigation surface**.

### 8.1 List columns (minimum)

| Column | Source | Notes |
|--------|--------|-------|
| **Date** | `started_at` | Primary sort default: newest first. Show local date + optional time. |
| **Name** | `name` or `source_file` | Ellipsis + tooltip for full text. |
| **Type** | `activity_type` | Icon or short label (run, ride, walk, …). |
| **Distance** | `distance_m` | Formatted: `10.7 km` / `6.6 mi` (unit preference optional). |
| **Place** | *derived* | City, State — see §8.3. |
| **Match** | `match_status` | Badge: pending / matched / failed / partial. |
| **Segments** | from `/segments` or match result | Show after matched; "—" if pending. |

Remove raw `activity_id` from default columns; show in detail panel or copy button.

### 8.2 Interaction model

| ID | Requirement |
|----|-------------|
| ACT-1 | **Single click** on row sets *focused activity* (highlighted row, drives map). |
| ACT-2 | **Prev / Next** buttons (and keyboard ← →) move focus through the *filtered* list. |
| ACT-3 | **Shift+click** or toggle "Bulk select" mode for multi-select (export, batch match). |
| ACT-4 | Sorting: date, distance, name, type, place, match status. |
| ACT-5 | Filters: type, date range, distance range, match status, region, text search (name/file). |
| ACT-6 | Empty state: "No activities — Ingest data" with CTA. |
| ACT-7 | Row shows loading skeleton while focused activity GeoJSON fetches. |

### 8.3 Location (city / state)

| ID | Requirement |
|----|-------------|
| LOC-1 | Show **City, ST** (or country for non-US) as primary location label. |
| LOC-2 | Fallback order: (a) reverse-geocode start point once and cache on activity or in frontend cache, (b) region name from `GET /regions`, (c) rounded lat/lon. |
| LOC-3 | Filter by region cluster (`region_id`) using human region label (e.g. `40.59°N, 75.52°W` or improved name). |
| LOC-4 | Optional map hover: start pin with coordinates in tooltip. |

### 8.4 Backend gaps

- **`start_place` or geocode cache** — Either store `city`, `state`, `country` at ingest (preferred), or add `GET /activities/{id}/place` that reverse-geocodes once.
- Activities list should support **`start` / `end` date query params** (API already has `start`/`end` on `GET /activities`).
- Expose **`region_id`** and region display name in list response.

---

## 9. Map View & Geometry Layers

### 9.1 Layer modes (mutually clear, not six checkboxes)

| Mode | Behavior |
|------|----------|
| **Matched only** (default when `match_status=matched`) | Blue catalog-matched path. |
| **Raw only** | Orange GPS track. |
| **Split / compare** | Both layers; matched solid, raw dashed or offset styling. |
| **Segments** (future) | Highlight segments from `activity_segment_usage` along matched path. |

Implement as a **3-way control**: `Raw | Both | Matched` (or segmented button group).

| ID | Requirement |
|----|-------------|
| MAP-1 | Map auto-fits to focused activity geometry when focus changes. |
| MAP-2 | Fetch `GET /activities/{id}/geojson` and `?variant=matched` **only for focused activity** (plus any bulk-selected if in bulk mode). |
| MAP-3 | Unmatched activities never load matched GeoJSON until requested (avoid 404 noise). |
| MAP-4 | Show start/end markers on focused activity. |
| MAP-5 | Match status overlay on map: confidence, segment count, points matched — from last match or `GET /activities/{id}/segments`. |
| MAP-6 | Basemap toggle stays (OSM default). |
| MAP-7 | Deep link `?customer=X&activity=Y&layer=matched` restores view. |

### 9.2 De-emphasize / relocate legacy controls

| Control | Disposition |
|---------|-------------|
| GPS accuracy input | Remove from default UI (catalog matcher uses env defaults). Advanced drawer if ever needed. |
| Show snapped points | Debug panel only. |
| Rectangle multi-select | Bulk mode only, or map lasso later. |
| GraphHopper inspect click | Debug panel only; catalog inspect TBD. |

### 9.3 Activity detail (map-adjacent)

When an activity is focused, show a compact **detail card**:

- Title, date/time, type, distance, duration  
- Place (city/state), region  
- Source file name  
- Match: status, confidence, segment count, last matched time (if stored)  
- Actions: **Match / Re-match**, **View segments**, **Export** (this activity)  
- Link: copy activity URL  

---

## 10. Catalog & Match Workflow UI

### 10.1 Catalog coverage strip

Visible whenever a customer is selected:

| ID | Requirement |
|----|-------------|
| CAT-1 | Call `GET /catalog/coverage?customerId=` and show: `N/M tiles ready`, progress bar or badge. |
| CAT-2 | If not complete: list count of `pending` / `building` / `failed` tiles. |
| CAT-3 | **Build tiles** action: `POST /catalog/build` with `customerId` + `limit` (default 5–10), show per-tile result toast/log. |
| CAT-4 | Link/tab to **Catalog explorer**: table or map of tiles colored by status (optional v1.1). |

### 10.2 Match actions

| ID | Requirement |
|----|-------------|
| MAT-1 | **Match focused** — `POST /mapmatch` with single id; inline progress spinner on detail card. |
| MAT-2 | **Match all pending** (customer scope, optional filter: ready catalog only). |
| MAT-3 | On success: refresh matched layer, segment count, `match_status` badge; no blocking `alert()`. |
| MAT-4 | On failure: show error from API (`catalog incomplete`, `no segments in bbox`, etc.) with link to catalog strip. |
| MAT-5 | If partial catalog: show which tiles missing; offer build action. |

### 10.3 Segments panel (v1 — read-only)

| ID | Requirement |
|----|-------------|
| SEG-1 | Drawer or tab: `GET /activities/{id}/segments` — table segment_id, traversals, length. |
| SEG-2 | Optional: click segment row → highlight on map when segment geometry endpoint exists. |

---

## 11. Ingest UI

| ID | Requirement |
|----|-------------|
| ING-1 | Ingest accessible from header ("Add data") — modal or slide-over, not a separate orphan page. |
| ING-2 | Fields: customer ID, optional name, source path (text input; folder picker later if feasible). |
| ING-3 | Live progress from `GET /ingest/progress` (same as today but inline). |
| ING-4 | On completion: summary (# new, updated, removed, regions, catalog tiles registered); button **Go to activities**. |
| ING-5 | Raw JSON response available in collapsible "Details" for debugging — not the primary output. |

---

## 12. Export & Bulk Operations

Bulk mode is **secondary**.

| ID | Requirement |
|----|-------------|
| EXP-1 | Export focused activity (GeoJSON raw/matched, SVG matched). |
| EXP-2 | Bulk export when multiple selected — current SVG export behavior. |
| EXP-3 | Bulk catalog match when multiple selected. |

---

## 13. URL State & Persistence

| Parameter | Meaning |
|-----------|---------|
| `customer` | Active customer ID |
| `activity` | Focused activity ID |
| `layer` | `raw` \| `matched` \| `both` |
| `type` | Activity type filter |
| `from` / `to` | Date range (ISO date) |
| `region` | `region_id` filter |

On load, apply URL → state → fetch. On state change, update URL (`replaceState` to avoid history spam on every filter keystroke; pushState on activity change).

---

## 14. Performance Requirements

| ID | Requirement |
|----|-------------|
| PERF-1 | Activity list (metadata only) loads in &lt;500 ms for 500 activities. |
| PERF-2 | Focus change loads and renders one activity GeoJSON in &lt;1 s typical. |
| PERF-3 | Do not fetch all GeoJSON when customer loads — **list endpoint only**. |
| PERF-4 | Debounce filter changes (300 ms) before refetching list. |
| PERF-5 | Show explicit loading states; cancel in-flight fetch on rapid prev/next. |

---

## 15. Visual & UX Notes (lightweight)

- **Color convention:** Keep raw = orange (`#ff5a1f`), matched = blue (`#1479ff`) for continuity with today.
- **Focused row** — Strong left border or background; visible when sidebar scrolled.
- **Panel width** — Default 320–400 px sidebar; resizable.
- **Typography** — System font stack is fine; prioritize readable tabular numbers for distance/date.
- **Errors** — Inline banners, not only `alert()`.
- **Keyboard** — `j`/`k` or arrows for list navigation; `/` focuses search.

Full design system (tokens, components) is out of scope until requirements stabilize.

---

## 16. Phased Delivery (suggested)

### Phase 1 — Activity workspace (highest value)

- Merge customer + activity list + map on one page  
- Customer selector + URL state  
- Single-activity focus + prev/next  
- Lazy GeoJSON loading  
- Raw / Matched / Both toggle  
- Activity detail strip with match status  
- Ingest drawer  

**Enables:** Daily matcher QA without deep links.

### Phase 2 — Catalog operations

- Coverage strip + build tiles button  
- Match focused / match failures inline  
- Segments read-only drawer  

**Enables:** End-to-end catalog pipeline from UI.

### Phase 3 — Metadata & polish

- City/state at ingest or geocode cache  
- Region filter  
- Bulk mode refactor  
- Debug tools panel  

### Phase 4 — Segment-centric map (FinishLine target)

- `segment_stats` heatmap layer  
- Aggregation filters  
- Export from segments  

---

## 17. Open Questions (for review)

1. **Default layer when opening unmatched activity** — Raw only, or raw+both with matched disabled until match run?  
2. **Units** — Metric only, or user toggle km/mi?  
3. **Customer list** — Is typing a new customer ID enough for v1, or is dropdown mandatory day one?  
4. **Reverse geocoding** — At ingest (offline Nominatim once per activity) vs on-demand in UI?  
5. **Separate Catalog tab** — Tile map vs inline coverage strip only?  
6. **Multi-customer compare** — Ever needed on same map, or always single-customer scope?  
7. **Retention** — Show deleted-on-reingest activities, or only current snapshot?  
8. **Activity name editing** — Needed in UI, or read-only from file?  

---

## 18. Acceptance Checklist (Phase 1)

Use this to sign off on the first UI milestone:

- [ ] Open app → last customer restored or picker shown  
- [ ] Select customer → activity list loads without loading all tracks on map  
- [ ] Click activity → map shows track; URL updates  
- [ ] Prev/Next walks filtered list; map and URL follow  
- [ ] Toggle Raw / Matched / Both without losing focus  
- [ ] Ingest from workspace → new activities appear; customer stays selected  
- [ ] Match focused activity → matched line appears; status badge updates  
- [ ] No `alert()` for routine success paths  
- [ ] Deep link `?customer=&activity=` opens correct view  

---

## 19. Related Docs & APIs

| Resource | Use |
|----------|-----|
| [README.md](../README.md) | Architecture, env vars, roadmap |
| [backend/SCHEMA.md](../backend/SCHEMA.md) | Data model |
| `GET /activities` | List + filters |
| `GET /activities/{id}/geojson` | Raw / matched geometry |
| `GET /activities/{id}/segments` | Segment usage |
| `GET /catalog/coverage` | Tile readiness per customer |
| `POST /catalog/build` | Build pending tiles |
| `POST /mapmatch` | Catalog match |
| `GET /regions` | Region clusters |
| `POST /ingest` | Import activities |

---

## 20. Summary

The UI should pivot from **"checkbox list + overloaded toolbar"** to **"customer-scoped activity browser with one focused activity driving the map."** Catalog build and match belong in the same workspace as visualization. Location, date, distance, and type should be first-class filter/sort dimensions — with city/state added as soon as backend or geocode cache supports it. The panel can be rebuilt from scratch; these requirements define the behavior that matters for FinishLine progress and for replacing today's test/deep-link workflow.
