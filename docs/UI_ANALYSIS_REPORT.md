# KITTY Web UI Analysis Report

**Date:** December 15, 2025
**Analyst:** Claude Code
**Scope:** Full analysis of the KITTY web UI at `http://localhost:4173`

---

## Executive Summary

The KITTY web UI is largely functional with 10 main pages accessible from the menu. However, several issues were identified including broken API endpoints, duplicate code files, stale Docker builds, and minor UI inconsistencies.

**Critical Issues:** 2
**Major Issues:** 3
**Minor Issues:** 4

---

## Pages Analyzed

| Page | Route | Status | Notes |
|------|-------|--------|-------|
| Home/Menu | `/` | Working | 10 menu cards displayed |
| Voice | `/voice` | Working | Voice assistant with history sidebar |
| Shell | `/shell` | Working | Interactive chat with model selection |
| Fabrication Console | `/console` | Working | CAD generation + Mesh segmenter |
| Projects | `/projects` | Working | Shows 18 STL files in library |
| Dashboard | `/dashboard` | Working | Devices/Cameras/Materials tabs |
| Media Hub | `/media` | Working | Image generation + gallery |
| Research Hub | `/research` | Working | Research templates + history |
| Intelligence | `/intelligence` | **BROKEN** | API endpoint 404 error |
| Settings | `/settings` | Working* | Required Docker rebuild |
| Wall Terminal | `/wall` | Working | Remote read-only mode |

---

## Critical Issues

### 1. Intelligence Page - API Endpoint Broken
**Location:** `/intelligence` route, `PrintIntelligence.tsx:93`
**Error:** `Failed to load statistics`
**Root Cause:** Route ordering bug in `services/fabrication/src/fabrication/app.py`

The endpoint `/api/fabrication/outcomes/statistics` (line 1259) is defined AFTER `/api/fabrication/outcomes/{job_id}` (line 1151). FastAPI matches routes in order, so `statistics` is interpreted as a `job_id`, returning "Outcome not found: statistics".

**Fix Required:** Move the `/api/fabrication/outcomes/statistics` route definition BEFORE the `/api/fabrication/outcomes/{job_id}` route.

```python
# CURRENT ORDER (broken):
@app.get("/api/fabrication/outcomes/{job_id}")  # Line 1151
@app.get("/api/fabrication/outcomes/statistics")  # Line 1259

# CORRECT ORDER:
@app.get("/api/fabrication/outcomes/statistics")  # Static route first
@app.get("/api/fabrication/outcomes/{job_id}")    # Dynamic route second
```

### 2. Settings Page - Stale Docker Build
**Location:** `/settings` route, `Settings/index.tsx`
**Error:** Blank white page with console error: "Failed to load module script: Expected a JavaScript-or-Wasm module script but the server responded with a MIME type of text/html"

**Root Cause:** Docker container was serving cached/stale build assets. The Settings page module wasn't included in the served bundle.

**Resolution:** Rebuild the UI Docker container:
```bash
docker-compose -f infra/compose/docker-compose.yml build --no-cache ui
docker-compose -f infra/compose/docker-compose.yml up -d ui
```

**Prevention:** Consider adding a version hash or build timestamp to detect stale deployments.

---

## Major Issues

### 3. Duplicate Settings.tsx Files
**Files:**
- `services/ui/src/pages/Settings.tsx` (307 lines, 5 tabs)
- `services/ui/src/pages/Settings/index.tsx` (272 lines, 8 tabs)

**Impact:** The old `Settings.tsx` is dead code but creates confusion. Only `Settings/index.tsx` is imported by the router.

**Differences:**
| Feature | Old Settings.tsx | New Settings/index.tsx |
|---------|-----------------|----------------------|
| Tabs | 5 (connections, voice, voice_modes, fabrication, ui) | 8 (+runtime, model_testing, system) |
| CSS | Inline Tailwind classes | External `Settings.css` |
| URL Sync | No | Yes (uses searchParams) |
| Voice Tab | Inline implementation | Separate `VoiceTab.tsx` component |

**Recommendation:** Delete `services/ui/src/pages/Settings.tsx`

### 4. Navigation Inconsistency
**Location:** `components/Layout/Layout.tsx:12-18` vs `pages/Menu.tsx:14-75`

The top navigation bar shows only 5 items:
- Home, Voice, Research, Fabrication, Settings

But the Menu page displays 10 cards:
- Voice, Shell, Fabrication Console, Projects, Dashboard, Media Hub, Research Hub, Intelligence, Wall Terminal, Settings

**Missing from top nav:** Shell, Projects, Dashboard, Media Hub, Intelligence, Wall Terminal

**Impact:** Users can only access some pages via the menu, not direct navigation.

**Recommendation:** Either:
1. Add a "More" dropdown to the nav bar, or
2. Group related pages (e.g., Dashboard subsumes Projects, Intelligence)

