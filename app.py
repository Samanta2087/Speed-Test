# app.py
import os
import threading
import requests
import speedtest
from flask import Flask, request, jsonify

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_verify_token")

if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
    raise RuntimeError("Set ACCESS_TOKEN and PHONE_NUMBER_ID environment variables")

app = Flask(__name__)

BASE_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

def send_text(to, text):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    r = requests.post(BASE_URL, headers=HEADERS, json=payload)
    try:
        r.raise_for_status()
    except Exception:
        app.logger.warning("Send text failed: %s %s", r.status_code, r.text)

def send_menu(to):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "📋 Choose an option:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "speedtest", "title": "🚀 Speedtest"}},
                    {"type": "reply", "reply": {"id": "ping", "title": "📡 Ping"}},
                    {"type": "reply", "reply": {"id": "menu", "title": "📜 Menu"}}
                ]
            }
        }
    }
    r = requests.post(BASE_URL, headers=HEADERS, json=payload)
    try:
        r.raise_for_status()
    except Exception:
        app.logger.warning("Send menu failed: %s %s", r.status_code, r.text)

def speedtest_worker(to, quick=False):
    try:
        send_text(to, "🚀 Running speed test... this may take a while.")
        st = speedtest.Speedtest()
        st.get_best_server()
        # quick option: fewer threads to be faster (but less accurate)
        if quick:
            download = st.download(threads=1) / 1_000_000
            upload = st.upload(threads=1) / 1_000_000
        else:
            download = st.download() / 1_000_000
            upload = st.upload() / 1_000_000
        ping = st.results.ping
        msg = (f"✅ Speedtest Complete!\n\n"
               f"Ping: {ping:.2f} ms\n"
               f"Download: {download:.2f} Mbps\n"
               f"Upload: {upload:.2f} Mbps")
        send_text(to, msg)
    except Exception as e:
        send_text(to, f"⚠️ Speedtest failed: {e}")

def run_speedtest_async(to, quick=False):
    t = threading.Thread(target=speedtest_worker, args=(to, quick), daemon=True)
    t.start()

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    # Basic safe traversal of the webhook payload
    entries = data.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages") or []
            for msg in messages:
                from_number = msg.get("from")
                if not from_number:
                    continue
                # text message
                if "text" in msg:
                    text = msg["text"].get("body", "").strip().lower()
                    if text == "menu" or text == "/menu":
                        send_menu(from_number)
                    elif text == "speedtest" or text == "/speedtest":
                        # start speedtest in background
                        run_speedtest_async(from_number, quick=False)
                    elif text == "quick" or text == "/quick":
                        run_speedtest_async(from_number, quick=True)
                    elif text == "ping" or text == "/ping":
                        # quick ping obtained from speedtest results
                        try:
                            st = speedtest.Speedtest()
                            st.get_best_server()
                            send_text(from_number, f"📡 Ping: {st.results.ping:.2f} ms")
                        except Exception as e:
                            send_text(from_number, f"⚠️ Ping failed: {e}")
                    else:
                        send_text(from_number, "Send 'menu' to see options.")
                # interactive button replies
                elif "interactive" in msg:
                    interactive = msg["interactive"]
                    # button reply
                    if "button_reply" in interactive:
                        button_id = interactive["button_reply"].get("id")
                        if button_id == "speedtest":
                            run_speedtest_async(from_number, quick=False)
                        elif button_id == "ping":
                            try:
                                st = speedtest.Speedtest()
                                st.get_best_server()
                                send_text(from_number, f"📡 Ping: {st.results.ping:.2f} ms")
                            except Exception as e:
                                send_text(from_number, f"⚠️ Ping failed: {e}")
                        elif button_id == "menu":
                            send_menu(from_number)
    return "OK", 200

if __name__ == "__main__":
    # Render sets PORT in env — fallback to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
