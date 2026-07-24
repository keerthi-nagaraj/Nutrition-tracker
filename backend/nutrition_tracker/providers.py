"""Stage 2: multi-provider nutrition lookup — every enabled provider is queried, then per-nutrient results are merged."""

import csv
import difflib
from concurrent.futures import ThreadPoolExecutor

import requests

from .config import (
    USDA_API_KEY, USDA_SEARCH_URL, USDA_DETAIL_URL, USDA_DATA_TYPES,
    OFF_SEARCH_URL, OFF_HEADERS,
    NUTRITIONIX_APP_ID, NUTRITIONIX_APP_KEY, NUTRITIONIX_NATURAL_URL,
    INDB_CSV_PATH,
    NUTRIENTS, MATCH_SCORE_WEIGHT, COMPLETENESS_WEIGHT,
    FDC_MATCH_THRESHOLD,
)
from .normalization import normalize_food_name


def _match_score(food_name: str, matched_text: str | None) -> float:
    """Text similarity between the queried food name and a candidate's description."""
    return difflib.SequenceMatcher(None, food_name.lower(), (matched_text or "").lower()).ratio()


def _completeness(per_100g: dict | None) -> float:
    """Fraction of nutrient fields a provider actually populated (nonzero)."""
    if not per_100g:
        return 0.0
    return sum(1 for v in per_100g.values() if v) / len(per_100g)


def _provider_result(
    provider: str,
    source_id: str | None,
    matched_description: str | None,
    per_100g: dict | None,
    found: bool,
    food_name: str = "",
) -> dict:
    """Normalized shape every provider function returns, so results can be compared and merged."""
    return {
        "provider": provider,
        "source_id": source_id,
        "matched_description": matched_description,
        "per_100g": per_100g,
        "found": found,
        "match_score": _match_score(food_name, matched_description) if found else 0.0,
        "completeness": _completeness(per_100g) if found else 0.0,
    }


def _simplify_query(food_name: str) -> str:
    """Strips filler qualifiers USDA's search chokes on, e.g. 'masala chai with milk and sugar' -> 'masala chai'."""
    fillers = (" with ", " and ", " in ", " on ", " topped ", " served ")
    lowered = food_name.lower()
    cut_at = len(food_name)
    for f in fillers:
        idx = lowered.find(f)
        if idx != -1:
            cut_at = min(cut_at, idx)
    simplified = food_name[:cut_at].strip()
    return simplified if simplified else food_name


