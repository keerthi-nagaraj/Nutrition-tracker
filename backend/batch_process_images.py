"""Batch-processes every image in Test-images/ through the existing nutrition_tracker pipeline into a CSV."""

import os
import csv
import json
import glob

# Reusing the nutrition_tracker package's existing functions as-is — no edits.
from nutrition_tracker.vision import call_vlm_raw, parse_vlm_analysis, flatten_food
from nutrition_tracker.providers import lookup_nutrition_impl

IMAGE_DIR = os.path.join(os.path.dirname(__file__), "Test-images")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "meal_image_analysis.csv")

IMAGE_EXTENSIONS = ("*.jpg", "*.jpeg", "*.png", "*.webp")

HEADERS = ["Image", "What it sees", "Raw VLM response", "Parsed JSON", "Error"]


def _list_images(folder: str) -> list[str]:
    paths = []
    for ext in IMAGE_EXTENSIONS:
        paths.extend(glob.glob(os.path.join(folder, ext)))
        paths.extend(glob.glob(os.path.join(folder, ext.upper())))
    return sorted(set(paths))


def _flatten_foods(analysis: dict) -> list[dict]:
    """Reuses vision.py's flatten_food to shape the analysis into rows instead of re-deriving it here."""
    return [flatten_food(food) for food in analysis.get("foods", [])]


def _what_it_sees(foods: list[dict]) -> str:
    """Human-readable summary of detected foods for column B."""
    lines = []
    for f in foods:
        conf = f["confidence"]
        avg_conf = (conf.get("food_identification", 0) + conf.get("portion_estimation", 0)) / 2
        lines.append(f"{f['name']} (~{f['estimated_weight_g']:g}g, {avg_conf:.2f} confidence)")
    return "\n".join(lines)


def _build_foods_json(foods: list[dict]) -> str:
    """Attaches fdcid (via lookup_nutrition_impl) to each food and returns the {"foods": [...]} JSON string."""
    foods_with_fdcid = []
    for f in foods:
        nutrition_info = lookup_nutrition_impl(f["fdc_search_hint"])
        foods_with_fdcid.append({
            "name": f["name"],
            "estimated_weight_g": f["estimated_weight_g"],
            "confidence": f["confidence"],
            "fdcid": str(nutrition_info["fdc_id"]) if nutrition_info["fdc_id"] else None,
        })
    return json.dumps({"foods": foods_with_fdcid}, indent=2)


def process_folder(image_dir: str, output_path: str) -> None:
    images = _list_images(image_dir)
    if not images:
        print(f"No images found in {image_dir}")
        return

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)

        for image_path in images:
            filename = os.path.basename(image_path)
            print(f"\n=== Processing: {filename} ===")

            raw_reply = ""
            sees_text = ""
            foods_json = ""
            error_text = ""

            try:
                raw_reply = call_vlm_raw(image_path)
                analysis = parse_vlm_analysis(raw_reply)
                foods = _flatten_foods(analysis)
                sees_text = _what_it_sees(foods)
                foods_json = _build_foods_json(foods)
            except Exception as e:
                print(f"[ERROR] Failed on '{filename}': {e}")
                error_text = str(e)
                if not sees_text:
                    sees_text = f"ERROR: {e}"
                if not foods_json:
                    foods_json = json.dumps({"foods": [], "error": str(e)}, indent=2)

            writer.writerow([filename, sees_text, raw_reply, foods_json, error_text])

    print(f"\nDone. Wrote {len(images)} row(s) to: {output_path}")


if __name__ == "__main__":
    process_folder(IMAGE_DIR, OUTPUT_CSV)