### 5. Gateway Missing Fabrication Outcome Routes
**Location:** `services/gateway/src/gateway/routes/fabrication.py`

The gateway only proxies specific fabrication endpoints (open_in_slicer, analyze_model, segmentation/*). The `/outcomes/*` endpoints are not proxied, causing direct calls to fail.

The UI calls `/api/fabrication/outcomes/statistics` which goes through the gateway, but the gateway doesn't have a route for it.

**Current proxy routes:**
- `/api/fabrication/open_in_slicer`
- `/api/fabrication/analyze_model`
- `/api/fabrication/segmentation/*`

**Missing routes:**
- `/api/fabrication/outcomes/*`
- `/api/fabrication/outcomes/statistics`
- `/api/fabrication/outcomes/{job_id}`
- `/api/fabrication/outcomes/{job_id}/review`

---

## Minor Issues

### 6. Theme Toggle Icon Logic
**Location:** `components/Layout/Layout.tsx:50`

```tsx
{theme === 'dark' ? '☀️' : '🌙'}
```

When in dark mode, it shows the sun icon (suggesting switching to light). This is technically correct UX (showing what will happen on click), but could be confusing. Some users expect to see the current mode.

**Recommendation:** Optional - consider adding a tooltip clarifying the action.

### 7. Floating KITTY Badge on All Pages
**Location:** `components/Layout/Layout.tsx:59-61`

```tsx
{!isVoicePage && (
  <KittyBadge size={80} wandering={true} wanderInterval={30000} />
)}
```

The floating "KITTY" badge wanders around every 30 seconds on all pages except Voice. This is intentional design but may be distracting during focused work.

**Recommendation:** Consider adding a user preference to disable the wandering animation.

### 8. Console Errors on Initial Load
**Observation:** Some pages show brief console errors before data loads. The Intelligence page shows the error permanently, but other pages like Dashboard show "No devices connected" gracefully.

**Recommendation:** Ensure all pages have proper loading states and empty states.

### 9. Legacy Route Redirects Present
**Location:** `router.tsx:197-273`

Multiple legacy routes exist for backwards compatibility:
- `/vision` -> `/media?tab=gallery`
- `/images` -> `/media?tab=generate`
- `/results` -> `/research?tab=results`
- `/calendar` -> `/research?tab=schedule`
- `/cameras` -> `/dashboard?tab=cameras`
- `/inventory` -> `/dashboard?tab=materials`
- `/iocontrol` -> `/settings?tab=system`

**Impact:** Low - redirects work correctly. Consider documenting deprecation timeline.

---

## Working Features Verified

1. **Voice Page:** History sidebar, conversation list, voice mode selection, status indicators
2. **Shell Page:** Model selector (GPT-OSS 120B), session info, verbosity controls
3. **Fabrication Console:** CAD prompt input, Mesh segmenter with printer selection, joint types, hollowing options
4. **Projects:** STL library browser with 18 files, artifact type filter, download links
5. **Dashboard:** Devices/Cameras/Materials tabs, voice control button
6. **Media Hub:** Generate/Gallery tabs, model selection, steps/guidance sliders
7. **Research Hub:** Template selection, strategy options, cost limits, session history
8. **Settings:** All 8 tabs accessible (Connections, Voice, Voice Modes, Fabrication, Interface, Runtime, Model Testing, System)
9. **Wall Terminal:** Remote read-only display mode

---

## Recommended Priority Order for Fixes

1. **P0 - Critical:** Fix route ordering in `fabrication/app.py` for outcomes/statistics
2. **P0 - Critical:** Add outcomes routes to gateway proxy
3. **P1 - Major:** Delete duplicate `Settings.tsx` file
4. **P2 - Minor:** Consider nav bar expansion
5. **P3 - Low:** Theme toggle tooltip
6. **P3 - Low:** KittyBadge preference option

---

## Files to Modify

| Priority | File | Action |
|----------|------|--------|
| P0 | `services/fabrication/src/fabrication/app.py` | Reorder routes (statistics before {job_id}) |
| P0 | `services/gateway/src/gateway/routes/fabrication.py` | Add outcomes/* proxy routes |
| P1 | `services/ui/src/pages/Settings.tsx` | DELETE (duplicate) |
| P2 | `services/ui/src/components/Layout/Layout.tsx` | Optional nav expansion |

---

## Test Verification Commands

```bash
# Test outcomes/statistics endpoint after fix
curl http://localhost:8300/api/fabrication/outcomes/statistics
# Expected: {"total_outcomes": 0, "success_rate": 0.0, ...}

# Test via gateway after proxy fix
curl http://localhost:8080/api/fabrication/outcomes/statistics

# Rebuild UI after changes
docker-compose -f infra/compose/docker-compose.yml build --no-cache ui
docker-compose -f infra/compose/docker-compose.yml up -d ui
```
