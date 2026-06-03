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

# ── Təkrar mesajların qarşısını almaq üçün ──────────────────────
processed_messages = set()
MAX_PROCESSED = 1000

# ── Tez-tez soruşulan sözlər — AI-sız ani cavab ────────────────
FAST_REPLIES = {
    ("qiymət","qiymətlər","nəqədər","neçəyə","pul","məbləğ"): "prices",
    ("saat","vaxt","nə vaxt","iş saatı","açıqsınız","bağlısınız"): "hours",
    ("harada","ünvan","adres","ofis","məkan","yer"): "address",
    ("kimsiniz","şirkət","garant","haqqında","nəsiniz"): "about",
}

# ── Rate limit şablon cavabı ────────────────────────────────────
RATE_LIMIT_MESAJ = (
    "😅 Vay, bu saat nə qədər aktiv müştərilərimiz var!\n\n"
    "Hal-hazırda çox sayda sorğu daxil olur və sistemimiz bir az nəfəs almaq istəyir. "
    "Zəhmət olmasa 10-15 dəqiqə sonra yenidən yazın. 🙏\n\n"
    "Təcili hallarda:\n"
    "📞 İş saatlarımız: B.E – Cümə, 10:00 – 18:00\n\n"
    "Səbriniz üçün təşəkkür edirik! 🌟"
)

SISTEM_PROMPTU = """Sən Garant Consulting şirkətinin WhatsApp köməkçisisən. 
Üslubun: pozitiv, mehriban, komik (amma nəzakətli), müştəri yönümlü və peşəkar.
Hər cavabda müştərini xüsusi hiss etdir. Emojidən yerli-yerində istifadə et.
Cavablarını qısa saxla — maksimum 3-4 cümlə.

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
- Həmişə pozitiv və enerji dolu ol
- Müştərinin adını bildikdə mütləq adı ilə müraciət et
- Əvvəlki müraciəti varsa: "Yenidən qapımızı döydünüz, çox şad olduq!" kimi isti qarşıla
- Müştəri müraciət etmək istədikdə YALNIZ adını soruş
- Ad alındıqdan sonra hansı xidməti istədiyini soruş
- Bütün məlumatlar tamamlandıqda MÜTLƏQ bu formatda yaz:
  ✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]
- Qeydiyyatdan sonra: "🎉 Hörmətli [ad], müraciətiniz qəbul edildi! Ən qısa zamanda mütəxəssislərimiz sizinlə əlaqə saxlayacaq. Garant Consulting olaraq sizə ən keyfiyyətli xidməti təqdim etməyə hazırıq! 🙏"

MÜŞTƏRİ SEQMENTLƏRİNƏ GÖRƏ YANAŞMA:
- Yeni müştəri: xüsusilə isti qarşıla, ətraflı izah et
- Sadiq müştəri (3+ müraciət): "Siz artıq ailəmizin bir parçasısınız!" de
- VIP (5+ müraciət): "Ən dəyərli müştərilərimizdənsiniz!" de, xüsusi diqqət göstər
"""

conversations = {}


# ════════════════════════════════════════════════════════════════
# YARDIMÇI — SAAT VƏ GÜN
# ════════════════════════════════════════════════════════════════

def baku_now():
    """Bakı vaxtını qaytarır (UTC+4)"""
    utc = datetime.utcnow()
    return utc.replace(hour=(utc.hour + 4) % 24)


def is_work_hours():
    """İş saatıdırmı? B.E-Cümə 10:00-18:00"""
    now = baku_now()
    if now.weekday() >= 5:  # Şənbə, Bazar
        return False
    return 10 <= now.hour < 18


def get_time_greeting():
    """Saata görə salamlama"""
    h = baku_now().hour
    if 5 <= h < 12:  return "Sabahınız xeyir"
    if 12 <= h < 17: return "Günortanız xeyir"
    if 17 <= h < 21: return "Axşamınız xeyir"
    return "Gecəniz xeyir"


