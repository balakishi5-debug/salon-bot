import os
import time
import requests
from flask import Flask, request, jsonify
from groq import Groq

app = Flask(__name__)
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

WHATSAPP_TOKEN  = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN", "salon123")

SALON_INFO = """Sən Garant Consulting şirkətinin WhatsApp köməkçisisən.

ŞİRKƏT MƏLUMATLARI:
- Ad: Garant Consulting
- Təsisçilər: Balakişi Qurbanov və Ayşən Salamova
- Rəhbər: Ayşən Salamova
- İş saatları: Həftənin 5 günü (Bazar ertəsi – Cümə), saat 10:00 – 18:00

XİDMƏTLƏRİMİZ:
1. 📊 Mühasibat uçotunun aparılması
2. 📋 Vergi hesabatlarının hazırlanması
3. 💼 Əmək haqqı hesablanması (Payroll)
4. 🏢 Şirkət qeydiyyatı və ləğvi
5. 📑 Mühasibat konsaltinqi
6. 🔍 Maliyyə audit xidməti
7. 💰 Vergi optimallaşdırması
8. 📈 Maliyyə hesabatlarının hazırlanması

DAVRANIŞIN:
- Azərbaycan dilində mehriban və peşəkar danış
- Müştərinin sualını diqqətlə dinlə
- Xidmətlər haqqında ətraflı məlumat ver
- Müştəri xidmət seçdikdə və ya əlaqə saxlamaq istədikdə onun adını və telefon nömrəsini öyrən
- Məlumatlar tamamlandıqda mütləq bu formatda yaz:
  ✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]
- Qeydiyyat tamamlandıqdan sonra müştəriyə bildiriş göndər ki, ən qısa zamanda əlaqə yaradılacaq
- Saat xaricində yazılsa, sabah iş saatlarında cavab veriləcəyini bildir"""

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
        "Salam! 👋 *Garant Consulting*-ə xoş gəldiniz!\n"
        "Peşəkar mühasibat xidmətləri üçün doğru yerə müraciət etdiniz. 💼"
    )
    time.sleep(1)
    send_whatsapp(phone,
        "🏢 *Garant Consulting* haqqında:\n"
        "• Rəhbər: Ayşən Salamova\n"
        "• İş saatları: B.E – Cümə, 10:00 – 18:00\n"
        "• Peşəkar mühasibat & vergi xidmətləri"
    )
    time.sleep(1)
    send_buttons(phone,
        "Sizə necə kömək edə bilərik? 👇",
        [
            {"id": "btn_xidmetler", "title": "📊 Xidmətlərimiz"},
            {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
            {"id": "btn_elaqe",     "title": "📞 Əlaqə"},
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
        max_tokens=600,
        messages=[
            {"role": "system", "content": SALON_INFO},
            *conversations[phone]
        ]
    )

    ai_text = response.choices[0].message.content
    conversations[phone].append({"role": "assistant", "content": ai_text})
    return ai_text


def notify_owner(ai_text, phone):
    if "QEYDİYYAT:" in ai_text:
        owner = os.environ.get("OWNER_PHONE", "")
        if owner:
            details = ai_text.split("QEYDİYYAT:")[1].strip()
            send_whatsapp(owner,
                f"🔔 *YENİ MÜRACİƏT — Garant Consulting*\n"
                f"Müştəri nömrəsi: {phone}\n"
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
                    "btn_xidmetler": "Xidmətləriniz haqqında ətraflı məlumat verin",
                    "btn_qeydiyyat": "Müraciət etmək istəyirəm, qeydiyyatdan keçmək istəyirəm",
                    "btn_elaqe":     "Əlaqə məlumatlarınızı verin",
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
    return "Garant Consulting WhatsApp Bot işləyir! ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
