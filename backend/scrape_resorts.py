import os
import json
import time
import google.generativeai as genai
from playwright.sync_api import sync_playwright

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
    return genai.GenerativeModel("gemini-flash-latest") # Flash is more reliable for free tier automation

def fetch_html_with_browser(url):
    print(f"Fetching {url } with Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # Set a real user agent
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Wait for meaningful content (e.g. a table or specific class)
            # This is a generic wait, we can improve if we know the selector
            time.sleep(5) 
            
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        print(f"Playwright fetch failed for {url}: {e}")
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
            html = fetch_html_with_browser(resort["lift_url"])
            if html:
                try:
                    # Truncate to avoid token limits, but 100k is usually fine for Gemini 1.5 Pro
                    prompt = LIFT_PROMPT.format(html=html[:100000]) 
                    resp = model.generate_content(prompt)
                    if resp.text:
                        json_str = clean_json(resp.text)
                        try:
                            resort_data["lifts"] = json.loads(json_str)
                            print(f"  - Extracted {len(resort_data['lifts'])} lifts")
                        except json.JSONDecodeError:
                            print(f"  - Failed to decode Lift JSON: {json_str[:100]}...")
                except Exception as e:
                    print(f"  - Lift parsing failed: {e}")
        
        # 2. Process Weather
        if resort.get("weather_url"):
            # Weather page might be simpler, but use browser to be safe
            html = fetch_html_with_browser(resort["weather_url"])
            if html:
                try:
                    prompt = WEATHER_PROMPT.format(html=html[:100000])
                    resp = model.generate_content(prompt)
                    if resp.text:
                        json_str = clean_json(resp.text)
                        try:
                            resort_data["weather"] = json.loads(json_str)
                            print(f"  - Extracted {len(resort_data['weather'])} weather stations")
                        except json.JSONDecodeError:
                            print(f"  - Failed to decode Weather JSON: {json_str[:100]}...")
                except Exception as e:
                     print(f"  - Weather parsing failed: {e}")
                    
        results["resorts"].append(resort_data)
        
    # Write Output
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Success! Data written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
