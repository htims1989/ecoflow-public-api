"""One-off MQTT capture: collect every telemetry field a device pushes.

Usage:
    ACCESS=... SECRET=... SN=... HOST=api-e.ecoflow.com SECONDS=150 \
        python3 scripts/mqtt_capture.py

Not shipped to users; a diagnostic aid for mapping new fields.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import ssl
import time
import urllib.request

import paho.mqtt.client as mqtt

ACCESS = os.environ["ACCESS"]
SECRET = os.environ["SECRET"]
SN = os.environ["SN"]
HOST = os.environ.get("HOST", "api-e.ecoflow.com")
RUN_SECONDS = int(os.environ.get("SECONDS", "150"))


def _signed_get(endpoint: str, params: dict[str, str] | None = None) -> dict:
    params = params or {}
    ps = "&".join(f"{k}={params[k]}" for k in sorted(params))
    nonce = str(random.randint(10000, 1000000))
    ts = str(int(time.time() * 1000))
    base = f"accessKey={ACCESS}&nonce={nonce}&timestamp={ts}"
    target = f"{ps}&{base}" if ps else base
    sign = hmac.new(SECRET.encode(), target.encode(), hashlib.sha256).hexdigest()
    url = f"https://{HOST}/iot-open/sign{endpoint}"
    if ps:
        url = f"{url}?{ps}"
    req = urllib.request.Request(
        url,
        headers={
            "accessKey": ACCESS,
            "nonce": nonce,
            "timestamp": ts,
            "sign": sign,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> None:
    cert = _signed_get("/certification")["data"]
    account = cert["certificateAccount"]
    password = cert["certificatePassword"]
    broker = cert["url"]
    port = int(cert["port"])
    topic = f"/open/{account}/{SN}/quota"

    seen: dict[str, object] = {}
    msg_count = 0

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"connected rc={reason_code}; subscribing {topic}")
        client.subscribe(topic)

    def on_message(client, userdata, message):
        nonlocal msg_count
        msg_count += 1
        try:
            payload = json.loads(message.payload)
        except Exception:
            return
        params = payload.get("param") or payload.get("params") or payload
        if isinstance(params, dict):
            for key, value in params.items():
                seen[key] = value

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"diag-capture-{random.randint(1000,9999)}")
    client.username_pw_set(account, password)
    client.tls_set_context(ssl.create_default_context())
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port, 60)
    client.loop_start()

    deadline = time.time() + RUN_SECONDS
    while time.time() < deadline:
        time.sleep(2)
    client.loop_stop()
    client.disconnect()

    print(f"\n=== {msg_count} messages, {len(seen)} unique fields ===")
    for key in sorted(seen):
        print(f"{key} = {seen[key]}")


if __name__ == "__main__":
    main()
