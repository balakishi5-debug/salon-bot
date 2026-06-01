import os
import time
import requests
from flask import Flask, request, jsonify, render_template_string
from groq import Groq
from supabase import create_client

app = Flask(__name__)
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

WHATSAPP_TOKEN  = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN", "salon123")
SUPABASE_URL    = os.environ.get("SUPABASE_URL")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY")
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "garant2024")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SISTEM_PROMPTU = """Sən Garant Consulting şirkətinin WhatsApp köməkçisisən. Peşəkar, mehriban və isti üslubda danışırsan.

ŞİRKƏT MƏLUMATLARI:
- Ad: Garant Consulting
- Təsisçilər: Balakişi Qurbanov və Ayşən Salamova
- Rəhbər: Ayşən Salamova
- İş saatları: Bazar ertəsi – Cümə, saat 10:00 – 18:00

XİDMƏTLƏRİMİZ VƏ QİYMƏTLƏR:
1. 📊 Mühasibat uçotunun aparılması — aylıq 150₼-dan
2. 📋 Vergi hesabatlarının hazırlanması — 80₼-dan
3. 💼 Əmək haqqı hesablanması (Payroll) — aylıq 100₼-dan
4. 🏢 Şirkət qeydiyyatı — 200₼
5. 🏢 Şirkətin ləğvi — 300₼-dan
6. 📑 Mühasibat konsaltinqi — saatlıq 50₼
7. 🔍 Maliyyə audit xidməti — 500₼-dan
8. 💰 Vergi optimallaşdırması — fərdi qiymət
9. 📈 Maliyyə hesabatlarının hazırlanması — 120₼-dan

DANIŞIQ QAYDALARI:
- Həmişə mehriban, isti və peşəkar ol
- Müştərinin adını bildikdə ona adı ilə müraciət et
- Əvvəlki müraciəti varsa xatırlat: "Sizi yenidən görməkdən məmnunuq!"
- Sualları aydın və qısa cavabla
- Müştəri müraciət etmək istədikdə YALNIZ adını soruş (telefon nömrəsi avtomatik var)
- Ad alındıqdan sonra hansı xidməti istədiyini soruş
- Bütün məlumatlar tamamlandıqda MÜTLƏQ bu formatda yaz:
  ✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]
- Qeydiyyatdan sonra de: "🎉 Hörmətli [ad], müraciətiniz qəbul edildi! Ən qısa zamanda mütəxəssislərimiz sizinlə əlaqə saxlayacaq. Garant Consulting olaraq sizə ən keyfiyyətli xidməti təqdim etməyə hazırıq! 🙏"
- İş saatları xaricində yazılsa: "Hal-hazırda iş saatlarımız xaricindədir (B.E-Cümə, 10:00-18:00). Sabah iş saatlarında sizinlə əlaqə saxlanılacaq! 🌙"
"""

conversations = {}


def send_whatsapp(to, text):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, headers=headers, json=payload)


def send_buttons(to, body_text, buttons):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    btn_list = [{"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}} for b in buttons[:3]]
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body_text}, "action": {"buttons": btn_list}}
    }
    requests.post(url, headers=headers, json=payload)


def download_whatsapp_audio(media_id):
    """WhatsApp media ID-dən audio faylını yüklə"""
    try:
        # 1. Media URL-ni al
        url_req = requests.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        media_url = url_req.json().get("url")
        if not media_url:
            return None

        # 2. Audio faylını yüklə
        audio_resp = requests.get(
            media_url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        return audio_resp.content  # bytes qaytarır
    except Exception as e:
        print(f"Audio yükləmə xətası: {e}")
        return None


def transcribe_audio(audio_bytes, mime_type="audio/ogg"):
    """Groq Whisper ilə səsli mesajı mətнə çevir"""
    try:
        import io
        # Mime type-a görə fayl uzantısını müəyyən et
        ext_map = {
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "mp4",
            "audio/wav": "wav",
            "audio/webm": "webm",
        }
        ext = ext_map.get(mime_type, "ogg")
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"voice.{ext}"

        transcription = groq_client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=audio_file,
            language="az",          # Azərbaycan dili
            response_format="text"
        )
        return transcription.strip() if transcription else None
    except Exception as e:
        print(f"Transkripsiya xətası: {e}")
        return None


