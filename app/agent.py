# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

try:
    from a2ui.basic_catalog.provider import BasicCatalog
    from a2ui.schema.manager import A2uiSchemaManager
    _HAS_A2UI_SDK = True
except ImportError:
    _HAS_A2UI_SDK = False

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google import genai
from google.genai import types

from app.a2ui_utils import a2ui_callback

PROJECT_ID = "qwiklabs-gcp-04-9c1ed5613483"
BUCKET_NAME = "bayfly-media-qwiklabs-gcp-04-9c1ed5613483"
COLLECTION_NAME = "flights"
AGENT_ENGINE_ID = "1462603352616468480"
SANDBOX_RESOURCE_NAME = (
    f"projects/929843512123/locations/us-east1/reasoningEngines/{AGENT_ENGINE_ID}"
    "/sandboxEnvironments/6031568946258247680"
)
MODEL = "gemini-3.6-flash"
IMAGE_MODEL = "gemini-3.1-flash-lite-image"


def _get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the explicit project ID."""
    return firestore.Client(project=PROJECT_ID)


def search_flights(
    destination: str,
    origin_airport: Optional[str] = None,
    travel_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Searches and compares flights from Bay Area airports (SJC, SFO, OAK) to a destination.

    Args:
        destination: Destination airport code (e.g., 'JFK', 'SEA', 'ORD') or city name (e.g., 'New York', 'Seattle', 'Chicago').
        origin_airport: Optional specific Bay Area airport filter ('SJC', 'SFO', or 'OAK'). If omitted, compares all available Bay Area airports.
        travel_type: Optional travel context filter ('business' or 'leisure').

    Returns:
        A list of matching flight records with details including airport, airline, price, duration, and delay risk.
    """
    db = _get_firestore_client()
    flights_ref = db.collection(COLLECTION_NAME)

    results = []
    dest_normalized = destination.strip().lower()

    for doc in flights_ref.stream():
        data = doc.to_dict()
        doc_dest_code = str(data.get("destination", "")).lower()
        doc_dest_city = str(data.get("destination_city", "")).lower()

        # Match destination by airport code or city name
        if dest_normalized not in doc_dest_code and dest_normalized not in doc_dest_city:
            continue

        if origin_airport and data.get("origin_airport", "").upper() != origin_airport.strip().upper():
            continue

        if travel_type and data.get("travel_type", "").lower() != travel_type.strip().lower():
            continue

        results.append(data)

    # Sort results by price ascending
    results.sort(key=lambda x: x.get("base_price", 9999))
    return results


def save_flight_route(
    flight_number: str,
    origin_airport: str,
    destination: str,
    destination_city: str,
    airline: str,
    base_price: int,
    duration_minutes: int,
    is_nonstop: bool = True,
    travel_type: str = "leisure",
    departure_time: str = "08:00",
    arrival_time: str = "12:00",
    wifi_available: bool = True,
    delay_risk: str = "low",
) -> Dict[str, Any]:
    """Saves or updates a flight route in Firestore.

    Args:
        flight_number: Flight code (e.g., 'UA101', 'WN305').
        origin_airport: Origin airport code ('SJC', 'SFO', or 'OAK').
        destination: Destination airport code (e.g., 'JFK', 'SEA', 'ORD').
        destination_city: Name of destination city.
        airline: Operating airline (e.g., 'United Airlines', 'Southwest Airlines').
        base_price: Estimated base ticket price in USD.
        duration_minutes: Flight duration in minutes.
        is_nonstop: Whether the flight is nonstop.
        travel_type: 'business' or 'leisure'.
        departure_time: Scheduled departure time in 24hr format (HH:MM).
        arrival_time: Scheduled arrival time in 24hr format (HH:MM).
        wifi_available: Whether in-flight Wi-Fi is available.
        delay_risk: Historical delay risk ('low', 'moderate', 'high').

    Returns:
        A dictionary with the confirmation status and saved flight record.
    """
    db = _get_firestore_client()
    doc_id = f"{origin_airport.upper()}_{destination.upper()}_{flight_number.upper()}"
    record = {
        "flight_number": flight_number.upper(),
        "origin_airport": origin_airport.upper(),
        "destination": destination.upper(),
        "destination_city": destination_city,
        "airline": airline,
        "base_price": int(base_price),
        "duration_minutes": int(duration_minutes),
        "is_nonstop": bool(is_nonstop),
        "travel_type": travel_type.lower(),
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "wifi_available": bool(wifi_available),
        "delay_risk": delay_risk.lower(),
    }
    db.collection(COLLECTION_NAME).document(doc_id).set(record)
    return {"status": "success", "id": doc_id, "flight": record}


