# etl/adapters/ais_streamer.py
"""
Lightweight AIS streamer skeleton.
This file provides a WebSocket client hook and an on_message example.
Provider-specific details will differ (NMEA vs JSON).
"""
import logging
import json
import threading
import time
try:
    from websocket import WebSocketApp
    WEBSOCKET_AVAILABLE = True
except Exception:
    WEBSOCKET_AVAILABLE = False

logger = logging.getLogger("ais_streamer")

def on_message_example(message: str):
    """
    A generic handler to parse and print AIS messages.
    Real parsing requires provider format knowledge or pyais.
    """
    try:
        obj = None
        try:
            obj = json.loads(message)
        except Exception:
            pass
        logger.info("AIS raw: %s", obj or message[:200])
    except Exception:
        logger.exception("Failed to handle AIS message")

def start_ais_stream(ws_url: str):
    if not WEBSOCKET_AVAILABLE:
        logger.error("websocket-client not installed. install websocket-client to use AIS streamer.")
        return

    def on_message(ws, message):
        try:
            on_message_example(message)
        except Exception:
            logger.exception("message handler error")

    def on_error(ws, error):
        logger.error("AIS websocket error: %s", error)

    def on_close(ws, close_status_code, close_msg):
        logger.warning("AIS websocket closed: %s %s", close_status_code, close_msg)

    def on_open(ws):
        logger.info("AIS websocket opened")

    ws = WebSocketApp(ws_url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    # run in current thread (blocking) — caller can spawn a thread if needed
    ws.run_forever()