def _usda_search(query: str) -> requests.Response | None:
    """Runs one USDA search call; returns None on failure (network error or non-2xx status), never raises."""
    try:
        resp = requests.get(
            USDA_SEARCH_URL,
            params={
                "api_key": USDA_API_KEY,
                "query": query,
                "pageSize": 1,
                "dataType": USDA_DATA_TYPES,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"[USDA] WARNING: search failed for '{query}' — {e}")
        return None


def _usda_provider(food_name: str) -> dict:
    """Normalizes, searches USDA, takes its top result, retrying with a simplified query on failure or a weak match."""
    if not USDA_API_KEY:
        return _provider_result("usda", None, None, None, False, food_name)

    query = normalize_food_name(food_name)
    search = _usda_search(query)

    if search is None:
        simplified = _simplify_query(query)
        if simplified != query:
            print(f"[USDA] Retrying with simplified query: '{simplified}'")
            search = _usda_search(simplified)
            if search is not None:
                # Keep `query` in sync with whatever search actually
                # succeeded, so the score check below scores the right text
                # and the FDC_MATCH_THRESHOLD fallback further down doesn't
                # re-simplify (and re-search) the same query a second time.
                query = simplified
        if search is None:
            return _provider_result("usda", None, None, None, False, food_name)

    foods = search.json().get("foods", [])
    if not foods:
        print(f"[USDA] WARNING: no match found for '{food_name}' — nutrition unavailable")
        return _provider_result("usda", None, None, None, False, food_name)

    match = foods[0]
    score = _match_score(query, match.get("description"))
    print(f"[USDA] '{food_name}' -> FDC ID: {match['fdcId']} | {match.get('description')} (score={score:.2f})")

    if score < FDC_MATCH_THRESHOLD:
        simplified = _simplify_query(query)
        if simplified != query:
            fallback_search = _usda_search(simplified)
            fallback_foods = (fallback_search.json().get("foods", []) if fallback_search else [])
            if fallback_foods:
                fallback_match = fallback_foods[0]
                fallback_score = _match_score(simplified, fallback_match.get("description"))
                if fallback_score > score:
                    print(f"[USDA] Falling back to broader query '{simplified}' (score {score:.2f} -> {fallback_score:.2f})")
                    match, score = fallback_match, fallback_score

    fdc_id, description = match["fdcId"], match.get("description")

    try:
        detail_resp = requests.get(
            USDA_DETAIL_URL.format(fdc_id=fdc_id),
            params={"api_key": USDA_API_KEY},
            timeout=15,
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
    except requests.RequestException as e:
        print(f"[USDA] WARNING: detail lookup failed for FDC ID {fdc_id} — {e}")
        return _provider_result("usda", None, None, None, False, food_name)

    per_100g = {v: 0.0 for v in NUTRIENTS.values()}
    for n in detail.get("foodNutrients", []):
        name = n.get("nutrient", {}).get("name") or n.get("nutrientName")
        if name in NUTRIENTS:
            per_100g[NUTRIENTS[name]] = float(n.get("amount", n.get("value", 0)) or 0)

    result = _provider_result("usda", str(fdc_id), description, per_100g, True, food_name)
    result["fdc_match_confidence"] = score
    return result


def _openfoodfacts_provider(food_name: str) -> dict:
    """Searches Open Food Facts and takes its top result; no API key required."""
    try:
        resp = requests.get(
            OFF_SEARCH_URL,
            params={
                "search_terms": food_name,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 1,
            },
            headers=OFF_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        products = resp.json().get("products", [])
    except requests.RequestException as e:
        print(f"[OpenFoodFacts] WARNING: search failed for '{food_name}' — {e}")
        return _provider_result("openfoodfacts", None, None, None, False, food_name)

    if not products:
        print(f"[OpenFoodFacts] WARNING: no match found for '{food_name}'")
        return _provider_result("openfoodfacts", None, None, None, False, food_name)

    best = products[0]
    nutriments = best.get("nutriments", {})

    per_100g = {
        "calories": float(nutriments.get("energy-kcal_100g") or 0),
        "protein_g": float(nutriments.get("proteins_100g") or 0),
        "carbohydrate_g": float(nutriments.get("carbohydrates_100g") or 0),
        "fat_g": float(nutriments.get("fat_100g") or 0),
        "fiber_g": float(nutriments.get("fiber_100g") or 0),
        "sugar_g": float(nutriments.get("sugars_100g") or 0),
    }
    # OFF reports sodium in grams per 100g; fall back to salt (NaCl) if
    # sodium itself isn't populated — salt-to-sodium is a standard /2.5.
    sodium_g = nutriments.get("sodium_100g")
    if sodium_g is None:
        salt_g = nutriments.get("salt_100g")
        sodium_g = (salt_g / 2.5) if salt_g else 0
    per_100g["sodium_mg"] = float(sodium_g or 0) * 1000

    description = best.get("product_name") or best.get("generic_name")
    source_id = best.get("code")
    print(f"[OpenFoodFacts] '{food_name}' -> code: {source_id} | {description}")

    return _provider_result("openfoodfacts", source_id, description, per_100g, True, food_name)


def _nutritionix_provider(food_name: str) -> dict:
    """Optional provider: returns 'not found' without a network call unless both Nutritionix env vars are set."""
    if not (NUTRITIONIX_APP_ID and NUTRITIONIX_APP_KEY):
        return _provider_result("nutritionix", None, None, None, False, food_name)

    try:
        resp = requests.post(
            NUTRITIONIX_NATURAL_URL,
            headers={
                "x-app-id": NUTRITIONIX_APP_ID,
                "x-app-key": NUTRITIONIX_APP_KEY,
                "Content-Type": "application/json",
            },
            json={"query": food_name},
            timeout=15,
        )
        resp.raise_for_status()
        foods = resp.json().get("foods", [])
    except requests.RequestException as e:
        print(f"[Nutritionix] WARNING: lookup failed for '{food_name}' — {e}")
        return _provider_result("nutritionix", None, None, None, False, food_name)

    if not foods:
        print(f"[Nutritionix] WARNING: no match found for '{food_name}'")
        return _provider_result("nutritionix", None, None, None, False, food_name)

    best = max(foods, key=lambda f: _match_score(food_name, f.get("food_name")))
    # Nutritionix reports nutrients per serving, not per 100g — rescale.
    serving_grams = float(best.get("serving_weight_grams") or 100) or 100.0
    scale = 100.0 / serving_grams

    per_100g = {
        "calories": float(best.get("nf_calories") or 0) * scale,
        "protein_g": float(best.get("nf_protein") or 0) * scale,
        "carbohydrate_g": float(best.get("nf_total_carbohydrate") or 0) * scale,
        "fat_g": float(best.get("nf_total_fat") or 0) * scale,
        "fiber_g": float(best.get("nf_dietary_fiber") or 0) * scale,
        "sugar_g": float(best.get("nf_sugars") or 0) * scale,
        "sodium_mg": float(best.get("nf_sodium") or 0) * scale,
    }
    description = best.get("food_name")
    source_id = best.get("nix_item_id") or description
    print(f"[Nutritionix] '{food_name}' -> {description} ({serving_grams:g}g serving)")

    return _provider_result("nutritionix", source_id, description, per_100g, True, food_name)


def _load_indb_rows() -> list[dict]:
    """Loads the local INDB CSV once at import time; missing/unreadable file degrades to an empty table."""
    try:
        with open(INDB_CSV_PATH, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError as e:
        print(f"[INDB] WARNING: could not load {INDB_CSV_PATH} — {e}")
        return []


_INDB_ROWS = _load_indb_rows()


def _indb_provider(food_name: str) -> dict:
    """Fuzzy-matches against the local Indian Nutrient Databank CSV; no network call, no unit conversion needed."""
    if not _INDB_ROWS:
        return _provider_result("indb", None, None, None, False, food_name)

    best, best_score = max(
        ((row, _match_score(food_name, row.get("food_name"))) for row in _INDB_ROWS),
        key=lambda pair: pair[1],
    )
    if best_score == 0:
        return _provider_result("indb", None, None, None, False, food_name)

    def num(key: str) -> float:
        try:
            return float(best.get(key) or 0)
        except ValueError:
            return 0.0

    per_100g = {
        "calories": num("energy_kcal"),
        "protein_g": num("protein_g"),
        "carbohydrate_g": num("carb_g"),
        "fat_g": num("fat_g"),
        "fiber_g": num("fibre_g"),
        "sugar_g": num("freesugar_g"),
        "sodium_mg": num("sodium_mg"),
    }
    description = best.get("food_name")
    source_id = best.get("food_code")
    print(f"[INDB] '{food_name}' -> {source_id} | {description}")

    return _provider_result("indb", source_id, description, per_100g, True, food_name)


# Every enabled provider is queried for every item; see module docstring
# above for how the merge works and how to add more.
PROVIDERS: list[tuple[str, callable]] = [
    ("usda", _usda_provider),
    ("openfoodfacts", _openfoodfacts_provider),
    ("nutritionix", _nutritionix_provider),
    ("indb", _indb_provider),
]


def _select_best_provider(results: list[dict]) -> dict | None:
    """Picks the closest-matching provider (text similarity, tie-broken by completeness) to label the merged result."""
    found = [r for r in results if r["found"]]
    if not found:
        return None
    return max(found, key=lambda r: r["match_score"] * MATCH_SCORE_WEIGHT + r["completeness"] * COMPLETENESS_WEIGHT)


def _merge_provider_results(results: list[dict]) -> dict:
    """Merges every matching provider's per-100g nutrients, per-nutrient, as a match-score-weighted average."""
    found = [r for r in results if r["found"]]
    if not found:
        return {
            "per_100g": None, "matched_description": None, "found": False,
            "primary_source": None, "primary_source_id": None, "sources": [],
        }

    per_100g = {}
    sources = set()
    for key in NUTRIENTS.values():
        weighted_sum = weight_total = 0.0
        for r in found:
            value = (r["per_100g"] or {}).get(key, 0)
            if value:
                weight = max(r["match_score"], 0.05)
                weighted_sum += value * weight
                weight_total += weight
                sources.add(r["provider"])
        per_100g[key] = round(weighted_sum / weight_total, 2) if weight_total else 0.0

    primary = _select_best_provider(found)

    return {
        "per_100g": per_100g,
        "matched_description": primary["matched_description"],
        "found": True,
        "primary_source": primary["provider"],
        "primary_source_id": primary["source_id"],
        "sources": sorted(sources),
    }


def _merge_and_label(food_name: str, results: list[dict]) -> dict:
    """Turns one food's per-provider results into the merged+labeled shape both lookup functions return."""
    merged = _merge_provider_results(results)
    usda_hit = next((r for r in results if r["provider"] == "usda" and r["found"]), None)

    # match_confidence is specifically the USDA top-result's plain text-match
    # score (see _usda_provider) for the returned fdc_id — the two describe
    # the same match, so match_confidence is 0 whenever fdc_id is null rather
    # than borrowing some other provider's unrelated text-match score.
    match_confidence = usda_hit["fdc_match_confidence"] if usda_hit else 0.0

    return {
        "item": food_name,
        "fdc_id": usda_hit["source_id"] if usda_hit else None,
        "match_confidence": round(match_confidence, 2),
        "matched_description": merged["matched_description"],
        "per_100g": merged["per_100g"],
        "found": merged["found"],
        "source": merged["primary_source"],
        "source_id": merged["primary_source_id"],
        "sources": merged["sources"],
        "providers": results,
    }


def lookup_nutrition_impl(food_name: str) -> dict:
    """Looks up ONE food across every enabled provider; implemented as the single-food case of lookup_nutrition_batch."""
    return lookup_nutrition_batch([food_name])[0]


def lookup_nutrition_batch(food_names: list[str]) -> list[dict]:
    """Looks up a whole meal's foods at once, one shared thread pool for every food x provider call, order preserved."""
    if not food_names:
        return []

    with ThreadPoolExecutor(max_workers=len(food_names) * len(PROVIDERS)) as pool:
        futures = {
            pool.submit(fn, food_name): (i, name)
            for i, food_name in enumerate(food_names)
            for name, fn in PROVIDERS
        }
        results_by_index: list[list[dict]] = [[] for _ in food_names]
        for fut in futures:
            i, provider_name = futures[fut]
            try:
                results_by_index[i].append(fut.result())
            except Exception as e:
                print(f"[{provider_name}] ERROR: provider raised unexpectedly — {e}")
                results_by_index[i].append(
                    _provider_result(provider_name, None, None, None, False, food_names[i])
                )

    return [_merge_and_label(food_names[i], results_by_index[i]) for i in range(len(food_names))]
