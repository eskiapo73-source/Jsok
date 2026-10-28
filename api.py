import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "keys.db")

app = Flask(__name__)

def db_connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con

def now():
    return datetime.now(timezone.utc)

def parse_date(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result
    except (ValueError, TypeError):
        return None

@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "license-api"})

@app.post("/v1/validate")
def validate():
    data = request.get_json(silent=True) or {}
    key = data.get("key")
    device_id = data.get("device_id")

    if not isinstance(key, str) or not key.strip():
        return jsonify({"ok": False, "error": "KEY_REQUIRED"}), 400

    if not isinstance(device_id, str) or not (8 <= len(device_id) <= 128):
        return jsonify({"ok": False, "error": "DEVICE_ID_INVALID"}), 400

    key = key.strip()
    device_id = device_id.strip()

    con = db_connect()
    try:
        con.execute("BEGIN IMMEDIATE")

        license_row = con.execute(
            "SELECT * FROM licenses WHERE key = ?", (key,)
        ).fetchone()

        if license_row is None:
            con.rollback()
            return jsonify({"ok": False, "error": "KEY_INVALID"}), 403

        if not license_row["active"]:
            con.rollback()
            return jsonify({"ok": False, "error": "KEY_DISABLED"}), 403

        expires = parse_date(license_row["expires"])
        if license_row["expires"] and (
            expires is None or expires <= now()
        ):
            con.rollback()
            return jsonify({"ok": False, "error": "KEY_EXPIRED"}), 403

        device = con.execute(
            "SELECT banned FROM devices WHERE key = ? AND device_id = ?",
            (key, device_id)
        ).fetchone()

        if device and device["banned"]:
            con.rollback()
            return jsonify({"ok": False, "error": "DEVICE_BANNED"}), 403

        if not device:
            count = con.execute(
                "SELECT COUNT(*) FROM devices WHERE key = ?",
                (key,)
            ).fetchone()[0]

            if count >= license_row["max_devices"]:
                con.rollback()
                return jsonify({"ok": False, "error": "DEVICE_LIMIT"}), 403

            con.execute(
                """INSERT INTO devices(key, device_id, banned, first_seen)
                   VALUES (?, ?, 0, ?)""",
                (key, device_id, now().isoformat())
            )

        con.commit()

        remaining = None
        if expires:
            remaining = max(0, int((expires - now()).total_seconds()))

        return jsonify({
            "ok": True,
            "expires": license_row["expires"],
            "remaining_seconds": remaining,
            "device_limit": license_row["max_devices"]
        })

    except sqlite3.Error:
        con.rollback()
        app.logger.exception("Database error")
        return jsonify({"ok": False, "error": "SERVER_ERROR"}), 500
    finally:
        con.close()

if __name__ == "__main__":
    # Local testing only. Do not expose this development server directly
    # to the public internet.
    app.run(host="127.0.0.1", port=8787, debug=False)