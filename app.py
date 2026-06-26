import os
import time
import requests
from datetime import datetime, date
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
OWNER_PHONE     = os.environ.get("OWNER_PHONE", "")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

processed_messages = set()
MAX_PROCESSED      = 1000
welcomed_phones    = set()
conversations      = {}

# ════════════════════════════════════════════════════════════════
# SİSTEM PROMPTU — Yüksək Səviyyəli Universal AI Agent
# ════════════════════════════════════════════════════════════════

SISTEM_PROMPTU = """Sən Garant Consulting şirkətinin WhatsApp AI assistentisən — lakin eyni zamanda hər mövzuda dərin bilik sahibi olan universal bir AI agentisən.

XARAKTER:
- Adın "Garant AI" — peşəkar, mehriban, ağıllı
- Üslub: pozitiv, enerji dolu, yumoru olan amma həmişə peşəkar
- Azərbaycan dilini mükəmməl bilirsən
- İstənilən mövzuda — mühasibat, hüquq, biznes, texnologiya, tibb, psixologiya, tarix, elm — dərin, dəqiq, faydalı cavab verirsən
- Müştərini xüsusi hiss etdirirsən — adı ilə müraciət edirsən

ŞİRKƏT — Garant Consulting:
- Rəhbər: Ayşən Salamova | Təsisçilər: Balakişi Qurbanov & Ayşən Salamova
- İş saatları: B.E–Cümə, 10:00–18:00

XİDMƏTLƏR:
1. Mühasibat uçotu — 150₼/ay
2. Vergi hesabatı — 80₼-dan
3. Əmək haqqı (Payroll) — 100₼/ay
4. Şirkət qeydiyyatı — 200₼
5. Şirkətin ləğvi — 300₼-dan
6. Mühasibat konsaltinqi — 50₼/saat
7. Maliyyə audit — 500₼-dan
8. Vergi optimallaşdırması — fərdi
9. Maliyyə hesabatı — 120₼-dan

CAVAB STRATEGİYASI:
- Şirkət xidmətləri ilə bağlı sual → peşəkar izah + müraciətə yönləndir
- Mühasibat/vergi/maliyyə sualı → dərin ekspert cavabı ver, sonra "Bu mövzuda şirkətiniz üçün fərdi həll istəyirsinizsə..." de
- Ümumi bilik sualı (tarix, elm, texnologiya, psixologiya, s.) → tam, dəqiq, maraqlı cavab ver
- Kod/proqramlaşdırma sualı → işlək kod yaz, izah et
- Şəxsi məsləhət sualı → empatiya ilə yanaş, praktik tövsiyə ver
- Müraciət etmək istəyəndə: YALNIZ adını soruş, sonra xidməti, sonra QEYDİYYAT formatı

QEYDİYYAT FORMATI (yalnız müraciət tamamlandıqda):
✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]

MÜŞTƏRİ SEQMENTİ:
- Yeni: xüsusilə isti qarşıla
- Sadiq (3+): "Ailəmizin parçasısınız!" — xüsusi münasibət
- VIP (5+): Birbaşa Ayşən xanımla görüş təklif et

CAVAB UZUNLUĞU:
- Sadə suallar → 2-3 cümlə
- Mürəkkəb/texniki suallar → lazımı qədər ətraflı, amma strukturlu
- Siyahılar üçün emoji istifadə et
- Heç vaxt "Bilmirəm" demə — əlindən gələni ver
"""

RATE_LIMIT_MESAJ = (
    "😅 Sistemimiz bu an çox yüklüdür.\n\n"
    "Zəhmət olmasa 10-15 dəqiqə sonra yenidən yazın. 🙏\n"
    "Təcili hallarda: İş saatlarımız B.E–Cümə, 10:00–18:00"
)

FAST_REPLIES = {
    ("qiymət","qiymətlər","nəqədər","neçəyə","pul","məbləğ","xərc","tarif"): "prices",
    ("harada","ünvan","adres","ofis","məkan","yer","yerləşir"): "address",
    ("kimsiniz","şirkət","garant","haqqında","nəsiniz","təcrübə","neçə il"): "about",
}