def get_customer(phone):
    try:
        result = supabase.table("musteriler").select("*").eq("telefon", phone).execute()
        return result.data[0] if result.data else None
    except:
        return None


def save_customer(phone, ad=None, xidmet=None):
    try:
        existing = get_customer(phone)
        if existing:
            update_data = {"son_muraciet": "now()", "muraciet_sayi": existing["muraciet_sayi"] + 1}
            if ad: update_data["ad"] = ad
            if xidmet: update_data["xidmet"] = xidmet
            supabase.table("musteriler").update(update_data).eq("telefon", phone).execute()
        else:
            supabase.table("musteriler").insert({"telefon": phone, "ad": ad, "xidmet": xidmet}).execute()
    except:
        pass


def save_muraciet(phone, ad, xidmet):
    try:
        supabase.table("muracietler").insert({"telefon": phone, "ad": ad, "xidmet": xidmet, "status": "yeni"}).execute()
    except:
        pass


def send_welcome(phone):
    customer = get_customer(phone)
    if customer and customer.get("ad"):
        ad = customer["ad"]
        muraciet_sayi = customer.get("muraciet_sayi", 1)
        send_whatsapp(phone, f"Xoş gördük, hörmətli *{ad}*! 👋\nSizi yenidən görməkdən məmnunuq! Bu sizin {muraciet_sayi + 1}-ci müraciətinizdir. 🌟")
        time.sleep(1)
        send_buttons(phone, "Sizə bu dəfə necə kömək edə bilərik? 👇",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe", "title": "📞 Əlaqə"}])
    else:
        send_whatsapp(phone, "Salam! 👋 *Garant Consulting*-ə xoş gəldiniz!\nPeşəkar mühasibat xidmətləri üçün doğru yerə müraciət etdiniz. 💼")
        time.sleep(1)
        send_whatsapp(phone, "🏢 *Garant Consulting*:\n• Rəhbər: Ayşən Salamova\n• İş saatları: B.E – Cümə, 10:00 – 18:00\n• Peşəkar mühasibat & vergi xidmətləri\n• Təcrübəli mütəxəssislər komandası")
        time.sleep(1)
        send_buttons(phone, "Sizə necə kömək edə bilərik? 👇",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlərimiz"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe", "title": "📞 Əlaqə"}])
    save_customer(phone)


def get_ai_response(phone, user_message):
    if phone not in conversations:
        conversations[phone] = []
    customer = get_customer(phone)
    musteri_melumat = f"\nMÜŞTƏRİ TELEFONU: +{phone} (soruşma)"
    if customer and customer.get("ad"):
        musteri_melumat += f"\nMÜŞTƏRİNİN ADI: {customer['ad']} (adı ilə müraciət et)"
    if customer and customer.get("muraciet_sayi", 0) > 1:
        musteri_melumat += f"\nƏVVƏLKİ MÜRACİƏTLƏR: {customer['muraciet_sayi']} dəfə müraciət edib"
    conversations[phone].append({"role": "user", "content": user_message})
    if len(conversations[phone]) > 20:
        conversations[phone] = conversations[phone][-20:]
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile", max_tokens=600,
        messages=[{"role": "system", "content": SISTEM_PROMPTU + musteri_melumat}, *conversations[phone]]
    )
    ai_text = response.choices[0].message.content
    conversations[phone].append({"role": "assistant", "content": ai_text})
    return ai_text


def process_registration(ai_text, phone):
    if "QEYDİYYAT:" in ai_text:
        try:
            details = ai_text.split("QEYDİYYAT:")[1].strip().split("|")
            ad = details[0].strip() if len(details) > 0 else ""
            xidmet = details[2].strip() if len(details) > 2 else ""
            save_customer(phone, ad=ad, xidmet=xidmet)
            save_muraciet(phone, ad, xidmet)
            owner = os.environ.get("OWNER_PHONE", "")
            if owner:
                send_whatsapp(owner,
                    f"🔔 *YENİ MÜRACİƏT — Garant Consulting*\n"
                    f"👤 Ad: {ad}\n📞 Tel: +{phone}\n💼 Xidmət: {xidmet}\n⏰ Vaxt: indicə")
        except:
            pass