def get_off_hours_message(customer_name=None):
    """İş saatı xaricində komik və pozitiv mesaj"""
    now = baku_now()
    h   = now.hour
    name_part = f"hörmətli *{customer_name}*" if customer_name else "hörmətli dostumuz"

    # Neçə saat sonra iş başlayır
    if h < 10:
        hours_left = 10 - h
        time_msg = f"Cəmi *{hours_left} saat* sonra iş başlayır! ⏰"
    else:
        # Növbəti iş günü
        weekday = now.weekday()
        if weekday == 4:   # Cümə axşamı
            time_msg = "Bazar ertəsi səhər saat 10:00-da ilk işimiz sizinlə əlaqə saxlamaq olacaq! 📅"
        elif weekday >= 5: # Həftəsonu
            days = 7 - weekday
            time_msg = f"*{days} gün* sonra, Bazar ertəsi saat 10:00-da sizə zəng edəcəyik! 📅"
        else:
            time_msg = "Sabah səhər saat 10:00-da ilk işimiz sizinlə əlaqə saxlamaq olacaq! 🌅"

    if h >= 22 or h < 1:
        komik = (
            f"🌙 Ay {name_part}, bu saat işçilərimiz artıq evlərindədir — "
            f"bəziləri yəqin ki xoruldayır da! 😄\n\n"
            f"Amma narahat olmayın, sabah açılan kimi müraciətiniz masalarında ilk sırada olacaq. "
            f"{time_msg}\n\n"
            f"İndi bir az dincəlin, xeyirxah işlər gündüz daha yaxşı olur! 😴💼"
        )
    elif h >= 18:
        komik = (
            f"🌆 Salam, {name_part}! İşçilərimiz bu saat artıq "
            f"evə çatıb, ailələri ilə vaxt keçirirlər — haqları da var! 😊\n\n"
            f"Müraciətiniz qeydə alındı. {time_msg}\n\n"
            f"Çox gözlətməyəcəyik, söz! 🤝"
        )
    else:  # Həftəsonu
        komik = (
            f"🏖️ Salam, {name_part}! Bu gün həftəsonudur — "
            f"komandamız yaxşı qazanılmış istirahətini keçirir! 😄\n\n"
            f"Müraciətiniz qeydə alındı. {time_msg}\n\n"
            f"Həftəsonu üçün planlarınız uğurlu olsun! 🌟"
        )
    return komik


# ════════════════════════════════════════════════════════════════
# WHATSAPP GÖNDƏRMƏ
# ════════════════════════════════════════════════════════════════

def send_whatsapp(to, text):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"send_whatsapp xətası: {e}")


def send_buttons(to, body_text, buttons):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    btn_list = [{"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}} for b in buttons[:3]]
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body_text}, "action": {"buttons": btn_list}}
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
        url_req = requests.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=10)
        media_url = url_req.json().get("url")
        if not media_url:
            return None
        audio_resp = requests.get(media_url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, timeout=30)
        return audio_resp.content
    except Exception as e:
        print(f"Audio yükləmə xətası: {e}")
        return None


def transcribe_audio(audio_bytes, mime_type="audio/ogg"):
    try:
        import io
        ext_map = {"audio/ogg":"ogg","audio/mpeg":"mp3",
                   "audio/mp4":"mp4","audio/wav":"wav","audio/webm":"webm"}
        ext = ext_map.get(mime_type, "ogg")
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"voice.{ext}"
        transcription = groq_client.audio.transcriptions.create(
            model="whisper-large-v3-turbo", file=audio_file,
            language="az", response_format="text")
        return transcription.strip() if transcription else None
    except Exception as e:
        print(f"Transkripsiya xətası: {e}")
        return None


# ════════════════════════════════════════════════════════════════
# SUPABASE
# ════════════════════════════════════════════════════════════════

def get_customer(phone):
    try:
        result = supabase.table("musteriler").select("*").eq("telefon", phone).execute()
        return result.data[0] if result.data else None
    except:
        return None