def calculate_total_trip_cost(
    airfare: int,
    origin_airport: str,
    home_area: str,
    trip_days: int = 3,
    transport_mode: str = "parking",
) -> Dict[str, Any]:
    """Calculates true door-to-door trip cost including airfare, ground transit (parking or rideshare), and bridge tolls.

    Args:
        airfare: Ticket price in USD.
        origin_airport: Origin airport code ('SJC', 'SFO', or 'OAK').
        home_area: Traveler's home base (e.g. 'South Bay', 'San Jose', 'San Francisco', 'East Bay', 'Oakland', 'Peninsula', 'North Bay').
        trip_days: Number of days parked at the airport (defaults to 3).
        transport_mode: 'parking' (daily long-term parking + gas/tolls) or 'rideshare' (roundtrip Uber/Lyft).

    Returns:
        A breakdown with airfare, ground transport cost, tolls, and total trip cost.
    """
    airport = origin_airport.upper().strip()
    home = home_area.lower().strip()
    mode = transport_mode.lower().strip()

    # Daily long-term economy parking rates ($/day)
    daily_parking_rates = {
        "SJC": 18,
        "OAK": 18,
        "SFO": 26,
    }

    # Estimated round-trip rideshare (Uber/Lyft) costs by home area to each airport
    # Format: {home_area_keyword: {airport: roundtrip_cost}}
    rideshare_matrix = {
        "south bay": {"SJC": 40, "SFO": 110, "OAK": 120},
        "san jose": {"SJC": 35, "SFO": 115, "OAK": 125},
        "peninsula": {"SJC": 70, "SFO": 55, "OAK": 90},
        "san francisco": {"SJC": 120, "SFO": 50, "OAK": 75},
        "east bay": {"SJC": 90, "SFO": 95, "OAK": 40},
        "oakland": {"SJC": 95, "SFO": 90, "OAK": 35},
        "fremont": {"SJC": 50, "SFO": 85, "OAK": 55},
    }

    # Bridge tolls incurred based on route (roundtrip)
    bridge_tolls = {
        "south bay": {"SJC": 0, "SFO": 0, "OAK": 0},
        "san jose": {"SJC": 0, "SFO": 0, "OAK": 0},
        "peninsula": {"SJC": 0, "SFO": 0, "OAK": 7},
        "san francisco": {"SJC": 0, "SFO": 0, "OAK": 7},
        "east bay": {"SJC": 0, "SFO": 7, "OAK": 0},
        "oakland": {"SJC": 0, "SFO": 7, "OAK": 0},
        "fremont": {"SJC": 0, "SFO": 7, "OAK": 0},
    }

    # Match home area
    matched_area = "south bay"
    for key in rideshare_matrix:
        if key in home:
            matched_area = key
            break

    toll = bridge_tolls.get(matched_area, {}).get(airport, 0)

    if mode == "rideshare":
        ground_cost = rideshare_matrix.get(matched_area, {}).get(airport, 80)
        breakdown_note = f"Round-trip rideshare ({matched_area.title()} -> {airport})"
    else:
        # Default: parking
        daily_rate = daily_parking_rates.get(airport, 22)
        ground_cost = daily_rate * max(1, trip_days)
        breakdown_note = f"{trip_days} days parking @ ${daily_rate}/day at {airport}"

    total_cost = airfare + ground_cost + toll

    return {
        "origin_airport": airport,
        "home_area": matched_area.title(),
        "airfare": airfare,
        "transport_mode": mode,
        "ground_cost": ground_cost,
        "bridge_toll": toll,
        "total_cost": total_cost,
        "details": f"{breakdown_note} + ${toll} toll (Total Ground: ${ground_cost + toll})",
    }


