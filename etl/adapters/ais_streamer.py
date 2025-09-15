# etl/adapters/ais_streamer.py
from websocket import WebSocketApp
import logging
from pyais import decode as ais_decode
import json
import time
import requests

# Example websocket: 'wss://aisstream.io/...' (check provider docs)
def on_message(ws, message):
    try:
        # message is often a JSON wrapper or raw NMEA; provider varies
        # Example: if message contains 'nmea' field
        obj = json.loads(message)
        nmea = obj.get("nmea") or obj.get("payload") or message
        parsed = ais_decode(nmea)
        # parsed is a dict-like object - map fields you care about
        data = {
            "mmsi": parsed.get("mmsi"),
            "lat": parsed.get("y"),
            "lon": parsed.get("x"),
            "sog": parsed.get("speed_over_ground"),
            "course": parsed.get("course")
        }
        # push to backend alerts or AIS ingestion endpoint
        # requests.post("http://127.0.0.1:8000/api/v1/ais", json=data)
        logging.info("AIS: %s", data)
    except Exception as e:
        logging.exception("Failed to parse AIS message: %s", e)

def start_ais_stream(ws_url):
    ws = WebSocketApp(ws_url, on_message=on_message)
    ws.run_forever()