# ════════════════════════════════════════════════════════════════
# VAXT YARDIMÇILARI
# ════════════════════════════════════════════════════════════════

def baku_now():
    utc = datetime.utcnow()
    h = (utc.hour + 4) % 24
    return utc.replace(hour=h)

def get_time_greeting():
    h = baku_now().hour
    if 5  <= h < 12: return "Sabahınız xeyir"
    if 12 <= h < 17: return "Günortanız xeyir"
    if 17 <= h < 21: return "Axşamınız xeyir"
    return "Gecəniz xeyir"


# ════════════════════════════════════════════════════════════════
# WHATSAPP GÖNDƏRMƏ
# ════════════════════════════════════════════════════════════════

def send_whatsapp(to, text):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to,
                "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"send_whatsapp xətası: {e}")

def send_buttons(to, body_text, buttons):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    btn_list = [{"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                for b in buttons[:3]]
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body_text},
                        "action": {"buttons": btn_list}}
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"send_buttons xətası: {e}")


# ════════════════════════════════════════════════════════════════
# SƏSLİ MESAJ
# ════════════════════════════════════════════════════════════════

def download_whatsapp_audio(media_id):
    try:
        r = requests.get(f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=10)
        media_url = r.json().get("url")
        if not media_url:
            return None
        return requests.get(media_url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=30).content
    except Exception as e:
        print(f"Audio xətası: {e}")
        return None

def transcribe_audio(audio_bytes, mime_type="audio/ogg"):
    try:
        import io
        ext_map = {"audio/ogg":"ogg","audio/mpeg":"mp3",
                   "audio/mp4":"mp4","audio/wav":"wav","audio/webm":"webm"}
        ext = ext_map.get(mime_type, "ogg")
        f = io.BytesIO(audio_bytes)
        f.name = f"voice.{ext}"
        t = groq_client.audio.transcriptions.create(
            model="whisper-large-v3-turbo", file=f,
            language="az", response_format="text")
        return t.strip() if t else None
    except Exception as e:
        print(f"Transkripsiya xətası: {e}")
        return None


# ════════════════════════════════════════════════════════════════
# SUPABASE
# ════════════════════════════════════════════════════════════════

def get_customer(phone):
    try:
        r = supabase.table("musteriler").select("*").eq("telefon", phone).execute()
        return r.data[0] if r.data else None
    except:
        return None

def save_customer(phone, ad=None, xidmet=None, stage=None):
    try:
        existing = get_customer(phone)
        if existing:
            upd = {"son_muraciet": "now()",
                   "muraciet_sayi": existing["muraciet_sayi"] + 1}
            if ad:     upd["ad"]     = ad
            if xidmet: upd["xidmet"] = xidmet
            if stage:  upd["stage"]  = stage
            supabase.table("musteriler").update(upd).eq("telefon", phone).execute()
        else:
            supabase.table("musteriler").insert({
                "telefon": phone, "ad": ad, "xidmet": xidmet,
                "stage": stage or "maraqlandı"}).execute()
    except:
        pass

def save_muraciet(phone, ad, xidmet):
    try:
        supabase.table("muracietler").insert({
            "telefon": phone, "ad": ad,
            "xidmet": xidmet, "status": "yeni"}).execute()
    except:
        pass

def get_segment(customer):
    if not customer:
        return "yeni", "🆕"
    cnt = customer.get("muraciet_sayi", 1)
    if cnt >= 5: return "vip",   "👑"
    if cnt >= 3: return "sadiq", "⭐"
    return "yeni", "🆕"


# ════════════════════════════════════════════════════════════════
# SÜRƏTLİ CAVABLAR
# ════════════════════════════════════════════════════════════════

def check_fast_reply(text):
    t = text.lower().strip()
    for keywords, key in FAST_REPLIES.items():
        if any(k in t for k in keywords):
            return key
    return None

