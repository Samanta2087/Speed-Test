import os
import threading
import requests
import speedtest
from flask import Flask, request

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_verify_token")

if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
    raise RuntimeError("Set ACCESS_TOKEN and PHONE_NUMBER_ID environment variables")

app = Flask(__name__)

BASE_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

# ----------- Senders -----------
def send_text(to, text):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(BASE_URL, headers=HEADERS, json=payload)

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
    requests.post(BASE_URL, headers=HEADERS, json=payload)

# ----------- Workers -----------
def speedtest_worker(to):
    try:
        send_text(to, "🚀 Running speed test... please wait")
        st = speedtest.Speedtest()
        st.get_best_server()
        download = st.download() / 1_000_000
        upload = st.upload() / 1_000_000
        ping = st.results.ping
        send_text(to, f"✅ Speedtest Complete!\nPing: {ping:.2f} ms\nDownload: {download:.2f} Mbps\nUpload: {upload:.2f} Mbps")
    except Exception as e:
        send_text(to, f"⚠️ Speedtest failed: {e}")

def run_speedtest_async(to):
    threading.Thread(target=speedtest_worker, args=(to,), daemon=True).start()

# ----------- Routes -----------
@app.route("/")
def home():
    return "✅ WhatsApp Bot is running. Use /webhook for Meta verification.", 200

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
    data = request.get_json()
    if not data:
        return "No data", 400

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                from_number = msg.get("from")
                if "text" in msg:
                    text = msg["text"]["body"].strip().lower()
                    if text in ["menu", "/menu"]:
                        send_menu(from_number)
                    elif text in ["speedtest", "/speedtest"]:
                        run_speedtest_async(from_number)
                    elif text in ["ping", "/ping"]:
                        st = speedtest.Speedtest()
                        st.get_best_server()
                        send_text(from_number, f"📡 Ping: {st.results.ping:.2f} ms")
                    else:
                        send_text(from_number, "Send 'menu' to see options.")
                elif "interactive" in msg:
                    button_id = msg["interactive"]["button_reply"]["id"]
                    if button_id == "speedtest":
                        run_speedtest_async(from_number)
                    elif button_id == "ping":
                        st = speedtest.Speedtest()
                        st.get_best_server()
                        send_text(from_number, f"📡 Ping: {st.results.ping:.2f} ms")
                    elif button_id == "menu":
                        send_menu(from_number)

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)