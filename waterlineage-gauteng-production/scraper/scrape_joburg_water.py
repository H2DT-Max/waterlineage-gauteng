#!/usr/bin/env python3
"""
Johannesburg Water & Gauteng Real Outage Scraper (scrape_joburg_water.py)
-------------------------------------------------------------------------
1. Scrapes Johannesburg Water's official Daily Water Notices & Media Statements
   plus SAnews municipal water briefings.
2. Uses Gemini 2.5 Flash (`gemini-2.5-flash`) structured JSON extraction when
   `GEMINI_API_KEY` is set in GitHub Actions Secrets / environment.
3. Includes a built-in deterministic regex/NLP fallback extractor so that even if
   `GEMINI_API_KEY` is not yet configured, any new reservoir percentages or tower
   bypass notices on johannesburgwater.co.za are parsed automatically.
"""
import datetime
import json
import os
import re
import urllib.request
import urllib.error

SAST = datetime.timezone(datetime.timedelta(hours=2))

RESERVOIR_KEYWORDS = {
    "grand_central": ["grand central"],
    "erand": ["erand"],
    "president_park": ["president park", "ivory park", "kaalfontein", "ebony park"],
    "diepsloot": ["diepsloot"],
    "rabie_ridge": ["rabie ridge"],
    "brixton": ["brixton"],
    "hursthill": ["hursthill", "parktown west", "melville"],
    "crosby": ["crosby"],
    "linden": ["linden", "robin hills"],
    "northcliff": ["northcliff"],
    "honeydew": ["honeydew", "sundowner", "northriding", "cosmo city"],
    "morningside": ["morningside", "bryanston", "illovo", "sandton"],
    "crown_gardens": ["crown gardens", "meredale"],
    "clifton_centurion": ["clifton", "centurion", "brakfontein", "the reeds"],
    "garsfontein": ["garsfontein", "waterkloof ridge"],
    "bedfordview_ridge": ["bedfordview", "edenvale", "gillooly"],
    "kempton_park": ["kempton park", "glen marais"],
    "benoni": ["benoni", "northmead"],
    "krugersdorp_ridge": ["krugersdorp", "noordheuwel", "kenmare"],
}

OFFICIAL_SOURCES = [
    "https://www.johannesburgwater.co.za/daily-water-notices/",
    "https://www.johannesburgwater.co.za/media/media-statement/",
    "https://www.sanews.gov.za/south-africa/johannesburg-water-supply-improving-says-morero",
]


def get_sast_demand_phase(sast_dt: datetime.datetime) -> dict:
    hour = sast_dt.hour
    if 21 <= hour or hour < 5:
        return {
            "phase_id": "overnight_recharge",
            "label": "Overnight Municipal Throttling & Recharge Window (21:00–05:00 SAST)",
            "demand_multiplier": 0.45,
            "typical_note": "Municipalities frequently throttle outlet valves between 21:00 and 05:00 to rebuild reservoir head."
        }
    elif 5 <= hour < 9:
        return {
            "phase_id": "morning_peak",
            "label": "Morning Peak Draw-Off & Airlock Clearing (05:00–09:00 SAST)",
            "demand_multiplier": 1.35,
            "typical_note": "High morning demand slows ridge repressurization as trapped air pockets clear from main lines."
        }
    elif 9 <= hour < 17:
        return {
            "phase_id": "daytime_equilibrium",
            "label": "Daytime Bulk Inflow & Reticulation Balance (09:00–17:00 SAST)",
            "demand_multiplier": 0.95,
            "typical_note": "Steady bulk pumping from Rand Water (Palmiet / Eikenhof / Mapleton)."
        }
    else:
        return {
            "phase_id": "evening_peak",
            "label": "Evening Peak Drawdown (17:00–21:00 SAST)",
            "demand_multiplier": 1.40,
            "typical_note": "Evening residential draw-off reduces static head on elevated ridges first."
        }


def fetch_url_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "WaterLineageGauteng/2.5 (+https://waterlineage-gauteng.pages.dev)"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