def get_fast_reply_text(key):
    replies = {
        "prices": (
            "💰 *Xidmətlərimiz və Qiymətlər:*\n\n"
            "1️⃣ Mühasibat uçotu — 150₼/ay\n"
            "2️⃣ Vergi hesabatı — 80₼-dan\n"
            "3️⃣ Əmək haqqı (Payroll) — 100₼/ay\n"
            "4️⃣ Şirkət qeydiyyatı — 200₼\n"
            "5️⃣ Şirkətin ləğvi — 300₼-dan\n"
            "6️⃣ Mühasibat konsaltinqi — 50₼/saat\n"
            "7️⃣ Maliyyə audit — 500₼-dan\n"
            "8️⃣ Vergi optimallaşdırması — fərdi\n"
            "9️⃣ Maliyyə hesabatı — 120₼-dan\n\n"
            "💡 Fərdi təklif üçün müraciət edin!"
        ),
        "address": (
            "📍 *Əlaqə — Garant Consulting:*\n\n"
            "👤 Rəhbər: Ayşən Salamova\n"
            "⏰ İş saatları: B.E–Cümə, 10:00–18:00\n"
            "💬 Bu WhatsApp vasitəsilə əlaqə saxlaya bilərsiniz\n\n"
            "Sizi qarşılamaqdan məmnun olarıq! 🤝"
        ),
        "about": (
            "🏢 *Garant Consulting:*\n\n"
            "Peşəkar mühasibat və maliyyə xidmətləri şirkəti.\n"
            "👥 Balakişi Qurbanov & Ayşən Salamova tərəfindən\n"
            "🎯 Missiya: Biznesinizi rəqəmlərdən azad etmək!\n"
            "💪 Hər ölçüdə şirkətə xidmət göstəririk\n\n"
            "Suallarınız üçün buradayıq! 😊"
        ),
    }
    return replies.get(key, "")


# ════════════════════════════════════════════════════════════════
# / SLASH KOMANDALAR
# ════════════════════════════════════════════════════════════════