def get_airport_weather(airport_code: str) -> Dict[str, Any]:
    """Fetches real-time weather and flight operational conditions for a Bay Area airport using the free Open-Meteo API.

    Args:
        airport_code: The 3-letter IATA airport code ('SFO', 'SJC', or 'OAK').

    Returns:
        A dictionary with live weather data (temperature, wind speed, conditions, and fog/delay risk).
    """
    import urllib.request
    import json

    # Precise runway coordinates for Bay Area airports
    airport_coords = {
        "SFO": {"name": "San Francisco International", "lat": 37.6213, "lon": -122.3790},
        "SJC": {"name": "San Jose Mineta International", "lat": 37.3639, "lon": -121.9289},
        "OAK": {"name": "Oakland International", "lat": 37.7213, "lon": -122.2207},
    }

    code = airport_code.upper().strip()
    if code not in airport_coords:
        return {"error": f"Unknown airport '{airport_code}'. Supported airports: SFO, SJC, OAK"}

    meta = airport_coords[code]
    api_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={meta['lat']}&longitude={meta['lon']}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
    )

    req = urllib.request.Request(api_url, headers={"User-Agent": "BayFlyAgent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            current = data.get("current", {})

            temp = current.get("temperature_2m")
            humidity = current.get("relative_humidity_2m", 0)
            wind = current.get("wind_speed_10m", 0)
            weather_code = current.get("weather_code", 0)

            # WMO Weather interpretation codes
            # 0: Clear, 1-3: Partly Cloudy / Overcast, 45/48: Fog, 51-67: Rain/Drizzle
            weather_desc = "Clear"
            delay_risk = "Low"
            if weather_code in (45, 48):
                weather_desc = "Fog / Low Visibility"
                delay_risk = "High" if code == "SFO" else "Moderate"
            elif weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
                weather_desc = "Rain / Showers"
                delay_risk = "Moderate"
            elif weather_code in (1, 2, 3):
                weather_desc = "Cloudy / Overcast"
                if code == "SFO" and humidity > 85:
                    delay_risk = "Moderate (Marine Layer / Stratus)"

            if wind > 25:
                delay_risk = "High (High Crosswinds)"

            return {
                "airport": code,
                "airport_name": meta["name"],
                "temperature_f": temp,
                "relative_humidity_pct": humidity,
                "wind_speed_mph": wind,
                "condition": weather_desc,
                "delay_risk_level": delay_risk,
                "source": "Open-Meteo Free API (https://open-meteo.com/)",
            }
    except Exception as e:
        return {"error": f"Failed to fetch weather data: {str(e)}", "airport": code}


def search_google_flights(
    destination: str,
    outbound_date: Optional[str] = None,
    return_date: Optional[str] = None,
    origin_airport: Optional[str] = None,
    travel_class: int = 1,
) -> Dict[str, Any]:
    """Queries live Google Flights via SerpApi to compare flights from SJC, SFO, and OAK.

    Requires SERPAPI_API_KEY environment variable. If the key is not set, falls back
    gracefully and instructs the user to provide an API key or use search_flights.

    Args:
        destination: 3-letter IATA destination code (e.g., 'JFK', 'SEA', 'ORD', 'LAX').
        outbound_date: Departure date in YYYY-MM-DD format. Defaults to 14 days from today.
        return_date: Optional return date in YYYY-MM-DD format (for roundtrip).
        origin_airport: Specific origin airport ('SJC', 'SFO', or 'OAK'). If omitted, queries all three simultaneously.
        travel_class: 1 for Economy, 2 for Premium Economy, 3 for Business, 4 for First.

    Returns:
        A dictionary with live flight search results or fallback guidance.
    """
    import os
    import urllib.request
    import urllib.parse
    import json
    from datetime import datetime, timedelta

    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return {
            "status": "missing_api_key",
            "message": (
                "SERPAPI_API_KEY environment variable is not configured. "
                "To enable live Google Flights search, set SERPAPI_API_KEY in your .env file "
                "(get a free key at https://serpapi.com). Falling back to search_flights."
            ),
        }

    # Default date if not specified: 14 days from today
    if not outbound_date:
        outbound_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    # Multi-airport departure query if no specific airport provided
    departure_ids = origin_airport.upper().strip() if origin_airport else "SJC,SFO,OAK"
    arrival_id = destination.upper().strip()

    params = {
        "engine": "google_flights",
        "departure_id": departure_ids,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "travel_class": str(travel_class),
        "currency": "USD",
        "hl": "en",
        "api_key": api_key,
    }
    if return_date:
        params["return_date"] = return_date
        params["type"] = "1"  # Round trip
    else:
        params["type"] = "2"  # One way

    query_string = urllib.parse.urlencode(params)
    request_url = f"https://serpapi.com/search?{query_string}"

    try:
        req = urllib.request.Request(request_url, headers={"User-Agent": "BayFlyAgent/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))

        best_flights = data.get("best_flights", [])
        other_flights = data.get("other_flights", [])
        all_options = (best_flights + other_flights)[:6]

        formatted_flights = []
        for item in all_options:
            flights_list = item.get("flights", [])
            if not flights_list:
                continue
            first_leg = flights_list[0]
            dep_airport = first_leg.get("departure_airport", {}).get("id")
            arr_airport = flights_list[-1].get("arrival_airport", {}).get("id")
            airline = first_leg.get("airline")
            duration = item.get("total_duration")
            price = item.get("price")
            layovers = len(flights_list) - 1

            formatted_flights.append({
                "origin_airport": dep_airport,
                "destination": arr_airport,
                "airline": airline,
                "price_usd": price,
                "total_duration_minutes": duration,
                "is_nonstop": layovers == 0,
                "layover_count": layovers,
                "departure_time": first_leg.get("departure_airport", {}).get("time"),
                "arrival_time": flights_list[-1].get("arrival_airport", {}).get("time"),
                "booking_link": (
                    f"https://www.google.com/travel/flights?q=Flights%20to%20{arr_airport}%20from%20{dep_airport}"
                    f"%20on%20{outbound_date}" + (f"%20through%20{return_date}" if return_date else "")
                ),
            })

        overall_search_url = data.get("search_metadata", {}).get("google_flights_url") or (
            f"https://www.google.com/travel/flights?q=Flights%20to%20{arrival_id}%20from%20{departure_ids}"
            f"%20on%20{outbound_date}" + (f"%20through%20{return_date}" if return_date else "")
        )

        return {
            "status": "success",
            "source": "Google Flights (via SerpApi)",
            "outbound_date": outbound_date,
            "return_date": return_date,
            "destination": arrival_id,
            "google_flights_booking_url": overall_search_url,
            "flights_found": len(formatted_flights),
            "flights": formatted_flights,
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed to fetch Google Flights: {str(e)}"}


def generate_destination_image(
    destination: str,
    tool_context: ToolContext,
    theme: str = "travel postcard",
) -> Dict[str, Any]:
    """Generates an image for a travel destination using gemini-3.1-flash-lite-image in the global region.

    Saves the image as an ADK session artifact (visible in Playground's Artifacts panel)
    and uploads the image bytes to public Google Cloud Storage, returning the public HTTPS URL.

    Args:
        destination: Destination city or airport name (e.g. 'Seattle', 'New York', 'Chicago', 'Los Angeles').
        tool_context: ADK ToolContext injected automatically by the runtime.
        theme: Visual theme or style (e.g., 'scenic landscape', 'vibrant city skyline', 'travel postcard').

    Returns:
        A dictionary with the public image URL, artifact filename, and destination.
    """
    import re
    import uuid

    clean_dest = re.sub(r"[^a-zA-Z0-9_-]", "_", destination.strip().lower())
    timestamp_id = uuid.uuid4().hex[:8]
    filename = f"{clean_dest}_{timestamp_id}.jpg"

    prompt = (
        f"A beautiful, high quality {theme} showcasing {destination}. "
        "Scenic view, vibrant colors, cinematic lighting, professional travel photography style."
    )

    # 1. Generate image using gemini-3.1-flash-lite-image in global region
    ai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    response = ai_client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
    )

    image_bytes = None
    mime_type = "image/jpeg"
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type or "image/jpeg"
                break
        if image_bytes:
            break

    if not image_bytes:
        return {"status": "error", "error": f"No image generated for {destination}"}

    # 2. Save artifact using tool_context.save_artifact for Playground Artifacts panel
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    tool_context.save_artifact(
        filename=filename,
        artifact=artifact_part,
        custom_metadata={"destination": destination, "theme": theme},
    )

    # 3. Upload bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "destination": destination,
        "artifact_filename": filename,
        "public_image_url": public_url,
        "details": f"Generated image for {destination} saved to session artifacts and uploaded to public storage.",
    }


def get_current_time(query: str = "San Francisco") -> str:
    """Returns the current local time for the Bay Area (Pacific Time).

    Args:
        query: Location query (defaults to 'San Francisco' / Bay Area).

    Returns:
        The current date and time string in Pacific Time.
    """
    tz = ZoneInfo("America/Los_Angeles")
    now = datetime.datetime.now(tz)
    return f"The current Bay Area time is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


async def generate_memories_callback(callback_context: CallbackContext):
    """Saves session facts and preferences to Vertex AI Memory Bank after each agent turn."""
    await callback_context.add_session_to_memory()
    return None


sandbox_executor = AgentEngineSandboxCodeExecutor(
    sandbox_resource_name=SANDBOX_RESOURCE_NAME
)

if _HAS_A2UI_SDK:
    a2ui_schema_manager = A2uiSchemaManager(
        version="0.8",
        catalogs=[BasicCatalog.get_config("0.8")],
    )

    a2ui_instruction = a2ui_schema_manager.generate_system_prompt(
        role_description=(
            "You are BayFly, an expert Bay Area flight comparison concierge. "
            "You remember the user's stated travel preferences (e.g. home neighborhood/ZIP, preferred airline loyalty, "
            "travel mode preference like business vs. leisure, and baggage needs) from previous conversations and use them "
            "to personalize your recommendations without needing to ask repeatedly. "
            "Your mission is to help travelers compare flight options side-by-side across "
            "the three major Bay Area airports: San Jose (SJC), San Francisco (SFO), and Oakland (OAK). "
            "Treat all three airports as equal contenders by default. "
            "Tailor your recommendations based on whether the trip is for business (prioritize non-stop, early schedules, Wi-Fi, and low delay risk) "
            "or leisure (prioritize total price, value, and baggage flexibility). "
            "For flight data: use search_google_flights to query live Google Flights if available; otherwise use search_flights to query Firestore. "
            "When presenting flight options, always include the flight booking link or the Google Flights booking URL so travelers can directly book or view the flights on Google Flights. "
            "Use save_flight_route to save new routes, "
            "calculate_total_trip_cost to provide the true door-to-door trip cost (airfare + parking or rideshare + tolls), "
            "get_airport_weather to check real-time weather, wind, and delay risks (especially SFO fog vs SJC/OAK conditions), "
            "and generate_destination_image to generate a destination postcard/preview image and present its public URL to the traveler. "
            "You also have a secure Python code execution sandbox to perform complex calculations, simulations, or mathematical optimizations."
        ),
        workflow_description="Analyze the flight comparison request and return structured UI when appropriate.",
        ui_description=(
            "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
            "Never nest a Card inside a Card. "
            "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
            "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
            "nothing in adk web). "
            "You may include one Image component, but only when you have a public https "
            "URL for the image (for example the URL an image tool returns after uploading "
            "to a public bucket). Set the Image url to that exact https link, for example "
            "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
            "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
            "not have a public URL, add a short Text line noting the image instead. "
            "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
            "headings and emphasis. "
            "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
            "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
        ),
        include_schema=True,
        include_examples=True,
    )
else:
    from app.a2ui_prompt import A2UI_INSTRUCTION

    a2ui_instruction = A2UI_INSTRUCTION

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=sandbox_executor,
    tools=[
        PreloadMemoryTool(),
        search_google_flights,
        search_flights,
        save_flight_route,
        calculate_total_trip_cost,
        get_airport_weather,
        generate_destination_image,
        get_current_time,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
