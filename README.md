# Nutrition Tracker

Take a photo of your food → AI detects what's on the plate and estimates portions → nutrition
is looked up and calculated → the meal is logged.

The backend is an **MCP server** (a set of callable tools). The Svelte frontend is one client of
it, but any MCP-compatible client (voice agent, chat app) can drive the same flow.

## Architecture

```
┌─────────────┐        MCP tool calls (JSON over HTTP)        ┌──────────────────┐
│  Svelte      │ ────────────────────────────────────────────▶ │  FastMCP server   │
│  frontend    │ ◀──────────────────────────────────────────── │  (backend/)       │
└─────────────┘                                                └──────────────────┘
                                                                         │
                                                  ┌──────────────────────┼──────────────────────┐
                                                  ▼                      ▼                      ▼
                                          Gemini (vision)      Nutrition providers        SQLite store
                                          detect foods +        USDA / OpenFoodFacts /    analyses, meals
                                          portions from photo   Nutritionix / local INDB
```

## How it works

```
photo ──▶ analyze_meal ──▶ estimate_meal_nutrition ──▶ log_meal
              │
              └─ ambiguous item? ask the user, then resolve_meal_clarification
```

If you want to track what was actually *eaten* (not just served), there's a second photo step:

```
before-photo ──▶ analyze_meal ──▶ after-photo ──▶ analyze_meal_remaining ──▶ estimate_meal_nutrition ──▶ log_meal
```

(`analyze_meal_remaining` figures out consumed = before − remaining, using Gemini only on the
after-photo.)

## The tools

| # | Tool | Does |
|---|---|---|
| 1 | `analyze_meal` | Photo → detected foods + estimated weights. Asks the user to confirm before moving on. |
| 2 | `analyze_meal_remaining` | After-photo + the earlier analysis → how much was actually eaten. |
| 3 | `resolve_meal_clarification` | Applies the user's answer to an ambiguous item (e.g. "whole milk or skim?"). |
| 4 | `estimate_meal_nutrition` | Foods + weights → calories & nutrients. |
| 5 | `log_meal` | Saves the meal. |

All defined in `backend/controllers/`.

## Where nutrition numbers come from

`backend/nutrition_tracker/providers.py` looks each food up across a few sources at once, then
blends the results (weighted by how good each match was):

- **USDA FoodData Central** — needs `USDA_API_KEY`
- **Open Food Facts** — free, no key needed
- **Nutritionix** — needs `NUTRITIONIX_APP_ID` + `NUTRITIONIX_APP_KEY`
- **INDB** (Indian foods) — local CSV, no network call

Any source without its API key set is just skipped.

## Setup

`backend/.env`:
```
GEMINI_API_KEY=...        # required — powers food detection
USDA_API_KEY=...          # optional
NUTRITIONIX_APP_ID=...    # optional
NUTRITIONIX_APP_KEY=...   # optional
```

## Run

```bash
cd backend && python server.py     # MCP server → http://0.0.0.0:8000/mcp
cd frontend && npm run dev          # web UI
```

## Layout

```
backend/
  server.py                 entrypoint
  controllers/               the 5 tools above
  nutrition_tracker/         Gemini calls, nutrition providers, database
  views/                     shared input/response helpers

frontend/
  src/lib/mcp/               talks to the backend
  src/lib/stores/            drives the UI through the flow
  src/lib/components/        one component per step (photo upload, confirm, results, ...)
```