@app.route("/webhook", methods=["GET"])
def verify():
    mode, token, challenge = request.args.get("hub.mode"), request.args.get("hub.verify_token"), request.args.get("hub.challenge")
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
        msg = messages[0]
        phone = msg["from"]
        mtype = msg["type"]
        if mtype == "text":
            user_text = msg["text"]["body"]
        elif mtype == "interactive" and msg["interactive"]["type"] == "button_reply":
            btn_map = {
                "btn_xidmetler": "Xidmətləriniz və qiymətlər haqqında ətraflı məlumat verin",
                "btn_qeydiyyat": "Müraciət etmək istəyirəm",
                "btn_elaqe": "Əlaqə məlumatlarınızı verin",
            }
            user_text = btn_map.get(msg["interactive"]["button_reply"]["id"], "")
        elif mtype == "audio":
            # ── SƏSLİ MESAJ İŞLƏMƏ ──
            media_id   = msg["audio"]["id"]
            mime_type  = msg["audio"].get("mime_type", "audio/ogg")
            audio_bytes = download_whatsapp_audio(media_id)
            if not audio_bytes:
                send_whatsapp(phone, "😔 Üzr istəyirəm, səsli mesajınızı eşidə bilmədim. Zəhmət olmasa yazılı şəkildə göndərin.")
                return jsonify({"status": "ok"})
            user_text = transcribe_audio(audio_bytes, mime_type)
            if not user_text:
                send_whatsapp(phone, "😔 Səsli mesajınızı başa düşə bilmədim. Zəhmət olmasa yenidən cəhd edin və ya yazılı göndərin.")
                return jsonify({"status": "ok"})
            # İstifadəçiyə transkripsiya edilən mətni göstər
            send_whatsapp(phone, f"🎤 Eşitdim: _{user_text}_")
            time.sleep(0.5)
        else:
            return jsonify({"status": "ok"})

        if phone not in conversations:
            send_welcome(phone)
            conversations[phone] = []
            return jsonify({"status": "ok"})

        ai_reply = get_ai_response(phone, user_text)
        process_registration(ai_reply, phone)
        send_whatsapp(phone, ai_reply)
    except (KeyError, IndexError):
        pass
    return jsonify({"status": "ok"})


