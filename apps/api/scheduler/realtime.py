import json
import os
import time
import redis

_CHANNEL = "imessage_events"

def _client():
    return redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)

def publish(event: dict):
    payload = json.dumps({"ts": time.time(), **event})
    _client().publish(_CHANNEL, payload)