def handle_slash_command(phone, text):
    cmd = text.strip().lower()

    if cmd in ["/", "/menu", "/start", "/help", "/kömək"]:
        send_buttons(phone,
            "🤖 *Garant AI* — Nə ilə kömək edə bilərəm?",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
        return True

    if cmd in ["/xidmetler", "/xidmət", "/qiymət", "/qiymətlər"]:
        send_whatsapp(phone, get_fast_reply_text("prices"))
        time.sleep(0.5)
        send_buttons(phone, "Müraciət etmək istərdinizmi?",
            [{"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
        return True

    if cmd in ["/müraciət", "/muraciet", "/qeydiyyat"]:
        send_buttons(phone, "📝 Müraciət üçün:",
            [{"id": "btn_qeydiyyat", "title": "📝 Müraciət et"}])
        return True

    if cmd in ["/əlaqə", "/elaqe", "/kontakt"]:
        send_whatsapp(phone, get_fast_reply_text("address"))
        return True

    return False


# ════════════════════════════════════════════════════════════════
# ADMIN BİLDİRİŞ
# ════════════════════════════════════════════════════════════════

def notify_owner(phone, ad, xidmet, customer):
    if not OWNER_PHONE:
        return
    segment, emoji = get_segment(customer)
    cnt  = customer.get("muraciet_sayi", 1) if customer else 1
    stxt = {"vip":   f"👑 VIP ({cnt}-ci müraciət)",
            "sadiq": f"⭐ SADİQ ({cnt}-ci müraciət)",
            "yeni":  "🆕 YENİ MÜŞTƏRİ"}.get(segment, "")
    now = baku_now()
    send_whatsapp(OWNER_PHONE,
        f"🔔 *YENİ MÜRACİƏT — Garant Consulting*\n"
        f"{'─'*30}\n"
        f"👤 Ad: {ad}\n"
        f"📞 Tel: +{phone}\n"
        f"💼 Xidmət: {xidmet}\n"
        f"🏷️ {stxt}\n"
        f"⏰ {now.strftime('%d.%m.%Y %H:%M')} (Bakı)\n"
        f"{'─'*30}\n"
        f"💡 Ən qısa zamanda zəng edin!")


# ════════════════════════════════════════════════════════════════
# 🧠 YÜKSƏK SƏVİYYƏLİ AI CAVAB
# ════════════════════════════════════════════════════════════════

def get_ai_response(phone, user_message):
    if phone not in conversations:
        conversations[phone] = []

    customer       = get_customer(phone)
    segment, emoji = get_segment(customer)

    # Müştəri konteksti
    meta = f"\n\n[SİSTEM KONTEKST]\nMÜŞTƏRİ: +{phone}"
    if customer and customer.get("ad"):
        meta += f"\nAD: {customer['ad']} (HƏMİŞƏ adı ilə müraciət et)"
    meta += f"\nSEQMENT: {segment} {emoji}"
    if customer and customer.get("muraciet_sayi", 0) > 1:
        meta += f"\nMÜRACİƏT SAYI: {customer['muraciet_sayi']}"
    now = baku_now()
    meta += f"\nBAKI SAATI: {now.strftime('%H:%M, %d.%m.%Y')}"

    conversations[phone].append({"role": "user", "content": user_message})
    # Kontekst pəncərəsi — son 30 mesaj
    if len(conversations[phone]) > 30:
        conversations[phone] = conversations[phone][-30:]

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # Ən güclü model
            max_tokens=800,
            temperature=0.7,
            messages=[
                {"role": "system", "content": SISTEM_PROMPTU + meta},
                *conversations[phone]
            ]
        )
        ai_text = response.choices[0].message.content
        conversations[phone].append({"role": "assistant", "content": ai_text})

        stage = "müraciət etdi" if "QEYDİYYAT:" in ai_text else "sual verdi"
        save_customer(phone, stage=stage)
        return ai_text

    except Exception as e:
        err = str(e)
        print(f"AI xətası: {err}")
        # Rate limit → kiçik modelə fallback
        if "rate_limit_exceeded" in err or "429" in err:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    max_tokens=500,
                    temperature=0.7,
                    messages=[
                        {"role": "system", "content": SISTEM_PROMPTU + meta},
                        *conversations[phone][-10:]
                    ]
                )
                ai_text = response.choices[0].message.content
                conversations[phone].append({"role": "assistant", "content": ai_text})
                return ai_text
            except:
                return RATE_LIMIT_MESAJ
        return "😅 Kiçik texniki problem! Bir az sonra yenidən cəhd edin. 🔧"


# ════════════════════════════════════════════════════════════════
# QEYDİYYAT İŞLƏMƏ
# ════════════════════════════════════════════════════════════════

def process_registration(ai_text, phone):
    if "QEYDİYYAT:" in ai_text:
        try:
            details = ai_text.split("QEYDİYYAT:")[1].strip().split("|")
            ad      = details[0].strip() if len(details) > 0 else ""
            xidmet  = details[2].strip() if len(details) > 2 else ""
            save_customer(phone, ad=ad, xidmet=xidmet, stage="müraciət etdi")
            save_muraciet(phone, ad, xidmet)
            customer = get_customer(phone)
            notify_owner(phone, ad, xidmet, customer)
            # Paylaşım təşviqi
            time.sleep(1)
            send_whatsapp(phone,
                f"🎁 *Xüsusi təklifimiz:*\n\n"
                f"Bu nömrəni sahibkar dostunuza göndərin — "
                f"onlara *ilk konsultasiya pulsuzdur!* 🤝\n\n"
                f"Birlikdə Azərbaycan biznesini gücləndiriririk! 💪🇦🇿")
        except Exception as e:
            print(f"Qeydiyyat xətası: {e}")


# ════════════════════════════════════════════════════════════════
# XOŞ GƏLDİN
# ════════════════════════════════════════════════════════════════

def send_welcome(phone):
    customer       = get_customer(phone)
    greeting       = get_time_greeting()
    segment, emoji = get_segment(customer)

    if customer and customer.get("ad"):
        ad = customer["ad"]
        if segment == "vip":
            msg = f"👑 *{greeting}, əziz {ad}!*\nƏn dəyərli dostlarımızdansınız! Ayşən xanım sizi şəxsən qarşılamaq istəyir! 🌟"
        elif segment == "sadiq":
            msg = f"⭐ *{greeting}, hörmətli {ad}!*\nYenidən qapımızı döydünüz — biz də sevirik! Ailəmizin bir parçasısınız. 🏠"
        else:
            msg = f"🤖 *{greeting}, {ad}!*\nYenidən görməkdən çox məmnun oldum! Nə ilə kömək edə bilərəm? 😊"
        send_whatsapp(phone, msg)
        time.sleep(1)
        send_buttons(phone, "Seçiminizi edin:",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
    else:
        send_whatsapp(phone,
            f"🤖 *{greeting}! Garant AI-ya xoş gəldiniz!*\n\n"
            f"Mən *Garant Consulting*-in AI assistentiyəm.\n"
            f"Mühasibat, vergi, biznes və *istənilən* başqa mövzuda kömək edə bilərəm! 💡\n\n"
            f"Sadəcə soruşun — cavabsız qalmayacaqsınız! 🚀")
        time.sleep(1)
        send_whatsapp(phone,
            "🏢 *Garant Consulting:*\n"
            "• 👤 Rəhbər: Ayşən Salamova\n"
            "• ⏰ İş saatları: B.E–Cümə, 10:00–18:00\n"
            "• 💼 Mühasibat, vergi, audit xidmətləri\n"
            "• 🤖 24/7 AI dəstək")
        time.sleep(1)
        send_buttons(phone, "Necə kömək edə bilərəm? 👇",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
        time.sleep(0.5)
        send_whatsapp(phone,
            "💡 *İpucu:* */* yazaraq menyunu aça bilərsiniz.\n"
            "Mühasibatdan tutmuş istənilən mövzuda sual verə bilərsiniz! 🧠")
    save_customer(phone)


# ════════════════════════════════════════════════════════════════
# WEBHOOK
# ════════════════════════════════════════════════════════════════

@app.route("/webhook", methods=["GET"])
def verify():
    mode, token, challenge = (request.args.get("hub.mode"),
                               request.args.get("hub.verify_token"),
                               request.args.get("hub.challenge"))
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        entry    = data["entry"][0]["changes"][0]["value"]
        messages = entry.get("messages", [])
        if not messages:
            return jsonify({"status": "ok"})

        msg    = messages[0]
        phone  = msg["from"]
        mtype  = msg["type"]
        msg_id = msg.get("id", "")

        # ── Təkrar mesaj filtri ─────────────────────────────────
        if msg_id and msg_id in processed_messages:
            return jsonify({"status": "ok"})
        if msg_id:
            processed_messages.add(msg_id)
            if len(processed_messages) > MAX_PROCESSED:
                for item in list(processed_messages)[:200]:
                    processed_messages.discard(item)

        # ── Mesaj tipi ──────────────────────────────────────────
        if mtype == "text":
            user_text = msg["text"]["body"]

        elif mtype == "interactive" and msg["interactive"]["type"] == "button_reply":
            btn_map = {
                "btn_xidmetler": "Xidmətləriniz və qiymətlər haqqında məlumat verin",
                "btn_qeydiyyat": "Müraciət etmək istəyirəm",
                "btn_elaqe":     "Əlaqə məlumatlarınızı verin",
            }
            user_text = btn_map.get(msg["interactive"]["button_reply"]["id"], "")

        elif mtype == "audio":
            media_id    = msg["audio"]["id"]
            mime_type   = msg["audio"].get("mime_type", "audio/ogg")
            audio_bytes = download_whatsapp_audio(media_id)
            if not audio_bytes:
                send_whatsapp(phone, "😔 Səsli mesajı eşidə bilmədim. Yazılı göndərin!")
                return jsonify({"status": "ok"})
            user_text = transcribe_audio(audio_bytes, mime_type)
            if not user_text:
                send_whatsapp(phone, "😅 Səsinizi anlamadım. Yazılı cəhd edin!")
                return jsonify({"status": "ok"})
            send_whatsapp(phone, f"🎤 _Eşitdim: {user_text}_")
            time.sleep(0.5)

        else:
            return jsonify({"status": "ok"})

        # ── İlk dəfə yazır ──────────────────────────────────────
        if phone not in conversations:
            conversations[phone] = []
            if phone not in welcomed_phones:
                welcomed_phones.add(phone)
                send_welcome(phone)
                if user_text and user_text.startswith("/"):
                    time.sleep(0.5)
                    handle_slash_command(phone, user_text)
                return jsonify({"status": "ok"})

        # ── Slash komanda ────────────────────────────────────────
        if user_text and user_text.startswith("/"):
            if handle_slash_command(phone, user_text):
                return jsonify({"status": "ok"})

        # ── Sürətli cavab ────────────────────────────────────────
        fast_key = check_fast_reply(user_text)
        if fast_key:
            fast_text = get_fast_reply_text(fast_key)
            if fast_text:
                send_whatsapp(phone, fast_text)
                if fast_key == "prices":
                    time.sleep(0.5)
                    send_buttons(phone, "Müraciət etmək istərdinizmi?",
                        [{"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
                         {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
                save_customer(phone, stage="sual verdi")
                return jsonify({"status": "ok"})

        # ── AI cavabı — həmişə işləyir ───────────────────────────
        ai_reply = get_ai_response(phone, user_text)
        process_registration(ai_reply, phone)
        send_whatsapp(phone, ai_reply)

    except (KeyError, IndexError) as e:
        print(f"Parse xətası: {e}")
    except Exception as e:
        print(f"Ümumi xəta: {e}")

    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ════════════════════════════════════════════════════════════════

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="az">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Garant Consulting — Admin</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #1a202c; }
.header { background: linear-gradient(135deg, #1a365d, #2b6cb0); color: white;
          padding: 20px 30px; display:flex; justify-content:space-between; align-items:center; }
.header h1 { font-size: 22px; }
.header p  { font-size: 12px; opacity:.8; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
         gap:16px; padding:24px; }
.stat-card { background:white; border-radius:12px; padding:20px;
             box-shadow:0 2px 8px rgba(0,0,0,.08); text-align:center; }
.stat-n { font-size:36px; font-weight:700; color:#2b6cb0; }
.stat-l { font-size:12px; color:#718096; margin-top:4px; }
.section { padding:0 24px 24px; }
.section h2 { font-size:16px; font-weight:700; margin-bottom:14px; color:#2d3748; }
table { width:100%; background:white; border-radius:12px; overflow:hidden;
        box-shadow:0 2px 8px rgba(0,0,0,.08); border-collapse:collapse; }
th { background:#2b6cb0; color:white; padding:12px 16px; text-align:left;
     font-size:12px; font-weight:600; }
td { padding:12px 16px; font-size:13px; border-bottom:1px solid #edf2f7; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:#f7fafc; }
.badge { display:inline-block; padding:3px 10px; border-radius:20px;
         font-size:11px; font-weight:600; }
.badge.yeni   { background:#c6f6d5; color:#276749; }
.badge.elanib { background:#bee3f8; color:#2c5282; }
.badge.vip    { background:#fef3c7; color:#92400e; }
.badge.sadiq  { background:#e0e7ff; color:#3730a3; }
.refresh { background:#2b6cb0; color:white; border:none; padding:8px 18px;
           border-radius:8px; cursor:pointer; font-size:13px; }
.bar { height:20px; background:#2b6cb0; border-radius:4px; display:inline-block; min-width:4px; }
</style>
</head>
<body>
<div class="header">
  <div><h1>🏢 Garant Consulting</h1><p>🤖 Garant AI — Admin Panel</p></div>
  <button class="refresh" onclick="location.reload()">🔄 Yenilə</button>
</div>

<div class="stats">
  <div class="stat-card"><div class="stat-n">{{ cem_muraciet }}</div><div class="stat-l">Ümumi Müraciət</div></div>
  <div class="stat-card"><div class="stat-n">{{ yeni_muraciet }}</div><div class="stat-l">🆕 Yeni</div></div>
  <div class="stat-card"><div class="stat-n">{{ cem_musteri }}</div><div class="stat-l">Müştəri</div></div>
  <div class="stat-card"><div class="stat-n">{{ bugun }}</div><div class="stat-l">Bu gün</div></div>
  <div class="stat-card"><div class="stat-n">{{ vip_sayi }}</div><div class="stat-l">👑 VIP</div></div>
  <div class="stat-card"><div class="stat-n">{{ sadiq_sayi }}</div><div class="stat-l">⭐ Sadiq</div></div>
</div>

<div class="section">
  <h2>📊 Funnel</h2>
  <table>
    <tr><th>Mərhələ</th><th>Say</th><th>Vizual</th></tr>
    {% for s, c in funnel.items() %}
    <tr>
      <td>{{ s }}</td><td><b>{{ c }}</b></td>
      <td><div class="bar" style="width:{{ [c*20,300]|min }}px"></div></td>
    </tr>
    {% endfor %}
  </table>
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
    <tr><th>#</th><th>Ad</th><th>Telefon</th><th>Xidmət</th><th>Mərhələ</th><th>Say</th><th>Seqment</th></tr>
    {% for m in musteriler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ m.ad or '—' }}</td>
      <td>+{{ m.telefon }}</td>
      <td>{{ m.xidmet or '—' }}</td>
      <td>{{ m.stage or '—' }}</td>
      <td>{{ m.muraciet_sayi }}</td>
      <td>
        {% if m.muraciet_sayi >= 5 %}<span class="badge vip">👑 VIP</span>
        {% elif m.muraciet_sayi >= 3 %}<span class="badge sadiq">⭐ Sadiq</span>
        {% else %}<span class="badge yeni">🆕 Yeni</span>{% endif %}
      </td>
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
        return "<h2>❌ Giriş qadağandır.</h2>", 403
    try:
        muracietler = supabase.table("muracietler").select("*").order("tarix", desc=True).limit(50).execute().data
        musteriler  = supabase.table("musteriler").select("*").order("son_muraciet", desc=True).execute().data
        bugun_str   = str(date.today())
        bugun       = sum(1 for m in muracietler if m.get("tarix","").startswith(bugun_str))
        yeni        = sum(1 for m in muracietler if m.get("status") == "yeni")
        vip_sayi    = sum(1 for m in musteriler  if m.get("muraciet_sayi",0) >= 5)
        sadiq_sayi  = sum(1 for m in musteriler  if 3 <= m.get("muraciet_sayi",0) < 5)
        funnel      = {"maraqlandı": 0, "sual verdi": 0, "müraciət etdi": 0}
        for m in musteriler:
            s = m.get("stage", "maraqlandı")
            if s in funnel: funnel[s] += 1
        return render_template_string(ADMIN_HTML,
            muracietler=muracietler, musteriler=musteriler,
            cem_muraciet=len(muracietler), yeni_muraciet=yeni,
            cem_musteri=len(musteriler), bugun=bugun,
            vip_sayi=vip_sayi, sadiq_sayi=sadiq_sayi, funnel=funnel)
    except Exception as e:
        return f"<h3>Xəta: {e}</h3>", 500

@app.route("/")
def home():
    return "🤖 Garant AI — Garant Consulting WhatsApp Bot işləyir! ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
