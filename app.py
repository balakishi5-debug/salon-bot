import os
import json
import time
import requests
from flask import Flask, request, jsonify
from groq import Groq

app = Flask(__name__)
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

WHATSAPP_TOKEN  = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN", "salon123")

SALON_INFO = """Sən Glamour Studio gözəllik salonunun WhatsApp köməkçisisən.

SALON MƏLUMATLARI:
- Ünvan: Neftçilər pr. 45, Bakı
- Tel: +994 50 123 45 67
- İş saatları: 09:00–19:00 (B.E – Şənbə)

XİDMƏTLƏR VƏ QİYMƏTLƏR:
- 💇 Saç Kəsimi — 15₼
- 💅 Manikür — 20₼
- 🧖 Üz Baxımı — 35₼
- 💄 Makiyaj — 40₼
- 🎨 Saç Boyası — 50₼
- 👁️ Qaş Dizaynı — 10₼

MASTERLƏRIMIZ:
- Aytən xanım (saç, boyama)
- Günay xanım (manikür, qaş)
- Leyla xanım (üz baxımı, makiyaj)

RANDEVU SAATLARI: 09:00, 11:00, 13:00, 15:00, 17:00

DAVRANIŞIN:
- Azərbaycan dilində mehriban danış
- Qısa və aydın cavab ver
- Randevu üçün: xidmət + master + saat lazımdır
- Randevu tamamlandıqda mütləq bu formatda yaz:
  ✅ RANDEVU_TƏSDİQ: [xidmət] | [master] | [saat]"""

conversations = {}


def send_whatsapp(to, text):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, headers=headers, json=payload)


def send_buttons(to, body_text, buttons):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    btn_list = [
        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
        for b in buttons[:3]
    ]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": btn_list}
        }
    }
    requests.post(url, headers=headers, json=payload)


def send_welcome(phone):
    send_whatsapp(phone,
        "Salam! 👋 *Glamour Studio*-ya xoş gəldiniz!\n"
        "Mən sizin 24/7 WhatsApp köməkçinizəm 💆‍♀️"
    )
    time.sleep(1)
    send_whatsapp(phone,
        "✨ Bakının ən yaxşı gözəllik salonu:\n"
        "• 6 fərqli xidmət\n"
        "• 3 peşəkar master\n"
        "• Əlverişli qiymətlər"
    )
    time.sleep(1)
    send_buttons(phone,
        "Sizə necə kömək edə bilərəm? 👇",
        [
            {"id": "btn_randevu", "title": "📅 Randevu al"},
            {"id": "btn_xidmet",  "title": "💅 Xidmətlər"},
            {"id": "btn_unvan",   "title": "📍 Ünvan & Saat"},
        ]
    )


def get_ai_response(phone, user_message):
    if phone not in conversations:
        conversations[phone] = []

    conversations[phone].append({"role": "user", "content": user_message})

    if len(conversations[phone]) > 20:
        conversations[phone] = conversations[phone][-20:]

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=500,
        messages=[
            {"role": "system", "content": SALON_INFO},
            *conversations[phone]
        ]
    )

    ai_text = response.choices[0].message.content
    conversations[phone].append({"role": "assistant", "content": ai_text})
    return ai_text


def notify_owner(ai_text, phone):
    if "RANDEVU_TƏSDİQ:" in ai_text:
        owner = os.environ.get("OWNER_PHONE", "")
        if owner:
            details = ai_text.split("RANDEVU_TƏSDİQ:")[1].strip()
            send_whatsapp(owner,
                f"🔔 *YENİ RANDEVU*\n"
                f"Müştəri: {phone}\n"
                f"{details}"
            )


@app.route("/webhook", methods=["GET"])
def verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        messages = data["entry"][0]["changes"][0]["value"].get("messages", [])
        if not messages:
            return jsonify({"status": "ok"})

        msg   = messages[0]
        phone = msg["from"]
        mtype = msg["type"]

        if mtype == "text":
            user_text = msg["text"]["body"]
        elif mtype == "interactive":
            if msg["interactive"]["type"] == "button_reply":
                btn_id = msg["interactive"]["button_reply"]["id"]
                btn_map = {
                    "btn_randevu": "Randevu almaq istəyirəm",
                    "btn_xidmet":  "Xidmətlər və qiymətlər haqqında məlumat ver",
                    "btn_unvan":   "Ünvan və iş saatları haqqında məlumat ver",
                }
                user_text = btn_map.get(btn_id, btn_id)
            else:
                return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "ok"})

        if phone not in conversations:
            send_welcome(phone)
            conversations[phone] = []
            return jsonify({"status": "ok"})

        ai_reply = get_ai_response(phone, user_text)
        notify_owner(ai_reply, phone)
        send_whatsapp(phone, ai_reply)

    except (KeyError, IndexError):
        pass

    return jsonify({"status": "ok"})


@app.route("/")
def home():
    return "Glamour Studio WhatsApp Bot işləyir! ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