def save_customer(phone, ad=None, xidmet=None, stage=None):
    try:
        existing = get_customer(phone)
        if existing:
            upd = {"son_muraciet": "now()", "muraciet_sayi": existing["muraciet_sayi"] + 1}
            if ad:    upd["ad"]    = ad
            if xidmet: upd["xidmet"] = xidmet
            if stage:  upd["stage"]  = stage
            supabase.table("musteriler").update(upd).eq("telefon", phone).execute()
        else:
            row = {"telefon": phone, "ad": ad, "xidmet": xidmet, "stage": stage or "maraqlandı"}
            supabase.table("musteriler").insert(row).execute()
    except:
        pass


def save_muraciet(phone, ad, xidmet):
    try:
        supabase.table("muracietler").insert(
            {"telefon": phone, "ad": ad, "xidmet": xidmet, "status": "yeni"}).execute()
    except:
        pass


def get_segment(customer):
    """Müştəri seqmenti"""
    if not customer:
        return "yeni", "🆕"
    cnt = customer.get("muraciet_sayi", 1)
    if cnt >= 5:   return "vip",    "👑"
    if cnt >= 3:   return "sadiq",  "⭐"
    return "yeni", "🆕"


# ════════════════════════════════════════════════════════════════
# SÜRƏTLİ CAVABLAR — AI-sız
# ════════════════════════════════════════════════════════════════

def check_fast_reply(text):
    """Tez-tez soruşulan suallar üçün ani cavab"""
    t = text.lower().strip()
    for keywords, reply_key in FAST_REPLIES.items():
        if any(k in t for k in keywords):
            return reply_key
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
            "💡 Dəqiq qiymət üçün müraciət edin — fərdi təklif hazırlayaq!"
        ),
        "hours": (
            "🕐 *İş Saatlarımız:*\n\n"
            "📅 Bazar ertəsi – Cümə\n"
            "⏰ Saat 10:00 – 18:00\n\n"
            f"Hal-hazırda {'✅ *açıqıq*, sizə kömək etməyə hazırıq!' if is_work_hours() else '🌙 *bağlıyıq*, amma sabah ilk işimiz sizinlə olacaq!'}"
        ),
        "address": (
            "📍 *Əlaqə və Ünvan:*\n\n"
            "🏢 Garant Consulting\n"
            "👤 Rəhbər: Ayşən Salamova\n"
            "💬 Bu söhbət vasitəsilə əlaqə saxlaya bilərsiniz\n\n"
            "Sizi şəxsən qarşılamaqdan məmnun olarıq! 🤝"
        ),
        "about": (
            "🏢 *Garant Consulting haqqında:*\n\n"
            "Biz peşəkar mühasibat və maliyyə xidmətləri şirkətiyik.\n"
            "👥 Təsisçilər: Balakişi Qurbanov & Ayşən Salamova\n"
            "🎯 Missiyamız: Biznesinizi rəqəmlərdən azad etmək!\n"
            "💪 Hər ölçüdə şirkətə xidmət göstəririk\n\n"
            "Suallarınız üçün buradayıq! 😊"
        ),
    }
    return replies.get(key, "")


# ════════════════════════════════════════════════════════════════
# / SLASH KOMANDOLARı
# ════════════════════════════════════════════════════════════════