# ─── ADMIN PANEL ───────────────────────────────────────────────
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="az">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Garant Consulting — Admin Panel</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #1a202c; }
.header { background: linear-gradient(135deg, #1a365d, #2b6cb0); color: white; padding: 20px 30px; display:flex; justify-content:space-between; align-items:center; }
.header h1 { font-size: 22px; }
.header p { font-size: 12px; opacity: 0.8; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; padding: 24px; }
.stat-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align:center; }
.stat-n { font-size: 36px; font-weight: 700; color: #2b6cb0; }
.stat-l { font-size: 12px; color: #718096; margin-top: 4px; }
.section { padding: 0 24px 24px; }
.section h2 { font-size: 16px; font-weight: 700; margin-bottom: 14px; color: #2d3748; }
table { width: 100%; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-collapse: collapse; }
th { background: #2b6cb0; color: white; padding: 12px 16px; text-align: left; font-size: 12px; font-weight: 600; }
td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #edf2f7; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f7fafc; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.badge.yeni { background: #c6f6d5; color: #276749; }
.badge.elanib { background: #bee3f8; color: #2c5282; }
.refresh { background: #2b6cb0; color: white; border: none; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-size: 13px; }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🏢 Garant Consulting</h1>
    <p>Admin İdarəetmə Paneli</p>
  </div>
  <button class="refresh" onclick="location.reload()">🔄 Yenilə</button>
</div>

<div class="stats">
  <div class="stat-card"><div class="stat-n">{{ cem_muraciet }}</div><div class="stat-l">Ümumi Müraciət</div></div>
  <div class="stat-card"><div class="stat-n">{{ yeni_muraciet }}</div><div class="stat-l">Yeni Müraciət</div></div>
  <div class="stat-card"><div class="stat-n">{{ cem_musteri }}</div><div class="stat-l">Ümumi Müştəri</div></div>
  <div class="stat-card"><div class="stat-n">{{ bugun }}</div><div class="stat-l">Bu gün</div></div>
</div>

<div class="section">
  <h2>📋 Son Müraciətlər</h2>
  <table>
    <tr><th>#</th><th>Ad</th><th>Telefon</th><th>Xidmət</th><th>Status</th><th>Tarix</th></tr>
    {% for m in muracietler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ m.ad or '—' }}</td>
      <td>+{{ m.telefon }}</td>
      <td>{{ m.xidmet or '—' }}</td>
      <td><span class="badge {{ m.status }}">{{ m.status }}</span></td>
      <td>{{ m.tarix[:16] if m.tarix else '—' }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="section">
  <h2>👥 Müştərilər</h2>
  <table>
    <tr><th>#</th><th>Ad</th><th>Telefon</th><th>Son Xidmət</th><th>Müraciət</th><th>Qeydiyyat</th></tr>
    {% for m in musteriler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ m.ad or '—' }}</td>
      <td>+{{ m.telefon }}</td>
      <td>{{ m.xidmet or '—' }}</td>
      <td>{{ m.muraciet_sayi }}</td>
      <td>{{ m.qeydiyyat_tarixi[:10] if m.qeydiyyat_tarixi else '—' }}</td>
    </tr>
    {% endfor %}
  </table>
</div>
</body>
</html>
"""

@app.route("/admin")
def admin():
    pwd = request.args.get("pwd", "")
    if pwd != ADMIN_PASSWORD:
        return "<h2>❌ Giriş qadağandır. URL-ə ?pwd=şifrəniz əlavə edin.</h2>", 403
    try:
        muracietler = supabase.table("muracietler").select("*").order("tarix", desc=True).limit(50).execute().data
        musteriler  = supabase.table("musteriler").select("*").order("son_muraciet", desc=True).execute().data
        from datetime import date
        bugun_str = str(date.today())
        bugun = sum(1 for m in muracietler if m.get("tarix", "").startswith(bugun_str))
        yeni  = sum(1 for m in muracietler if m.get("status") == "yeni")
        return render_template_string(ADMIN_HTML,
            muracietler=muracietler, musteriler=musteriler,
            cem_muraciet=len(muracietler), yeni_muraciet=yeni,
            cem_musteri=len(musteriler), bugun=bugun)
    except Exception as e:
        return f"<h3>Xəta: {e}</h3>", 500


@app.route("/")
def home():
    return "Garant Consulting WhatsApp Bot işləyir! ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
import os
import time
import requests
from flask import Flask, request, jsonify, render_template_string
from groq import Groq
from supabase import create_client

app = Flask(__name__)
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

WHATSAPP_TOKEN  = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN", "salon123")
SUPABASE_URL    = os.environ.get("SUPABASE_URL")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY")
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "garant2024")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SISTEM_PROMPTU = """Sən Garant Consulting şirkətinin WhatsApp köməkçisisən. Peşəkar, mehriban və isti üslubda danışırsan.

ŞİRKƏT MƏLUMATLARI:
- Ad: Garant Consulting
- Təsisçilər: Balakişi Qurbanov və Ayşən Salamova
- Rəhbər: Ayşən Salamova
- İş saatları: Bazar ertəsi – Cümə, saat 10:00 – 18:00

XİDMƏTLƏRİMİZ VƏ QİYMƏTLƏR:
1. 📊 Mühasibat uçotunun aparılması — aylıq 150₼-dan
2. 📋 Vergi hesabatlarının hazırlanması — 80₼-dan
3. 💼 Əmək haqqı hesablanması (Payroll) — aylıq 100₼-dan
4. 🏢 Şirkət qeydiyyatı — 200₼
5. 🏢 Şirkətin ləğvi — 300₼-dan
6. 📑 Mühasibat konsaltinqi — saatlıq 50₼
7. 🔍 Maliyyə audit xidməti — 500₼-dan
8. 💰 Vergi optimallaşdırması — fərdi qiymət
9. 📈 Maliyyə hesabatlarının hazırlanması — 120₼-dan

DANIŞIQ QAYDALARI:
- Həmişə mehriban, isti və peşəkar ol
- Müştərinin adını bildikdə ona adı ilə müraciət et
- Əvvəlki müraciəti varsa xatırlat: "Sizi yenidən görməkdən məmnunuq!"
- Sualları aydın və qısa cavabla
- Müştəri müraciət etmək istədikdə YALNIZ adını soruş (telefon nömrəsi avtomatik var)
- Ad alındıqdan sonra hansı xidməti istədiyini soruş
- Bütün məlumatlar tamamlandıqda MÜTLƏQ bu formatda yaz:
  ✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]
- Qeydiyyatdan sonra de: "🎉 Hörmətli [ad], müraciətiniz qəbul edildi! Ən qısa zamanda mütəxəssislərimiz sizinlə əlaqə saxlayacaq. Garant Consulting olaraq sizə ən keyfiyyətli xidməti təqdim etməyə hazırıq! 🙏"
- İş saatları xaricində yazılsa: "Hal-hazırda iş saatlarımız xaricindədir (B.E-Cümə, 10:00-18:00). Sabah iş saatlarında sizinlə əlaqə saxlanılacaq! 🌙"
"""

conversations = {}


def send_whatsapp(to, text):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, headers=headers, json=payload)


def send_buttons(to, body_text, buttons):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    btn_list = [{"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}} for b in buttons[:3]]
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body_text}, "action": {"buttons": btn_list}}
    }
    requests.post(url, headers=headers, json=payload)


def download_whatsapp_audio(media_id):
    """WhatsApp media ID-dən audio faylını yüklə"""
    try:
        # 1. Media URL-ni al
        url_req = requests.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        media_url = url_req.json().get("url")
        if not media_url:
            return None

        # 2. Audio faylını yüklə
        audio_resp = requests.get(
            media_url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        return audio_resp.content  # bytes qaytarır
    except Exception as e:
        print(f"Audio yükləmə xətası: {e}")
        return None


def transcribe_audio(audio_bytes, mime_type="audio/ogg"):
    """Groq Whisper ilə səsli mesajı mətнə çevir"""
    try:
        import io
        # Mime type-a görə fayl uzantısını müəyyən et
        ext_map = {
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "mp4",
            "audio/wav": "wav",
            "audio/webm": "webm",
        }
        ext = ext_map.get(mime_type, "ogg")
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"voice.{ext}"

        transcription = groq_client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=audio_file,
            language="az",          # Azərbaycan dili
            response_format="text"
        )
        return transcription.strip() if transcription else None
    except Exception as e:
        print(f"Transkripsiya xətası: {e}")
        return None


def get_customer(phone):
    try:
        result = supabase.table("musteriler").select("*").eq("telefon", phone).execute()
        return result.data[0] if result.data else None
    except:
        return None


def save_customer(phone, ad=None, xidmet=None):
    try:
        existing = get_customer(phone)
        if existing:
            update_data = {"son_muraciet": "now()", "muraciet_sayi": existing["muraciet_sayi"] + 1}
            if ad: update_data["ad"] = ad
            if xidmet: update_data["xidmet"] = xidmet
            supabase.table("musteriler").update(update_data).eq("telefon", phone).execute()
        else:
            supabase.table("musteriler").insert({"telefon": phone, "ad": ad, "xidmet": xidmet}).execute()
    except:
        pass


def save_muraciet(phone, ad, xidmet):
    try:
        supabase.table("muracietler").insert({"telefon": phone, "ad": ad, "xidmet": xidmet, "status": "yeni"}).execute()
    except:
        pass


def send_welcome(phone):
    customer = get_customer(phone)
    if customer and customer.get("ad"):
        ad = customer["ad"]
        muraciet_sayi = customer.get("muraciet_sayi", 1)
        send_whatsapp(phone, f"Xoş gördük, hörmətli *{ad}*! 👋\nSizi yenidən görməkdən məmnunuq! Bu sizin {muraciet_sayi + 1}-ci müraciətinizdir. 🌟")
        time.sleep(1)
        send_buttons(phone, "Sizə bu dəfə necə kömək edə bilərik? 👇",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe", "title": "📞 Əlaqə"}])
    else:
        send_whatsapp(phone, "Salam! 👋 *Garant Consulting*-ə xoş gəldiniz!\nPeşəkar mühasibat xidmətləri üçün doğru yerə müraciət etdiniz. 💼")
        time.sleep(1)
        send_whatsapp(phone, "🏢 *Garant Consulting*:\n• Rəhbər: Ayşən Salamova\n• İş saatları: B.E – Cümə, 10:00 – 18:00\n• Peşəkar mühasibat & vergi xidmətləri\n• Təcrübəli mütəxəssislər komandası")
        time.sleep(1)
        send_buttons(phone, "Sizə necə kömək edə bilərik? 👇",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlərimiz"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe", "title": "📞 Əlaqə"}])
    save_customer(phone)


def get_ai_response(phone, user_message):
    if phone not in conversations:
        conversations[phone] = []
    customer = get_customer(phone)
    musteri_melumat = f"\nMÜŞTƏRİ TELEFONU: +{phone} (soruşma)"
    if customer and customer.get("ad"):
        musteri_melumat += f"\nMÜŞTƏRİNİN ADI: {customer['ad']} (adı ilə müraciət et)"
    if customer and customer.get("muraciet_sayi", 0) > 1:
        musteri_melumat += f"\nƏVVƏLKİ MÜRACİƏTLƏR: {customer['muraciet_sayi']} dəfə müraciət edib"
    conversations[phone].append({"role": "user", "content": user_message})
    if len(conversations[phone]) > 20:
        conversations[phone] = conversations[phone][-20:]
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile", max_tokens=600,
        messages=[{"role": "system", "content": SISTEM_PROMPTU + musteri_melumat}, *conversations[phone]]
    )
    ai_text = response.choices[0].message.content
    conversations[phone].append({"role": "assistant", "content": ai_text})
    return ai_text


def process_registration(ai_text, phone):
    if "QEYDİYYAT:" in ai_text:
        try:
            details = ai_text.split("QEYDİYYAT:")[1].strip().split("|")
            ad = details[0].strip() if len(details) > 0 else ""
            xidmet = details[2].strip() if len(details) > 2 else ""
            save_customer(phone, ad=ad, xidmet=xidmet)
            save_muraciet(phone, ad, xidmet)
            owner = os.environ.get("OWNER_PHONE", "")
            if owner:
                send_whatsapp(owner,
                    f"🔔 *YENİ MÜRACİƏT — Garant Consulting*\n"
                    f"👤 Ad: {ad}\n📞 Tel: +{phone}\n💼 Xidmət: {xidmet}\n⏰ Vaxt: indicə")
        except:
            pass


@app.route("/webhook", methods=["GET"])
def verify():
    mode, token, challenge = request.args.get("hub.mode"), request.args.get("hub.verify_token"), request.args.get("hub.challenge")
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
        msg = messages[0]
        phone = msg["from"]
        mtype = msg["type"]
        if mtype == "text":
            user_text = msg["text"]["body"]
        elif mtype == "interactive" and msg["interactive"]["type"] == "button_reply":
            btn_map = {
                "btn_xidmetler": "Xidmətləriniz və qiymətlər haqqında ətraflı məlumat verin",
                "btn_qeydiyyat": "Müraciət etmək istəyirəm",
                "btn_elaqe": "Əlaqə məlumatlarınızı verin",
            }
            user_text = btn_map.get(msg["interactive"]["button_reply"]["id"], "")
        elif mtype == "audio":
            # ── SƏSLİ MESAJ İŞLƏMƏ ──
            media_id   = msg["audio"]["id"]
            mime_type  = msg["audio"].get("mime_type", "audio/ogg")
            audio_bytes = download_whatsapp_audio(media_id)
            if not audio_bytes:
                send_whatsapp(phone, "😔 Üzr istəyirəm, səsli mesajınızı eşidə bilmədim. Zəhmət olmasa yazılı şəkildə göndərin.")
                return jsonify({"status": "ok"})
            user_text = transcribe_audio(audio_bytes, mime_type)
            if not user_text:
                send_whatsapp(phone, "😔 Səsli mesajınızı başa düşə bilmədim. Zəhmət olmasa yenidən cəhd edin və ya yazılı göndərin.")
                return jsonify({"status": "ok"})
            # İstifadəçiyə transkripsiya edilən mətni göstər
            send_whatsapp(phone, f"🎤 Eşitdim: _{user_text}_")
            time.sleep(0.5)
        else:
            return jsonify({"status": "ok"})

        if phone not in conversations:
            send_welcome(phone)
            conversations[phone] = []
            return jsonify({"status": "ok"})

        ai_reply = get_ai_response(phone, user_text)
        process_registration(ai_reply, phone)
        send_whatsapp(phone, ai_reply)
    except (KeyError, IndexError):
        pass
    return jsonify({"status": "ok"})


# ─── ADMIN PANEL ───────────────────────────────────────────────
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="az">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Garant Consulting — Admin Panel</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #1a202c; }
.header { background: linear-gradient(135deg, #1a365d, #2b6cb0); color: white; padding: 20px 30px; display:flex; justify-content:space-between; align-items:center; }
.header h1 { font-size: 22px; }
.header p { font-size: 12px; opacity: 0.8; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; padding: 24px; }
.stat-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align:center; }
.stat-n { font-size: 36px; font-weight: 700; color: #2b6cb0; }
.stat-l { font-size: 12px; color: #718096; margin-top: 4px; }
.section { padding: 0 24px 24px; }
.section h2 { font-size: 16px; font-weight: 700; margin-bottom: 14px; color: #2d3748; }
table { width: 100%; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-collapse: collapse; }
th { background: #2b6cb0; color: white; padding: 12px 16px; text-align: left; font-size: 12px; font-weight: 600; }
td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #edf2f7; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f7fafc; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.badge.yeni { background: #c6f6d5; color: #276749; }
.badge.elanib { background: #bee3f8; color: #2c5282; }
.refresh { background: #2b6cb0; color: white; border: none; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-size: 13px; }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🏢 Garant Consulting</h1>
    <p>Admin İdarəetmə Paneli</p>
  </div>
  <button class="refresh" onclick="location.reload()">🔄 Yenilə</button>
</div>

<div class="stats">
  <div class="stat-card"><div class="stat-n">{{ cem_muraciet }}</div><div class="stat-l">Ümumi Müraciət</div></div>
  <div class="stat-card"><div class="stat-n">{{ yeni_muraciet }}</div><div class="stat-l">Yeni Müraciət</div></div>
  <div class="stat-card"><div class="stat-n">{{ cem_musteri }}</div><div class="stat-l">Ümumi Müştəri</div></div>
  <div class="stat-card"><div class="stat-n">{{ bugun }}</div><div class="stat-l">Bu gün</div></div>
</div>

<div class="section">
  <h2>📋 Son Müraciətlər</h2>
  <table>
    <tr><th>#</th><th>Ad</th><th>Telefon</th><th>Xidmət</th><th>Status</th><th>Tarix</th></tr>
    {% for m in muracietler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ m.ad or '—' }}</td>
      <td>+{{ m.telefon }}</td>
      <td>{{ m.xidmet or '—' }}</td>
      <td><span class="badge {{ m.status }}">{{ m.status }}</span></td>
      <td>{{ m.tarix[:16] if m.tarix else '—' }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="section">
  <h2>👥 Müştərilər</h2>
  <table>
    <tr><th>#</th><th>Ad</th><th>Telefon</th><th>Son Xidmət</th><th>Müraciət</th><th>Qeydiyyat</th></tr>
    {% for m in musteriler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ m.ad or '—' }}</td>
      <td>+{{ m.telefon }}</td>
      <td>{{ m.xidmet or '—' }}</td>
      <td>{{ m.muraciet_sayi }}</td>
      <td>{{ m.qeydiyyat_tarixi[:10] if m.qeydiyyat_tarixi else '—' }}</td>
    </tr>
    {% endfor %}
  </table>
</div>
</body>
</html>
"""

@app.route("/admin")
def admin():
    pwd = request.args.get("pwd", "")
    if pwd != ADMIN_PASSWORD:
        return "<h2>❌ Giriş qadağandır. URL-ə ?pwd=şifrəniz əlavə edin.</h2>", 403
    try:
        muracietler = supabase.table("muracietler").select("*").order("tarix", desc=True).limit(50).execute().data
        musteriler  = supabase.table("musteriler").select("*").order("son_muraciet", desc=True).execute().data
        from datetime import date
        bugun_str = str(date.today())
        bugun = sum(1 for m in muracietler if m.get("tarix", "").startswith(bugun_str))
        yeni  = sum(1 for m in muracietler if m.get("status") == "yeni")
        return render_template_string(ADMIN_HTML,
            muracietler=muracietler, musteriler=musteriler,
            cem_muraciet=len(muracietler), yeni_muraciet=yeni,
            cem_musteri=len(musteriler), bugun=bugun)
    except Exception as e:
        return f"<h3>Xəta: {e}</h3>", 500


@app.route("/")
def home():
    return "Garant Consulting WhatsApp Bot işləyir! ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

