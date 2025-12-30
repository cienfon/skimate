import os
import json
import requests
import google.generativeai as genai
import time

# Configuration
OUTPUT_FILE = "docs/api/resort_data.json"

# IDs matching SkiResortService.swift
RESORTS = [
    {
        "id": "44444444-4444-4444-4444-444444444444", 
        "name": "Rusutsu Resort",
        "lift_url": "https://rusutsu.com/lift-and-trail-status/",
        "weather_url": "https://rusutsu.com/snow-and-weather-report/"
    }
    # Add others here as needed
]

# AI Prompts
LIFT_PROMPT = """
You are an expert data extractor.
Extract the ski lift status from the following HTML content.

Return specific lifts with their status (Open, Closed, Hold, Scheduled, Unknown).
Also extract lift type (Gondola, Chairlift, Ropeway, etc.) if mentioned or inferable.

HTML Content:
{html}

Output must be a valid JSON array of objects with these keys:
- name: String
- status: String (Open, Closed, Hold, Scheduled, Unknown)
- operation_time: String (e.g. "09:00 - 16:00")
- type: String (Gondola, Chairlift, Ropeway, T-Bar, Lift)

Example:
[{{"name": "Vista Chair", "status": "Open", "operation_time": "09:00 ~ 16:00", "type": "Chairlift"}}]

Return ONLY the raw JSON. No markdown formatting.
"""

WEATHER_PROMPT = """
You are an expert data extractor.
Extract ski resort weather conditions from the following HTML content.

The content may contain weather for multiple areas (e.g. "Base", "Summit", "West Mt", "East Mt").
Extract data for EACH distinct area found.

HTML Content:
{html}

Output must be a valid JSON array of objects with these keys:
- name: String (The location name, e.g. "West Mt Summit")
- temperature: Number (Celsius. If range, take average or lower bound. If in F, convert.)
- condition: String (Short description, e.g. "Snow", "Cloudy")
- wind_speed: Number (km/h. If m/s, multiply by 3.6)
- wind_direction: String (e.g. "NW")
- visibility: Number (km. If unable to find, estimate 10.0 for clear, 0.5 for snow)
- wind_chill: Number (Celsius. If not found, use temperature)
- summary: String (One sentence summary)

Example:
[{{"name": "Summit", "temperature": -8.5, "condition": "Snow", "wind_speed": 45, "wind_direction": "NW", "visibility": 0.2, "wind_chill": -15, "summary": "Blizzard conditions."}}]

Return ONLY the raw JSON. No markdown formatting.
"""

def setup_ai():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY env var not set")
        exit(1)
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-1.5-flash")

def fetch_html(url):
    print(f"Fetching {url}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

def clean_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    return text

def main():
    model = setup_ai()
    
    results = {
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "resorts": []
    }
    
    for resort in RESORTS:
        print(f"Processing {resort['name']}...")
        resort_data = {
            "id": resort["id"],
            "name": resort["name"],
            "lifts": [],
            "weather": []
        }
        
        # 1. Process Lifts
        if resort.get("lift_url"):
            html = fetch_html(resort["lift_url"])
            if html:
                try:
                    prompt = LIFT_PROMPT.format(html=html[:30000]) # Truncate to avoid token limits if massive
                    resp = model.generate_content(prompt)
                    if resp.text:
                        json_str = clean_json(resp.text)
                        resort_data["lifts"] = json.loads(json_str)
                        print(f"  - Extracted {len(resort_data['lifts'])} lifts")
                except Exception as e:
                    print(f"  - Lift parsing failed: {e}")
        
        # 2. Process Weather
        if resort.get("weather_url"):
            html = fetch_html(resort["weather_url"])
            if html:
                try:
                    prompt = WEATHER_PROMPT.format(html=html[:30000])
                    resp = model.generate_content(prompt)
                    if resp.text:
                        json_str = clean_json(resp.text)
                        resort_data["weather"] = json.loads(json_str)
                        print(f"  - Extracted {len(resort_data['weather'])} weather stations")
                except Exception as e:
                    print(f"  - Weather parsing failed: {e}")
                    
        results["resorts"].append(resort_data)
        time.sleep(2) # be nice to APIs
        
    # Write Output
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Success! Data written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