def handle_slash_command(phone, text):
    cmd = text.strip().lower()

    if cmd in ["/", "/menu", "/start", "/help", "/kömək"]:
        send_buttons(phone,
            "📋 *Əsas Menyu*\nAşağıdakı seçimlərdən birini edin:",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
        return True

    if cmd in ["/xidmetler", "/xidmət", "/qiymət", "/qiymətlər"]:
        send_whatsapp(phone, get_fast_reply_text("prices"))
        time.sleep(0.5)
        send_buttons(phone, "Müraciət etmək istərdinizmi? 👇",
            [{"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
        return True

    if cmd in ["/müraciət", "/muraciet", "/qeydiyyat"]:
        send_buttons(phone, "📝 Müraciət üçün aşağıdakı düyməyə basın:",
            [{"id": "btn_qeydiyyat", "title": "📝 Müraciət et"}])
        return True

    if cmd in ["/əlaqə", "/elaqe", "/kontakt"]:
        send_whatsapp(phone, get_fast_reply_text("address"))
        return True

    if cmd in ["/saat", "/vaxt", "/iş saatı"]:
        send_whatsapp(phone, get_fast_reply_text("hours"))
        return True

    return False


# ════════════════════════════════════════════════════════════════
# ADMIN BİLDİRİŞ — ZƏNGİN FORMAT
# ════════════════════════════════════════════════════════════════

def notify_owner(phone, ad, xidmet, customer):
    if not OWNER_PHONE:
        return
    segment, emoji = get_segment(customer)
    cnt = customer.get("muraciet_sayi", 1) if customer else 1
    segment_text = {
        "vip":   f"👑 VIP MÜŞTƏRİ ({cnt}-ci müraciət)",
        "sadiq": f"⭐ SADİQ MÜŞTƏRİ ({cnt}-ci müraciət)",
        "yeni":  "🆕 YENİ MÜŞTƏRİ"
    }.get(segment, "")
    now = baku_now()
    send_whatsapp(OWNER_PHONE,
        f"🔔 *YENİ MÜRACİƏT — Garant Consulting*\n"
        f"{'─'*30}\n"
        f"👤 Ad: {ad}\n"
        f"📞 Tel: +{phone}\n"
        f"💼 Xidmət: {xidmet}\n"
        f"🏷️ {segment_text}\n"
        f"⏰ {now.strftime('%d.%m.%Y %H:%M')} (Bakı)\n"
        f"{'─'*30}\n"
        f"💡 Müştəriyə ən qısa zamanda zəng edin!")


# ════════════════════════════════════════════════════════════════
# AI CAVAB — rate limit + seqment qoruması ilə
# ════════════════════════════════════════════════════════════════

def get_ai_response(phone, user_message):
    if phone not in conversations:
        conversations[phone] = []

    customer = get_customer(phone)
    segment, emoji = get_segment(customer)

    musteri_melumat = f"\nMÜŞTƏRİ TELEFONU: +{phone}"
    if customer and customer.get("ad"):
        musteri_melumat += f"\nMÜŞTƏRİNİN ADI: {customer['ad']} (mütləq adı ilə müraciət et)"
    musteri_melumat += f"\nMÜŞTƏRİ SEQMENTİ: {segment} {emoji}"
    if customer and customer.get("muraciet_sayi", 0) > 1:
        musteri_melumat += f"\nMÜRACİƏT SAYI: {customer['muraciet_sayi']} dəfə (sadiq müştəridir!)"

    conversations[phone].append({"role": "user", "content": user_message})
    if len(conversations[phone]) > 20:
        conversations[phone] = conversations[phone][-20:]

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=400,
            temperature=0.8,
            messages=[
                {"role": "system", "content": SISTEM_PROMPTU + musteri_melumat},
                *conversations[phone]
            ]
        )
        ai_text = response.choices[0].message.content
        conversations[phone].append({"role": "assistant", "content": ai_text})

        # Stage yenilə
        stage = "sual verdi"
        if "QEYDİYYAT:" in ai_text:
            stage = "müraciət etdi"
        save_customer(phone, stage=stage)

        return ai_text

    except Exception as e:
        err = str(e)
        print(f"Groq xətası: {err}")
        if "rate_limit_exceeded" in err or "429" in err:
            return RATE_LIMIT_MESAJ
        return "😅 Kiçik bir texniki nasazlıq baş verdi. Zəhmət olmasa bir az sonra yenidən cəhd edin! 🔧"


# ════════════════════════════════════════════════════════════════
# QEYDİYYAT İŞLƏMƏ
# ════════════════════════════════════════════════════════════════

def process_registration(ai_text, phone):
    if "QEYDİYYAT:" in ai_text:
        try:
            details = ai_text.split("QEYDİYYAT:")[1].strip().split("|")
            ad     = details[0].strip() if len(details) > 0 else ""
            xidmet = details[2].strip() if len(details) > 2 else ""
            save_customer(phone, ad=ad, xidmet=xidmet, stage="müraciət etdi")
            save_muraciet(phone, ad, xidmet)
            customer = get_customer(phone)
            notify_owner(phone, ad, xidmet, customer)
        except:
            pass


# ════════════════════════════════════════════════════════════════
# XOŞ GƏLDİN
# ════════════════════════════════════════════════════════════════

def send_welcome(phone):
    customer  = get_customer(phone)
    greeting  = get_time_greeting()
    segment, emoji = get_segment(customer)
    work      = is_work_hours()

    if customer and customer.get("ad"):
        ad  = customer["ad"]
        cnt = customer.get("muraciet_sayi", 1)

        if segment == "vip":
            intro = (f"{greeting}, əziz *{ad}*! 👑\n"
                     f"Ən dəyərli müştərilərimizdənsiniz — {cnt}-ci müraciətiniz! "
                     f"Sizi görmək həmişə xüsusi sevinc verir! 🌟")
        elif segment == "sadiq":
            intro = (f"{greeting}, hörmətli *{ad}*! ⭐\n"
                     f"Yenidən qapımızı döydünüz — {cnt}-ci dəfə! "
                     f"Artıq ailəmizin bir parçasısınız! 🏠")
        else:
            intro = (f"{greeting}, hörmətli *{ad}*! 👋\n"
                     f"Sizi yenidən görməkdən çox məmnun olduq! "
                     f"Bu sizin {cnt + 1}-ci müraciətinizdir. 🌟")

        send_whatsapp(phone, intro)
        time.sleep(1)

        if not work:
            send_whatsapp(phone, get_off_hours_message(ad))
            save_customer(phone)
            return

        send_buttons(phone, "Sizə bu dəfə necə kömək edə bilərik? 👇",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
    else:
        send_whatsapp(phone,
            f"{greeting}! 👋 *Garant Consulting*-ə xoş gəldiniz!\n"
            f"Peşəkar mühasibat xidmətləri üçün doğru yerə müraciət etdiniz. 💼\n"
            f"Biz rəqəmləri sevənlər üçün buradayıq! 😄")
        time.sleep(1)
        send_whatsapp(phone,
            "🏢 *Garant Consulting:*\n"
            "• 👤 Rəhbər: Ayşən Salamova\n"
            "• ⏰ İş saatları: B.E – Cümə, 10:00 – 18:00\n"
            "• 💼 Peşəkar mühasibat & vergi xidmətləri\n"
            "• 🏆 Hər ölçüdə şirkətə xidmət")
        time.sleep(1)

        if not work:
            send_whatsapp(phone, get_off_hours_message())
            save_customer(phone)
            return

        send_buttons(phone, "Sizə necə kömək edə bilərik? 👇",
            [{"id": "btn_xidmetler", "title": "📊 Xidmətlərimiz"},
             {"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
        time.sleep(0.5)
        send_whatsapp(phone, "💡 *İpucu:* */* yazaraq əsas menyunu istənilən vaxt aça bilərsiniz!")

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

        # ── Təkrar mesajların qarşısını al ──────────────────────
        if msg_id and msg_id in processed_messages:
            print(f"Təkrar mesaj atlandı: {msg_id}")
            return jsonify({"status": "ok"})
        if msg_id:
            processed_messages.add(msg_id)
            if len(processed_messages) > MAX_PROCESSED:
                to_remove = list(processed_messages)[:200]
                for item in to_remove:
                    processed_messages.discard(item)

        # ── Mesaj tipi ──────────────────────────────────────────
        if mtype == "text":
            user_text = msg["text"]["body"]

        elif mtype == "interactive" and msg["interactive"]["type"] == "button_reply":
            btn_map = {
                "btn_xidmetler": "Xidmətləriniz və qiymətlər haqqında ətraflı məlumat verin",
                "btn_qeydiyyat": "Müraciət etmək istəyirəm",
                "btn_elaqe":     "Əlaqə məlumatlarınızı verin",
            }
            user_text = btn_map.get(msg["interactive"]["button_reply"]["id"], "")

        elif mtype == "audio":
            media_id    = msg["audio"]["id"]
            mime_type   = msg["audio"].get("mime_type", "audio/ogg")
            audio_bytes = download_whatsapp_audio(media_id)
            if not audio_bytes:
                send_whatsapp(phone, "😔 Səsli mesajınızı eşidə bilmədim. Yazılı göndərin, zəhmət olmasa!")
                return jsonify({"status": "ok"})
            user_text = transcribe_audio(audio_bytes, mime_type)
            if not user_text:
                send_whatsapp(phone, "😅 Səsinizi anlamadım — yəqin arxa fon səs-küylü idi! Yazılı cəhd edin.")
                return jsonify({"status": "ok"})
            send_whatsapp(phone, f"🎤 _Eşitdim: {user_text}_")
            time.sleep(0.5)

        else:
            return jsonify({"status": "ok"})

        # ── İlk dəfə yazır ──────────────────────────────────────
        if phone not in conversations:
            send_welcome(phone)
            conversations[phone] = []
            if user_text and user_text.startswith("/"):
                time.sleep(0.5)
                handle_slash_command(phone, user_text)
            return jsonify({"status": "ok"})

        # ── İş saatı xaricindədirsə ─────────────────────────────
        if not is_work_hours():
            customer = get_customer(phone)
            ad = customer.get("ad") if customer else None
            send_whatsapp(phone, get_off_hours_message(ad))
            return jsonify({"status": "ok"})

        # ── Slash komanda ────────────────────────────────────────
        if user_text and user_text.startswith("/"):
            if handle_slash_command(phone, user_text):
                return jsonify({"status": "ok"})

        # ── Sürətli cavab yoxla ──────────────────────────────────
        fast_key = check_fast_reply(user_text)
        if fast_key:
            fast_text = get_fast_reply_text(fast_key)
            if fast_text:
                send_whatsapp(phone, fast_text)
                if fast_key == "prices":
                    time.sleep(0.5)
                    send_buttons(phone, "Müraciət etmək istərdinizmi? 👇",
                        [{"id": "btn_qeydiyyat", "title": "📝 Müraciət et"},
                         {"id": "btn_elaqe",     "title": "📞 Əlaqə"}])
                save_customer(phone, stage="sual verdi")
                return jsonify({"status": "ok"})

        # ── AI cavabı ────────────────────────────────────────────
        ai_reply = get_ai_response(phone, user_text)
        process_registration(ai_reply, phone)
        send_whatsapp(phone, ai_reply)

    except (KeyError, IndexError) as e:
        print(f"Webhook parse xətası: {e}")
    except Exception as e:
        print(f"Webhook ümumi xəta: {e}")

    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ════════════════════════════════════════════════════════════════

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
.header p  { font-size: 12px; opacity: 0.8; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; padding: 24px; }
.stat-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align:center; }
.stat-n  { font-size: 36px; font-weight: 700; color: #2b6cb0; }
.stat-l  { font-size: 12px; color: #718096; margin-top: 4px; }
.section { padding: 0 24px 24px; }
.section h2 { font-size: 16px; font-weight: 700; margin-bottom: 14px; color: #2d3748; }
table { width: 100%; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-collapse: collapse; }
th { background: #2b6cb0; color: white; padding: 12px 16px; text-align: left; font-size: 12px; font-weight: 600; }
td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #edf2f7; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f7fafc; }
.badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:600; }
.badge.yeni     { background:#c6f6d5; color:#276749; }
.badge.elanib   { background:#bee3f8; color:#2c5282; }
.badge.vip      { background:#fef3c7; color:#92400e; }
.badge.sadiq    { background:#e0e7ff; color:#3730a3; }
.stage-maraqlandı  { color: #718096; }
.stage-sual\ verdi { color: #2b6cb0; }
.stage-müraciət\ etdi { color: #276749; font-weight:600; }
.refresh { background:#2b6cb0; color:white; border:none; padding:8px 18px; border-radius:8px; cursor:pointer; font-size:13px; }
</style>
</head>
<body>
<div class="header">
  <div><h1>🏢 Garant Consulting</h1><p>Admin İdarəetmə Paneli</p></div>
  <button class="refresh" onclick="location.reload()">🔄 Yenilə</button>
</div>

<div class="stats">
  <div class="stat-card"><div class="stat-n">{{ cem_muraciet }}</div><div class="stat-l">Ümumi Müraciət</div></div>
  <div class="stat-card"><div class="stat-n">{{ yeni_muraciet }}</div><div class="stat-l">Yeni Müraciət</div></div>
  <div class="stat-card"><div class="stat-n">{{ cem_musteri }}</div><div class="stat-l">Ümumi Müştəri</div></div>
  <div class="stat-card"><div class="stat-n">{{ bugun }}</div><div class="stat-l">Bu gün</div></div>
  <div class="stat-card"><div class="stat-n">{{ vip_sayi }}</div><div class="stat-l">👑 VIP Müştəri</div></div>
  <div class="stat-card"><div class="stat-n">{{ sadiq_sayi }}</div><div class="stat-l">⭐ Sadiq Müştəri</div></div>
</div>

<div class="section">
  <h2>📊 Müraciət Hunisi (Funnel)</h2>
  <table>
    <tr><th>Mərhələ</th><th>Müştəri sayı</th></tr>
    {% for s, c in funnel.items() %}
    <tr><td class="stage-{{ s }}">{{ s }}</td><td><b>{{ c }}</b></td></tr>
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
    <tr><th>#</th><th>Ad</th><th>Telefon</th><th>Son Xidmət</th><th>Mərhələ</th><th>Müraciət</th><th>Seqment</th></tr>
    {% for m in musteriler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ m.ad or '—' }}</td>
      <td>+{{ m.telefon }}</td>
      <td>{{ m.xidmet or '—' }}</td>
      <td><span class="stage-{{ m.stage or '' }}">{{ m.stage or '—' }}</span></td>
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
        return "<h2>❌ Giriş qadağandır. URL-ə ?pwd=şifrəniz əlavə edin.</h2>", 403
    try:
        muracietler = supabase.table("muracietler").select("*").order("tarix", desc=True).limit(50).execute().data
        musteriler  = supabase.table("musteriler").select("*").order("son_muraciet", desc=True).execute().data
        bugun_str   = str(date.today())
        bugun       = sum(1 for m in muracietler if m.get("tarix", "").startswith(bugun_str))
        yeni        = sum(1 for m in muracietler if m.get("status") == "yeni")
        vip_sayi    = sum(1 for m in musteriler  if m.get("muraciet_sayi", 0) >= 5)
        sadiq_sayi  = sum(1 for m in musteriler  if 3 <= m.get("muraciet_sayi", 0) < 5)

        # Funnel hesabla
        funnel = {"maraqlandı": 0, "sual verdi": 0, "müraciət etdi": 0}
        for m in musteriler:
            s = m.get("stage", "maraqlandı")
            if s in funnel:
                funnel[s] += 1

        return render_template_string(ADMIN_HTML,
            muracietler=muracietler, musteriler=musteriler,
            cem_muraciet=len(muracietler), yeni_muraciet=yeni,
            cem_musteri=len(musteriler), bugun=bugun,
            vip_sayi=vip_sayi, sadiq_sayi=sadiq_sayi, funnel=funnel)
    except Exception as e:
        return f"<h3>Xəta: {e}</h3>", 500


@app.route("/")
def home():
    return "Garant Consulting WhatsApp Bot işləyir! ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