def parse_with_gemini_25_flash(scraped_text: str) -> dict:
    """
    Calls Google Gemini 2.5 Flash (`gemini-2.5-flash`) with a strict JSON response schema
    to extract reservoir levels, tower bypass states, and verified bulletins.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or not scraped_text:
        return {}

    res_ids_str = ", ".join(RESERVOIR_KEYWORDS.keys())
    prompt = (
        "You are an infrastructure telemetry extractor for Gauteng water reservoirs. "
        f"Given the official municipal water bulletin text below, extract updates for any of these reservoir IDs: {res_ids_str}. "
        "Return ONLY valid JSON mapping each mentioned reservoir_id to an object with keys: "
        "status ('critical_low'|'recovering_low'|'moderate_strain'|'normal'), "
        "capacity_pct (integer 0-100), "
        "tower_pumping_active (boolean), "
        "valve_state (short uppercase string), "
        "status_label (short uppercase summary), "
        "verified_bulletin (1-sentence factual summary).\n\nBulletin Text:\n" + scraped_text[:14000]
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }).encode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text_out = result["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_out)
    except Exception as exc:
        print(f"Gemini 2.5 Flash extraction skipped/failed: {exc}")
        return {}


def deterministic_fallback_extract(scraped_text: str) -> dict:
    """
    Zero-key regex fallback parser that scans sentence windows around reservoir names
    for percentage figures (e.g. '35%') and status keywords ('suspended', 'bypass', 'very low').
    """
    updates = {}
    sentences = re.split(r"(?<=[.!?])\s+", scraped_text)
    for res_id, kw_list in RESERVOIR_KEYWORDS.items():
        matched_sents = [s for s in sentences if any(k in s.lower() for k in kw_list)]
        if not matched_sents:
            continue
        window = " ".join(matched_sents[:2])
        pct_match = re.search(r"(\d{1,3})\s*%", window)
        lower_w = window.lower()
        patch = {}
        if pct_match:
            pct = max(5, min(100, int(pct_match.group(1))))
            patch["capacity_pct"] = pct
            if pct <= 25:
                patch["status"] = "critical_low"
            elif pct <= 40:
                patch["status"] = "recovering_low"
            elif pct <= 55:
                patch["status"] = "moderate_strain"
            else:
                patch["status"] = "normal"
        if "suspended" in lower_w or "bypass" in lower_w:
            patch["tower_pumping_active"] = False
        if patch:
            updates[res_id] = patch
    return updates


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outages_path = os.path.join(base_dir, "data", "outages.json")
    public_outages_path = os.path.join(base_dir, "public", "data", "outages.json")

    with open(outages_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    now_sast = datetime.datetime.now(SAST)
    data["generated_at_sast"] = now_sast.isoformat(timespec="seconds")
    data["sync_timestamp_ms"] = int(now_sast.timestamp() * 1000)
    data["sast_demand_curve"] = get_sast_demand_phase(now_sast)
    data["ai_engine"] = "gemini-2.5-flash"

    combined_text = []
    for url in OFFICIAL_SOURCES:
        try:
            txt = fetch_url_text(url)
            if txt:
                combined_text.append(txt[:5000])
        except Exception as exc:
            print(f"Notice fetch warning for {url}: {exc}")

    if combined_text:
        full_blob = "\n\n".join(combined_text)
        ai_updates = parse_with_gemini_25_flash(full_blob)
        if not ai_updates:
            ai_updates = deterministic_fallback_extract(full_blob)
        for res_id, patch in ai_updates.items():
            if res_id in data["reservoirs"] and isinstance(patch, dict):
                data["reservoirs"][res_id].update(patch)
                data["reservoirs"][res_id]["last_official_update"] = now_sast.strftime("%Y-%m-%d %H:%M SAST")

    for target in (outages_path, public_outages_path):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    print(f"Updated {len(data['reservoirs'])} reservoirs at {data['generated_at_sast']}")


if __name__ == "__main__":
    main()
