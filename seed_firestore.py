"""Seed script to populate initial flight routes in Firestore."""
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-04-9c1ed5613483"

SAMPLE_FLIGHTS = [
    {
        "flight_number": "UA101",
        "origin_airport": "SFO",
        "destination": "JFK",
        "destination_city": "New York",
        "airline": "United Airlines",
        "base_price": 289,
        "duration_minutes": 325,
        "is_nonstop": True,
        "travel_type": "business",
        "departure_time": "06:00",
        "arrival_time": "14:25",
        "wifi_available": True,
        "delay_risk": "moderate",
    },
    {
        "flight_number": "B6204",
        "origin_airport": "SJC",
        "destination": "JFK",
        "destination_city": "New York",
        "airline": "JetBlue",
        "base_price": 249,
        "duration_minutes": 320,
        "is_nonstop": True,
        "travel_type": "leisure",
        "departure_time": "08:15",
        "arrival_time": "16:35",
        "wifi_available": True,
        "delay_risk": "low",
    },
    {
        "flight_number": "WN305",
        "origin_airport": "OAK",
        "destination": "JFK",
        "destination_city": "New York",
        "airline": "Southwest Airlines",
        "base_price": 215,
        "duration_minutes": 410,
        "is_nonstop": False,
        "travel_type": "leisure",
        "departure_time": "09:30",
        "arrival_time": "19:20",
        "wifi_available": True,
        "delay_risk": "low",
    },
    {
        "flight_number": "AS412",
        "origin_airport": "SFO",
        "destination": "SEA",
        "destination_city": "Seattle",
        "airline": "Alaska Airlines",
        "base_price": 145,
        "duration_minutes": 130,
        "is_nonstop": True,
        "travel_type": "business",
        "departure_time": "07:30",
        "arrival_time": "09:40",
        "wifi_available": True,
        "delay_risk": "low",
    },
    {
        "flight_number": "AS588",
        "origin_airport": "SJC",
        "destination": "SEA",
        "destination_city": "Seattle",
        "airline": "Alaska Airlines",
        "base_price": 139,
        "duration_minutes": 135,
        "is_nonstop": True,
        "travel_type": "business",
        "departure_time": "08:00",
        "arrival_time": "10:15",
        "wifi_available": True,
        "delay_risk": "low",
    },
    {
        "flight_number": "WN712",
        "origin_airport": "OAK",
        "destination": "SEA",
        "destination_city": "Seattle",
        "airline": "Southwest Airlines",
        "base_price": 109,
        "duration_minutes": 135,
        "is_nonstop": True,
        "travel_type": "leisure",
        "departure_time": "11:20",
        "arrival_time": "13:35",
        "wifi_available": True,
        "delay_risk": "low",
    },
    {
        "flight_number": "UA620",
        "origin_airport": "SFO",
        "destination": "ORD",
        "destination_city": "Chicago",
        "airline": "United Airlines",
        "base_price": 219,
        "duration_minutes": 255,
        "is_nonstop": True,
        "travel_type": "business",
        "departure_time": "08:45",
        "arrival_time": "15:00",
        "wifi_available": True,
        "delay_risk": "moderate",
    },
    {
        "flight_number": "WN890",
        "origin_airport": "OAK",
        "destination": "ORD",
        "destination_city": "Chicago",
        "airline": "Southwest Airlines",
        "base_price": 178,
        "duration_minutes": 250,
        "is_nonstop": True,
        "travel_type": "leisure",
        "departure_time": "10:05",
        "arrival_time": "16:15",
        "wifi_available": True,
        "delay_risk": "low",
    },
    {
        "flight_number": "AA1240",
        "origin_airport": "SJC",
        "destination": "ORD",
        "destination_city": "Chicago",
        "airline": "American Airlines",
        "base_price": 195,
        "duration_minutes": 250,
        "is_nonstop": True,
        "travel_type": "business",
        "departure_time": "06:30",
        "arrival_time": "12:40",
        "wifi_available": True,
        "delay_risk": "low",
    },
]


def seed():
    db = firestore.Client(project=PROJECT_ID)
    flights_ref = db.collection("flights")
    print(f"Seeding {len(SAMPLE_FLIGHTS)} flights to Firestore project '{PROJECT_ID}' in collection 'flights'...")
    for flight in SAMPLE_FLIGHTS:
        doc_id = f"{flight['origin_airport']}_{flight['destination']}_{flight['flight_number']}"
        flights_ref.document(doc_id).set(flight)
        print(f"  Added flight: {doc_id} ({flight['origin_airport']} -> {flight['destination']} on {flight['airline']})")
    print("Seeding complete!")


if __name__ == "__main__":
    seed()
