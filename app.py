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

# Hər telefon nömrəsi üçün seçilmiş şirkəti yadda saxlayır
user_company = {}


# ════════════════════════════════════════════════════════════════
# 4 ŞİRKƏT KONFİQURASİYASI
# ════════════════════════════════════════════════════════════════

COMPANIES = {
    "garant": {
        "id": "garant",
        "name": "Garant Consulting",
        "emoji": "🏢",
        "color": "blue",
        "subtitle": "Mühasibatlıq & Maliyyə Xidmətləri",
        "owner": "Ayşən Salamova",
        "hours": "B.E–Cümə, 10:00–18:00",
        "welcome_btn_title": "🏢 Garant Consulting",
        "btn_id": "btn_company_garant",
    },
    "ai_system": {
        "id": "ai_system",
        "name": "AI İdarəetmə Sistemləri",
        "emoji": "🤖",
        "color": "purple",
        "subtitle": "Süni İntellekt & Avtomatlaşdırma",
        "owner": "AI Konsultant",
        "hours": "7/24 AI Dəstək",
        "welcome_btn_title": "🤖 AI Sistemlər",
        "btn_id": "btn_company_ai",
    },
    "nat_psixologiya": {
        "id": "nat_psixologiya",
        "name": "NAT Psixologiya",
        "emoji": "🧠",
        "color": "green",
        "subtitle": "Psixoloji Dəstək & Terapiya",
        "owner": "NAT Psixologiya Komandası",
        "hours": "B.E–Şənbə, 09:00–19:00",
        "welcome_btn_title": "🧠 NAT Psixologiya",
        "btn_id": "btn_company_nat",
    },
    "casa_eleganza": {
        "id": "casa_eleganza",
        "name": "Casa Eleganza",
        "emoji": "🛋️",
        "color": "gold",
        "subtitle": "Premium Mebel & İnteryer",
        "owner": "Casa Eleganza",
        "hours": "Həftəiçi 10:00–20:00, Ş-B 11:00–18:00",
        "welcome_btn_title": "🛋️ Casa Eleganza",
        "btn_id": "btn_company_casa",
    },
}


# ════════════════════════════════════════════════════════════════
# SİSTEM PROMPTLARI — Hər şirkət üçün ayrı
# ════════════════════════════════════════════════════════════════

SISTEM_PROMPTLARI = {

    "garant": """Sən Garant Consulting şirkətinin WhatsApp AI assistentisən — eyni zamanda hər mövzuda dərin bilik sahibi olan universal AI agentisən.

XARAKTER:
- Adın "Garant AI" — peşəkar, mehriban, ağıllı
- Üslub: pozitiv, enerji dolu, yumoru olan amma həmişə peşəkar
- Azərbaycan dilini mükəmməl bilirsən
- Mühasibat, vergi, hüquq, biznes, maliyyə mövzularında ekspertsən
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
- Mühasibat/vergi/maliyyə sualı → dərin ekspert cavabı ver
- Ümumi bilik sualı → tam, dəqiq cavab ver
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
- Heç vaxt "Bilmirəm" demə
""",

    "ai_system": """Sən "AI İdarəetmə Sistemləri" şirkətinin WhatsApp AI assistentisən — süni intellekt, avtomatlaşdırma və rəqəmsal transformasiya mövzusunda dünyaca tanınan ekspert AI-san.

XARAKTER:
- Adın "Nova AI" — visionar, innovativ, texnoloji cəhətdən üstün
- Üslub: gələcəyə baxan, aydın, həyəcan verici amma peşəkar
- Azərbaycan dilini mükəmməl bilirsən
- AI, machine learning, avtomatlaşdırma, chatbot, data analitika mövzularında dərin ekspertsən

ŞİRKƏT — AI İdarəetmə Sistemləri:
- Missiya: Azərbaycan bizneslərini AI ilə trilyoner səviyyəyə çatdırmaq
- İş saatları: 7/24 AI Dəstəyi + B.E–Cümə insan komandası

XİDMƏTLƏR:
1. WhatsApp AI Bot yaradılması — 500₼-dan
2. Müştəri xidmətləri avtomatlaşdırması — fərdi qiymət
3. CRM & AI inteqrasiyası — 1000₼-dan
4. Satış AI agenti — 800₼/ay
5. Məlumat analitika sistemi — 600₼-dan
6. Xüsusi AI tətbiq hazırlanması — fərdi
7. AI ilə content marketinq — 300₼/ay
8. İntelligent idarəetmə paneli — 700₼-dan
9. AI konsultasiya sessiyası — 100₼/saat

CAVAB STRATEGİYASI:
- AI/texnologiya sualı → dərin, vizionar cavab ver, gələcəyi göstər
- Biznes avtomatlaşdırması → konkret ROI göstər
- Kod/proqramlaşdırma sualı → işlək kod yaz, izah et
- Müraciət etmək istəyəndə: QEYDİYYAT formatı

QEYDİYYAT FORMATI (yalnız müraciət tamamlandıqda):
✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]

CAVAB UZUNLUĞU:
- Hər cavabda gələcəyə baxış ver
- Rəqəmlərlə dəyər göstər (vaxt, pul qənaəti)
- Heç vaxt "Bilmirəm" demə — innovativ həll təklif et
""",

    "nat_psixologiya": """Sən "NAT Psixologiya" mərkəzinin WhatsApp AI assistentisən — empatiya, anlayış və psixoloji dəstək sahəsində ixtisaslaşmış şəfqətli AI assistentsən.

XARAKTER:
- Adın "Nata" — isti, anlayışlı, şəfqətli, həssas
- Üslub: sakit, dəstəkləyici, qeyri-mühakimə edici, ümid verən
- Azərbaycan dilini mükəmməl bilirsən
- Psixologiya, terapiya, əlaqə dinamikası, stress idarəetmə mövzularında dərin ekspertsən
- HƏR ZAMAN insanın hissiyatını əvvəlcə eşit, sonra cavabla

ŞİRKƏT — NAT Psixologiya:
- Peşəkar psixoloji yardım mərkəzi
- İş saatları: B.E–Şənbə, 09:00–19:00
- Missiya: Hər insanı daha güclü, xoşbəxt, balanslaşmış həyata aparmaq

XİDMƏTLƏR:
1. Fərdi psixoterapiya (onlayn/offline) — 60₼/sesiya
2. Cüt terapiyası / münasibət konsultasiyası — 80₼/sesiya
3. Uşaq psixologiyası — 70₼/sesiya
4. Stres & əsəb idarəetməsi kursları — 150₼/kurs
5. Anxiety & depressiya müalicəsi — fərdi proqram
6. Ailə terapiyası — 90₼/sesiya
7. Karyera & həyat koçinqi — 70₼/sesiya
8. Qrup terapiya sessiyaları — 40₼/sesiya
9. Psixoloji test & qiymətləndirmə — 80₼

CAVAB STRATEGİYASI:
- Hər psixoloji sual → əvvəlcə empatiya göstər, sonra konstruktiv cavab ver
- KRİZİS siqnalları (özünəzərər, intihar fikri) → dərhal: "📞 Sizinlə danışmaq istəyirik. Zəhmət olmasa +994... nömrəsinə zəng edin"
- Ümumi psixologiya məlumatı → əlçatan, normallaşdırıcı dil
- Müraciət etmək istəyəndə: QEYDİYYAT formatı

QEYDİYYAT FORMATI (yalnız müraciət tamamlandıqda):
✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]

MÜHÜM: Heç vaxt təşxis qoyma. "Mütəxəssisimizlə görüş" de. Həmişə ümid ver.
""",

    "casa_eleganza": """Sən "Casa Eleganza" premium mebel şirkətinin WhatsApp AI assistentisən — estetika, lüks dizayn və premium yaşam üslubu sahəsinin bilicisən.

XARAKTER:
- Adın "Elena" — elegant, zövqlü, incə, zəngin bilgi sahibi
- Üslub: lüks, lakin istiqanlı; premium, lakin əlçatan
- Azərbaycan dilini mükəmməl bilirsən
- İnteryer dizayn, mebel materialları, ev dekorasiyası mövzularında ekspertsən
- Müştəriyə "ev sahibi" kimi yanaş — onların arzusunu həyata keçirməyə kömək et

ŞİRKƏT — Casa Eleganza:
- Premium segment mebel & interyer şirkəti
- İş saatları: Həftəiçi 10:00–20:00, Şənbə-Bazar 11:00–18:00
- Missiya: Hər evə bir şah əsəri bəxş etmək

KOLLEKSIYALAR & XİDMƏTLƏR:
1. Oturma otağı mebeli (sofa, kreslo, stol) — 800₼-dan
2. Yataq otağı dəstləri — 1500₼-dan
3. Mətbəx mebeli — 2000₼-dan
4. Xüsusi sifarişli mebel — fərdi
5. Ofis mebeli — 500₼-dan
6. İnteryer dizayn konsultasiyası — 150₼/saat
7. 3D planlaşdırma xidməti — 200₼
8. Ev tekstili & aksessuarlar — 100₼-dan
9. Çatdırılma & quraşdırma — pulsuz (500₼+ sifarişdə)

MATERİALLAR: İtalya meşin, natural ağac, paslanmaz polad, Türkiyə parçası

CAVAB STRATEGİYASI:
- Mebel/dizayn sualı → zövqlü, ətraflı izah; material keyfiyyəti vurğula
- Stil məsləhəti → Skandinav, Klasik, Minimalist, Art Deco — konkret tövsiyə ver
- Qiymət soruşanda → dəyər anlayışını vurğula, keyfiyyəti izah et
- Müraciət etmək istəyəndə: QEYDİYYAT formatı

QEYDİYYAT FORMATI (yalnız müraciət tamamlandıqda):
✅ QEYDİYYAT: [ad] | [telefon] | [xidmət]

CAVAB UZUNLUĞU:
- Estetik, zövqlü dil — "gözəl", "zərif", "şık", "premium" kimi sözlər
- Görsel məkan canlandır — "Təsəvvür edin: İtalyan meşin divanda..."
- Həmişə "sizin eviniz" perspektivindən danış
""",
}


# ════════════════════════════════════════════════════════════════
# ŞIRKƏT MENYULARI — Button strukturları
# ════════════════════════════════════════════════════════════════

def get_company_menu(company_id):
    menus = {
        "garant": {
            "body": "🏢 *Garant Consulting* — Nə ilə kömək edə bilərəm?",
            "buttons": [
                {"id": "garant_xidmetler",  "title": "📊 Xidmətlər"},
                {"id": "garant_qeydiyyat",  "title": "📝 Müraciət et"},
                {"id": "garant_elaqe",      "title": "📞 Əlaqə & Saatlar"},
            ]
        },
        "ai_system": {
            "body": "🤖 *AI İdarəetmə Sistemləri* — Biznesi AI ilə gücləndir!",
            "buttons": [
                {"id": "ai_xidmetler",      "title": "⚡ AI Xidmətlər"},
                {"id": "ai_demo",           "title": "🎯 Demo Tələb Et"},
                {"id": "ai_elaqe",          "title": "📞 Əlaqə"},
            ]
        },
        "nat_psixologiya": {
            "body": "🧠 *NAT Psixologiya* — Sizi dinləyirik, dəstəkləyirik!",
            "buttons": [
                {"id": "nat_xidmetler",     "title": "💚 Xidmətlər"},
                {"id": "nat_seans",         "title": "📅 Seans Ayırt"},
                {"id": "nat_elaqe",         "title": "📞 Əlaqə"},
            ]
        },
        "casa_eleganza": {
            "body": "🛋️ *Casa Eleganza* — Evinizi bir şah əsərinə çevirin!",
            "buttons": [
                {"id": "casa_kolleksiya",   "title": "✨ Kolleksiyalar"},
                {"id": "casa_sifaris",      "title": "🛍️ Sifariş Ver"},
                {"id": "casa_elaqe",        "title": "📞 Əlaqə"},
            ]
        },
    }
    return menus.get(company_id, {})


# Alt-menyular — hər button üçün
def handle_company_submenu(phone, btn_id):
    """Button ID-yə görə alt-menyu göndər. True qaytarır əgər işləndi."""

    # ── GARANT CONSULTING ───────────────────────────────────────
    if btn_id == "garant_xidmetler":
        send_whatsapp(phone,
            "💼 *Garant Consulting — Xidmətlər:*\n\n"
            "1️⃣ Mühasibat uçotu — 150₼/ay\n"
            "2️⃣ Vergi hesabatı — 80₼-dan\n"
            "3️⃣ Əmək haqqı (Payroll) — 100₼/ay\n"
            "4️⃣ Şirkət qeydiyyatı — 200₼\n"
            "5️⃣ Şirkətin ləğvi — 300₼-dan\n"
            "6️⃣ Mühasibat konsaltinqi — 50₼/saat\n"
            "7️⃣ Maliyyə audit — 500₼-dan\n"
            "8️⃣ Vergi optimallaşdırması — fərdi\n"
            "9️⃣ Maliyyə hesabatı — 120₼-dan\n\n"
            "💡 Fərdi qiymət üçün müraciət edin!")
        time.sleep(0.5)
        send_buttons(phone, "Hansı xidmətlə maraqlanırsınız?",
            [{"id": "garant_muhasibat",  "title": "📒 Mühasibat"},
             {"id": "garant_vergi",      "title": "🧾 Vergi"},
             {"id": "garant_qeydiyyat",  "title": "📝 Müraciət et"}])
        return True

    elif btn_id == "garant_muhasibat":
        send_whatsapp(phone,
            "📒 *Mühasibat Xidmətləri — Garant Consulting:*\n\n"
            "✅ Mühasibat uçotu — 150₼/ay\n"
            "   • Gəlir-xərc uçotu\n"
            "   • Bank hesablaşmaları\n"
            "   • Aylıq balans\n\n"
            "✅ Əmək haqqı (Payroll) — 100₼/ay\n"
            "   • DSMF hesablamaları\n"
            "   • İşçi cədvəlləri\n"
            "   • Elektron imza\n\n"
            "✅ Maliyyə hesabatı — 120₼-dan\n"
            "   • IFRS standartı\n"
            "   • Investor hesabatı\n"
            "   • Müqayisəli analiz\n\n"
            "🤝 Aylıq sabit ödənişlə arxayın olun!")
        time.sleep(0.5)
        send_buttons(phone, "Müraciət etmək istərdinizmi?",
            [{"id": "garant_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "garant_elaqe",     "title": "📞 Zəng et"}])
        return True

    elif btn_id == "garant_vergi":
        send_whatsapp(phone,
            "🧾 *Vergi Xidmətləri — Garant Consulting:*\n\n"
            "✅ Vergi hesabatı — 80₼-dan\n"
            "   • ƏDV hesabatları\n"
            "   • Gəlir vergisi\n"
            "   • Sadələşdirilmiş vergi\n\n"
            "✅ Vergi optimallaşdırması — fərdi\n"
            "   • Qanuni vergi azaldılması\n"
            "   • Vergi güzəştlərindən istifadə\n"
            "   • Risk analizi\n\n"
            "✅ Şirkət qeydiyyatı — 200₼\n"
            "   • MMC, SC, fərdi sahibkar\n"
            "   • Vergi orqanına qeydiyyat\n"
            "   • Elektron imza alınması\n\n"
            "⚡ Vergi yoxlamasından qorxmayın — biz yanınızdayıq!")
        time.sleep(0.5)
        send_buttons(phone, "Növbəti addım:",
            [{"id": "garant_qeydiyyat", "title": "📝 Müraciət et"},
             {"id": "garant_xidmetler", "title": "📊 Digər xidmətlər"}])
        return True

    elif btn_id == "garant_qeydiyyat":
        send_whatsapp(phone,
            "📝 *Müraciət — Garant Consulting*\n\n"
            "Mütəxəssisimizlə əlaqə qurmaq üçün sadəcə adınızı "
            "və hansı xidmətlə maraqlandığınızı yazın.\n\n"
            "Biz sizinlə ən qısa zamanda əlaqə saxlayacağıq! 🤝\n\n"
            "⏰ İş saatları: B.E–Cümə, 10:00–18:00")
        return True

    elif btn_id == "garant_elaqe":
        send_whatsapp(phone,
            "📞 *Garant Consulting — Əlaqə:*\n\n"
            "👤 Rəhbər: Ayşən Salamova\n"
            "👥 Təsisçi: Balakişi Qurbanov\n"
            "⏰ İş saatları: B.E–Cümə, 10:00–18:00\n"
            "💬 Bu WhatsApp vasitəsilə 24/7 AI dəstək\n\n"
            "🤝 Sizi qarşılamaqdan məmnun olarıq!")
        time.sleep(0.5)
        send_buttons(phone, "Başqa bir şey soruşmaq istərdinizmi?",
            [{"id": "garant_xidmetler", "title": "📊 Xidmətlər"},
             {"id": "garant_qeydiyyat", "title": "📝 Müraciət et"}])
        return True

    # ── AI İDARƏETMƏ SİSTEMLƏRİ ────────────────────────────────
    elif btn_id == "ai_xidmetler":
        send_whatsapp(phone,
            "⚡ *AI İdarəetmə Sistemləri — Xidmətlər:*\n\n"
            "1️⃣ WhatsApp AI Bot — 500₼-dan\n"
            "2️⃣ Müştəri xidmətləri avtomatlaşdırması — fərdi\n"
            "3️⃣ CRM & AI inteqrasiyası — 1000₼-dan\n"
            "4️⃣ Satış AI agenti — 800₼/ay\n"
            "5️⃣ Məlumat analitika sistemi — 600₼-dan\n"
            "6️⃣ Xüsusi AI tətbiq — fərdi\n"
            "7️⃣ AI content marketinq — 300₼/ay\n"
            "8️⃣ İntelligent idarəetmə paneli — 700₼-dan\n"
            "9️⃣ AI konsultasiya — 100₼/saat\n\n"
            "🚀 ROI: Orta hesabla 3 ayda özünü ödəyir!")
        time.sleep(0.5)
        send_buttons(phone, "Hansı AI həll sizi maraqlandırır?",
            [{"id": "ai_chatbot",     "title": "🤖 AI Chatbot"},
             {"id": "ai_analitika",   "title": "📊 Analitika"},
             {"id": "ai_demo",        "title": "🎯 Demo Tələb Et"}])
        return True

    elif btn_id == "ai_chatbot":
        send_whatsapp(phone,
            "🤖 *WhatsApp AI Bot Xidməti:*\n\n"
            "💡 Nə qazanırsınız:\n"
            "✅ 24/7 müştəri xidməti — insan xərci yox\n"
            "✅ Eyni anda 1000+ müştəriyə cavab\n"
            "✅ Azərbaycan, Rus, İngilis dil dəstəyi\n"
            "✅ Sifarişin avtomatik qeydiyyatı\n"
            "✅ CRM inteqrasiyası\n"
            "✅ Səsli mesaj transkripti\n\n"
            "💰 *Qiymətlər:*\n"
            "• Starter: 500₼ (quraşdırma) + 150₼/ay\n"
            "• Business: 800₼ + 250₼/ay\n"
            "• Enterprise: Fərdi\n\n"
            "📈 Nümunə: Garant Consulting botumuz ayda 200+ müraciəti avtomatik işləyir!")
        time.sleep(0.5)
        send_buttons(phone, "Sizin biznez üçün demo görmək istərdinizmi?",
            [{"id": "ai_demo",    "title": "🎯 Demo Tələb Et"},
             {"id": "ai_elaqe",  "title": "📞 Əlaqə"}])
        return True

    elif btn_id == "ai_analitika":
        send_whatsapp(phone,
            "📊 *AI Məlumat Analitika Sistemi:*\n\n"
            "🔍 *Nə edə bilər:*\n"
            "✅ Satış trendlərini proqnozlaşdır\n"
            "✅ Müştəri davranışını analiz et\n"
            "✅ Rəqabət monitorinqi\n"
            "✅ Real-vaxt dashboard\n"
            "✅ Avtomatik hesabatlar\n"
            "✅ Anomaliya aşkarlanması\n\n"
            "🏆 *Nümunə nəticə:*\n"
            "• Bir müştərimiz AI analitika ilə satışını 47% artırdı\n"
            "• Digəri inventar xərclərini 30% azaltdı\n\n"
            "💰 Qiymət: 600₼-dan başlayır")
        time.sleep(0.5)
        send_buttons(phone, "Öz biznesiniz üçün analiz istərdinizmi?",
            [{"id": "ai_demo",    "title": "🎯 Demo Tələb Et"},
             {"id": "ai_elaqe",  "title": "📞 Danışaq"}])
        return True

    elif btn_id == "ai_demo":
        send_whatsapp(phone,
            "🎯 *Pulsuz Demo Tələbi — AI Sistemləri*\n\n"
            "Biznesinizə uyğun AI həlli canlı nümayiş edirik!\n\n"
            "📋 Demo prosesi:\n"
            "1. Adınız və şirkətinizi yazın\n"
            "2. Biznes növünüzü qeyd edin\n"
            "3. Vaxt təyin edirik — 30 dəqiqəlik Zoom\n\n"
            "🎁 *Demo tamamilə PULSUZdur!*\n"
            "Adınızı yazın, başlayaq 🚀")
        return True

    elif btn_id == "ai_elaqe":
        send_whatsapp(phone,
            "📞 *AI İdarəetmə Sistemləri — Əlaqə:*\n\n"
            "🤖 AI dəstək: 7/24 bu chat vasitəsilə\n"
            "👥 İnsan komanda: B.E–Cümə, 10:00–18:00\n"
            "🌐 Xidmət: Azərbaycan & beynəlxalq\n\n"
            "💡 Ən sürətli cavab üçün buradan yazın!")
        time.sleep(0.5)
        send_buttons(phone, "Başqa bir şey soruşmaq istərdinizmi?",
            [{"id": "ai_xidmetler", "title": "⚡ Xidmətlər"},
             {"id": "ai_demo",     "title": "🎯 Demo"}])
        return True

    # ── NAT PSİXOLOGİYA ─────────────────────────────────────────
    elif btn_id == "nat_xidmetler":
        send_whatsapp(phone,
            "💚 *NAT Psixologiya — Xidmətlər:*\n\n"
            "🧘 Fərdi psixoterapiya — 60₼/sesiya\n"
            "💑 Cüt terapiyası — 80₼/sesiya\n"
            "👶 Uşaq psixologiyası — 70₼/sesiya\n"
            "😰 Stress & əsəb kursu — 150₼/kurs\n"
            "💙 Anxiety & depressiya proqramı — fərdi\n"
            "👨‍👩‍👧 Ailə terapiyası — 90₼/sesiya\n"
            "🎯 Karyera & həyat koçinqi — 70₼/sesiya\n"
            "👥 Qrup terapiyası — 40₼/sesiya\n"
            "📋 Psixoloji test — 80₼\n\n"
            "💙 İlk sessiyanız güvənli, məxfi, qeyri-mühakiməlidir.")
        time.sleep(0.5)
        send_buttons(phone, "Hansı sahə sizi maraqlandırır?",
            [{"id": "nat_fardi",   "title": "🧘 Fərdi Terapiya"},
             {"id": "nat_ailə",    "title": "👨‍👩‍👧 Ailə & Cüt"},
             {"id": "nat_seans",   "title": "📅 Seans Ayırt"}])
        return True

    elif btn_id == "nat_fardi":
        send_whatsapp(phone,
            "🧘 *Fərdi Psixoterapiya — NAT:*\n\n"
            "Fərdi terapiya ilə nə qazanırsınız:\n\n"
            "✅ Özünüzü daha yaxşı tanıyırsınız\n"
            "✅ Narahatedici düşüncələrlə başa çıxırsınız\n"
            "✅ Stress və narahatçılığı idarə etməyi öyrənirsiniz\n"
            "✅ Özgüvənləri artırırsınız\n"
            "✅ Keçmişdəki yaraları sağaldırsınız\n\n"
            "🕐 *Sesiya:* 50 dəqiqə | 💰 60₼\n"
            "🌐 *Format:* Onlayn (Zoom/WhatsApp video) + Offline\n"
            "🔒 *Məxfilik:* 100% təmin olunur\n\n"
            "💬 Heç bir şey paylaşmağa məcbur deyilsiniz. "
            "Öz tempinizlə gedirsiniz.")
        time.sleep(0.5)
        send_buttons(phone, "Seans ayırtmaq istərdinizmi?",
            [{"id": "nat_seans",    "title": "📅 Seans Ayırt"},
             {"id": "nat_elaqe",   "title": "📞 Əlaqə"}])
        return True

    elif btn_id == "nat_ailə":
        send_whatsapp(phone,
            "👨‍👩‍👧 *Ailə & Cüt Terapiyası — NAT:*\n\n"
            "💑 *Cüt terapiyası (80₼/sesiya):*\n"
            "• Ünsiyyət problemlərini həll et\n"
            "• Münaqişə idarəetməsini öyrən\n"
            "• Intimliyi yenidən qurun\n"
            "• Güvəni bərpa edin\n\n"
            "👨‍👩‍👧 *Ailə terapiyası (90₼/sesiya):*\n"
            "• Valideyn-uşaq münasibəti\n"
            "• Boşanma prosesini şüurlu keçirin\n"
            "• Ailə dinamikasını sağlamlaşdırın\n\n"
            "👶 *Uşaq psixologiyası (70₼/sesiya):*\n"
            "• Davranış problemləri\n"
            "• Məktəb uyumsuzluğu\n"
            "• Emosional çətinliklər\n\n"
            "💙 Ailənizdə hər şey həll oluna bilər — vaxt lazımdır.")
        time.sleep(0.5)
        send_buttons(phone, "Seans ayırtmaq istərdinizmi?",
            [{"id": "nat_seans",   "title": "📅 Seans Ayırt"},
             {"id": "nat_elaqe",  "title": "📞 Əlaqə"}])
        return True

    elif btn_id == "nat_seans":
        send_whatsapp(phone,
            "📅 *Seans Ayırtma — NAT Psixologiya*\n\n"
            "Seans ayırtmaq çox sadədir:\n\n"
            "1️⃣ Adınızı yazın\n"
            "2️⃣ Hansı xidmətlə maraqlandığınızı qeyd edin\n"
            "3️⃣ Əlverişli gün/saatı bildirin\n\n"
            "Mütəxəssisimiz sizinlə əlaqə saxlayacaq.\n\n"
            "⏰ Seans saatları: B.E–Şənbə, 09:00–19:00\n"
            "🌐 Format seçin: onlayn və ya offline\n\n"
            "💙 İlk addımı atmaq — ən cəsarətli hərəkətdir.")
        return True

    elif btn_id == "nat_elaqe":
        send_whatsapp(phone,
            "📞 *NAT Psixologiya — Əlaqə:*\n\n"
            "👥 NAT Psixologiya Komandası\n"
            "⏰ Seans saatları: B.E–Şənbə, 09:00–19:00\n"
            "💬 Bu WhatsApp vasitəsilə sual verə bilərsiniz\n"
            "🌐 Onlayn seanslar mövcuddur\n\n"
            "💙 Hər sual, hər hiss — dəyərlidir.\n"
            "Sizi dinləməkdən məmnunik! 🤝")
        time.sleep(0.5)
        send_buttons(phone, "Başqa bir şey soruşmaq istərdinizmi?",
            [{"id": "nat_xidmetler", "title": "💚 Xidmətlər"},
             {"id": "nat_seans",     "title": "📅 Seans Ayırt"}])
        return True

    # ── CASA ELEGANZA ───────────────────────────────────────────
    elif btn_id == "casa_kolleksiya":
        send_whatsapp(phone,
            "✨ *Casa Eleganza — Premium Kolleksiyalar:*\n\n"
            "🛋️ *Oturma Otağı:* 800₼-dan\n"
            "   • İtalya meşin sofalar\n"
            "   • Natural ağac jurnallıq masalar\n"
            "   • Designer kreslo & pouffe\n\n"
            "🛏️ *Yataq Otağı:* 1500₼-dan\n"
            "   • Premium yataq dəstləri\n"
            "   • Gizli rəfli şkaflar\n"
            "   • Tualet masası & ayna\n\n"
            "🍳 *Mətbəx:* 2000₼-dan\n"
            "   • Tam komplekt mətbəx\n"
            "   • Fərdi planlaşdırma\n"
            "   • Quartz & granite tezgah\n\n"
            "💼 *Ofis Mebeli:* 500₼-dan\n"
            "   • Executive masa & kreslo\n"
            "   • Kitabxana & rəflər")
        time.sleep(0.5)
        send_buttons(phone, "Hansı otağı dizayn edirsiniz?",
            [{"id": "casa_oturma",   "title": "🛋️ Oturma otağı"},
             {"id": "casa_yataq",    "title": "🛏️ Yataq otağı"},
             {"id": "casa_sifaris",  "title": "🛍️ Sifariş Ver"}])
        return True

    elif btn_id == "casa_oturma":
        send_whatsapp(phone,
            "🛋️ *Oturma Otağı Kolleksiyası — Casa Eleganza:*\n\n"
            "🏆 *Bestseller — Milano Seriyası:*\n"
            "• 3+1+1 divan dəsti — İtalya meşin\n"
            "• Rəng: Cognac, Navy, Pearl, Charcoal\n"
            "• Qiymət: 2400₼-dan\n\n"
            "🌿 *Skandinav Minimalist:*\n"
            "• Natural ağac ayaqlı, yumşaq parça\n"
            "• Modullu dizayn — istədiyiniz kimi düzün\n"
            "• Qiymət: 1800₼-dan\n\n"
            "👑 *Klassik Royal:*\n"
            "• Oyma dekor, qızıl detal\n"
            "• Brokad parça\n"
            "• Qiymət: 3200₼-dan\n\n"
            "🎁 *Xüsusi Təklif:* Tam dəstdə 15% endirim!\n"
            "📐 Pulsuz 3D planlaşdırma xidməti!")
        time.sleep(0.5)
        send_buttons(phone, "Bu kolleksiya üçün məsləhət alaq?",
            [{"id": "casa_sifaris",    "title": "🛍️ Sifariş Ver"},
             {"id": "casa_3d",         "title": "📐 3D Plan"},
             {"id": "casa_elaqe",      "title": "📞 Əlaqə"}])
        return True

    elif btn_id == "casa_yataq":
        send_whatsapp(phone,
            "🛏️ *Yataq Otağı Kolleksiyası — Casa Eleganza:*\n\n"
            "🌙 *Elegante Seriyası (bestseller):*\n"
            "• Döşəkçə + 2 gecəlik stol + şkaf\n"
            "• Material: natural palıd\n"
            "• Qiymət: 2800₼-dan\n\n"
            "✨ *Luxe Blanc (ağ lak):*\n"
            "• Modern minimalst dizayn\n"
            "• Gizli aparat sistemli şkaf\n"
            "• Qiymət: 3500₼-dan\n\n"
            "🪵 *Terra Natural:*\n"
            "• 100% natural ağac\n"
            "• Əl işi oyma detallar\n"
            "• Qiymət: 4200₼-dan\n\n"
            "💤 *Döşək Seçimi:*\n"
            "• Ortopedik premium — 600₼-dan\n"
            "• Memory foam — 800₼-dan\n\n"
            "🚚 Çatdırılma & quraşdırma — PULSUZdur!")
        time.sleep(0.5)
        send_buttons(phone, "Sizin üçün ideal seçim tapaq?",
            [{"id": "casa_sifaris",  "title": "🛍️ Sifariş Ver"},
             {"id": "casa_3d",       "title": "📐 3D Plan"},
             {"id": "casa_elaqe",    "title": "📞 Əlaqə"}])
        return True

    elif btn_id == "casa_3d":
        send_whatsapp(phone,
            "📐 *Pulsuz 3D Planlaşdırma — Casa Eleganza:*\n\n"
            "🎨 Evinizin ölçülərini göndərin — biz:\n\n"
            "✅ Otağınızın 3D modelini hazırlayırıq\n"
            "✅ Fərqli mebel variantlarını göstəririk\n"
            "✅ Rəng uyğunluğunu planlaşdırırıq\n"
            "✅ Real yerləşdirmə simulyasiyası edirik\n\n"
            "📏 Lazım olanlar:\n"
            "• Otağın uzunluq, en, hündürlük ölçüsü\n"
            "• Qapı & pəncərə yerləri\n"
            "• Üstünlük verdiyin stil\n\n"
            "⏱️ 3D plan 24 saatda hazırdır!\n"
            "💰 Bu xidmət tamamilə PULSUZdur!")
        return True

    elif btn_id == "casa_sifaris":
        send_whatsapp(phone,
            "🛍️ *Sifariş — Casa Eleganza*\n\n"
            "Sifarişinizi vermək üçün:\n\n"
            "1️⃣ Adınızı yazın\n"
            "2️⃣ Hansı mebel/xidmətlə maraqlandığınızı qeyd edin\n"
            "3️⃣ Ünvanınızı bildirin (çatdırılma üçün)\n\n"
            "Mütəxəssisimiz sizinlə əlaqə quracaq.\n\n"
            "🎁 *500₼+ sifarişdə çatdırılma & quraşdırma — PULSUZDUR!*\n"
            "⏰ Showroom: Həftəiçi 10:00–20:00")
        return True

    elif btn_id == "casa_elaqe":
        send_whatsapp(phone,
            "📞 *Casa Eleganza — Əlaqə:*\n\n"
            "🛋️ Premium Mebel & İnteryer\n"
            "⏰ Həftəiçi: 10:00–20:00\n"
            "⏰ Şənbə-Bazar: 11:00–18:00\n"
            "💬 Bu WhatsApp vasitəsilə məsləhət alın\n"
            "📐 Pulsuz 3D planlama mövcuddur\n\n"
            "✨ Evinizi bir şah əsərinə çeviririk! 🏠")
        time.sleep(0.5)
        send_buttons(phone, "Başqa bir şey soruşmaq istərdinizmi?",
            [{"id": "casa_kolleksiya",  "title": "✨ Kolleksiyalar"},
             {"id": "casa_3d",          "title": "📐 3D Plan"},
             {"id": "casa_sifaris",     "title": "🛍️ Sifariş Ver"}])
        return True

    return False


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

# WhatsApp maksimum 3 button dəstəkləyir, buna görə bölünmüş göndərmə
def send_4_company_buttons(phone, greeting):
    """İki ayrı mesaj ilə 4 şirkət seçimi göndər"""
    send_whatsapp(phone, greeting)
    time.sleep(0.5)
    send_buttons(phone,
        "🏢 Xidmət almaq istədiyiniz şirkəti seçin:",
        [{"id": "btn_company_garant", "title": "🏢 Garant Consulting"},
         {"id": "btn_company_ai",     "title": "🤖 AI Sistemlər"},
         {"id": "btn_company_nat",    "title": "🧠 NAT Psixologiya"}])
    time.sleep(0.5)
    send_buttons(phone,
        "Və ya:",
        [{"id": "btn_company_casa",  "title": "🛋️ Casa Eleganza"},
         {"id": "btn_back_main",     "title": "ℹ️ Hamısı haqqında"},
         {"id": "btn_back_main",     "title": "ℹ️ Məlumat"}])


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

def save_customer(phone, ad=None, xidmet=None, stage=None, company=None):
    try:
        existing = get_customer(phone)
        if existing:
            upd = {"son_muraciet": "now()",
                   "muraciet_sayi": existing["muraciet_sayi"] + 1}
            if ad:      upd["ad"]      = ad
            if xidmet:  upd["xidmet"]  = xidmet
            if stage:   upd["stage"]   = stage
            if company: upd["company"] = company
            supabase.table("musteriler").update(upd).eq("telefon", phone).execute()
        else:
            supabase.table("musteriler").insert({
                "telefon": phone, "ad": ad, "xidmet": xidmet,
                "stage": stage or "maraqlandı",
                "company": company or "naməlum"}).execute()
    except:
        pass

def save_muraciet(phone, ad, xidmet, company="naməlum"):
    try:
        supabase.table("muracietler").insert({
            "telefon": phone, "ad": ad,
            "xidmet": xidmet, "status": "yeni",
            "company": company}).execute()
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
# 🧠 AI CAVAB — Şirkətə görə prompt seçir
# ════════════════════════════════════════════════════════════════

RATE_LIMIT_MESAJ = (
    "😅 Sistemimiz bu an çox yüklüdür.\n\n"
    "Zəhmət olmasa 10-15 dəqiqə sonra yenidən yazın. 🙏"
)

def get_ai_response(phone, user_message):
    if phone not in conversations:
        conversations[phone] = []

    customer       = get_customer(phone)
    segment, emoji = get_segment(customer)
    company_id     = user_company.get(phone, "garant")
    sistem_promptu = SISTEM_PROMPTLARI.get(company_id, SISTEM_PROMPTLARI["garant"])
    company_info   = COMPANIES.get(company_id, COMPANIES["garant"])

    meta = f"\n\n[SİSTEM KONTEKST]\nMÜŞTƏRİ: +{phone}"
    if customer and customer.get("ad"):
        meta += f"\nAD: {customer['ad']} (HƏMİŞƏ adı ilə müraciət et)"
    meta += f"\nSEQMENT: {segment} {emoji}"
    meta += f"\nAKTİV ŞİRKƏT: {company_info['name']}"
    if customer and customer.get("muraciet_sayi", 0) > 1:
        meta += f"\nMÜRACİƏT SAYI: {customer['muraciet_sayi']}"
    now = baku_now()
    meta += f"\nBAKI SAATI: {now.strftime('%H:%M, %d.%m.%Y')}"

    conversations[phone].append({"role": "user", "content": user_message})
    if len(conversations[phone]) > 30:
        conversations[phone] = conversations[phone][-30:]

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=800,
            temperature=0.7,
            messages=[
                {"role": "system", "content": sistem_promptu + meta},
                *conversations[phone]
            ]
        )
        ai_text = response.choices[0].message.content
        conversations[phone].append({"role": "assistant", "content": ai_text})
        stage = "müraciət etdi" if "QEYDİYYAT:" in ai_text else "sual verdi"
        save_customer(phone, stage=stage, company=company_id)
        return ai_text

    except Exception as e:
        err = str(e)
        print(f"AI xətası: {err}")
        if "rate_limit_exceeded" in err or "429" in err:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    max_tokens=500,
                    temperature=0.7,
                    messages=[
                        {"role": "system", "content": sistem_promptu + meta},
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
            details  = ai_text.split("QEYDİYYAT:")[1].strip().split("|")
            ad       = details[0].strip() if len(details) > 0 else ""
            xidmet   = details[2].strip() if len(details) > 2 else ""
            company_id = user_company.get(phone, "garant")
            save_customer(phone, ad=ad, xidmet=xidmet, stage="müraciət etdi", company=company_id)
            save_muraciet(phone, ad, xidmet, company=company_id)
            customer = get_customer(phone)
            notify_owner(phone, ad, xidmet, customer, company_id)
            time.sleep(1)
            send_whatsapp(phone,
                f"🎁 *Xüsusi təklifimiz:*\n\n"
                f"Bu nömrəni sahibkar dostunuza göndərin — "
                f"onlara *ilk konsultasiya pulsuzdur!* 🤝\n\n"
                f"Birlikdə Azərbaycan biznesini gücləndiriririk! 💪🇦🇿")
        except Exception as e:
            print(f"Qeydiyyat xətası: {e}")


# ════════════════════════════════════════════════════════════════
# ADMIN BİLDİRİŞ
# ════════════════════════════════════════════════════════════════

def notify_owner(phone, ad, xidmet, customer, company_id="garant"):
    if not OWNER_PHONE:
        return
    segment, emoji = get_segment(customer)
    cnt   = customer.get("muraciet_sayi", 1) if customer else 1
    stxt  = {"vip":   f"👑 VIP ({cnt}-ci müraciət)",
              "sadiq": f"⭐ SADİQ ({cnt}-ci müraciət)",
              "yeni":  "🆕 YENİ MÜŞTƏRİ"}.get(segment, "")
    company_info = COMPANIES.get(company_id, COMPANIES["garant"])
    now = baku_now()
    send_whatsapp(OWNER_PHONE,
        f"🔔 *YENİ MÜRACİƏT — {company_info['name']}*\n"
        f"{'─'*30}\n"
        f"👤 Ad: {ad}\n"
        f"📞 Tel: +{phone}\n"
        f"💼 Xidmət: {xidmet}\n"
        f"🏢 Şirkət: {company_info['emoji']} {company_info['name']}\n"
        f"🏷️ {stxt}\n"
        f"⏰ {now.strftime('%d.%m.%Y %H:%M')} (Bakı)\n"
        f"{'─'*30}\n"
        f"💡 Ən qısa zamanda zəng edin!")


# ════════════════════════════════════════════════════════════════
# XOŞ GƏLDİN
# ════════════════════════════════════════════════════════════════

def send_welcome(phone):
    customer       = get_customer(phone)
    greeting       = get_time_greeting()
    segment, emoji = get_segment(customer)

    if customer and customer.get("ad"):
        ad = customer["ad"]
        company_id = user_company.get(phone, customer.get("company", "garant"))
        company_info = COMPANIES.get(company_id, COMPANIES["garant"])

        if segment == "vip":
            msg = (f"👑 *{greeting}, əziz {ad}!*\n\n"
                   f"Ən dəyərli dostlarımızdansınız! "
                   f"Xüsusi müraciətiniz üçün birbaşa mütəxəssisimizlə əlaqə quracağıq! 🌟")
        elif segment == "sadiq":
            msg = (f"⭐ *{greeting}, hörmətli {ad}!*\n\n"
                   f"Yenidən görməkdən çox məmnun olduq! "
                   f"Ailəmizin bir parçasısınız. 🏠")
        else:
            msg = (f"🤖 *{greeting}, {ad}!*\n\n"
                   f"Yenidən görməkdən çox məmnun oldum! "
                   f"Nə ilə kömək edə bilərəm? 😊")

        send_whatsapp(phone, msg)
        time.sleep(0.8)

    else:
        # Yeni müştəri — 4 şirkəti tanıt
        send_whatsapp(phone,
            f"✨ *{greeting}!*\n\n"
            f"Sizi xoş qarşılayırıq! Biz çoxsahəli AI dəstək platformasıyıq.\n\n"
            f"🏢 *Garant Consulting* — Mühasibatlıq & Maliyyə\n"
            f"🤖 *AI İdarəetmə Sistemləri* — Süni intellekt & Avtomatlaşdırma\n"
            f"🧠 *NAT Psixologiya* — Psixoloji dəstək & Terapiya\n"
            f"🛋️ *Casa Eleganza* — Premium Mebel & İnteryer\n\n"
            f"Hansı şirkət ilə əlaqə qurmaq istərsiniz? 👇")
        time.sleep(0.8)

    # Şirkət seçim buttonları (2 mesajda 4 button)
    send_buttons(phone,
        "Şirkət seçin:",
        [{"id": "btn_company_garant", "title": "🏢 Garant Consulting"},
         {"id": "btn_company_ai",     "title": "🤖 AI Sistemlər"},
         {"id": "btn_company_nat",    "title": "🧠 NAT Psixologiya"}])
    time.sleep(0.5)
    send_buttons(phone,
        "Və ya:",
        [{"id": "btn_company_casa",  "title": "🛋️ Casa Eleganza"},
         {"id": "btn_back_main",     "title": "🔄 Əsas Menyu"},
         {"id": "btn_back_main",     "title": "🔄 Menyu"}])

    save_customer(phone)


# ════════════════════════════════════════════════════════════════
# SLASH KOMANDALAR
# ════════════════════════════════════════════════════════════════

def handle_slash_command(phone, text):
    cmd = text.strip().lower()
    company_id = user_company.get(phone, "garant")

    if cmd in ["/", "/menu", "/start", "/help", "/kömək", "/menyu"]:
        send_welcome(phone)
        return True

    if cmd in ["/garant", "/muhasibat", "/mühasibat"]:
        user_company[phone] = "garant"
        menu = get_company_menu("garant")
        send_buttons(phone, menu["body"], menu["buttons"])
        return True

    if cmd in ["/ai", "/aibot", "/texnologiya"]:
        user_company[phone] = "ai_system"
        menu = get_company_menu("ai_system")
        send_buttons(phone, menu["body"], menu["buttons"])
        return True

    if cmd in ["/nat", "/psixologiya", "/terapiya"]:
        user_company[phone] = "nat_psixologiya"
        menu = get_company_menu("nat_psixologiya")
        send_buttons(phone, menu["body"], menu["buttons"])
        return True

    if cmd in ["/casa", "/mebel", "/eleganza"]:
        user_company[phone] = "casa_eleganza"
        menu = get_company_menu("casa_eleganza")
        send_buttons(phone, menu["body"], menu["buttons"])
        return True

    return False


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

        user_text = ""

        # ── Mesaj tipi ──────────────────────────────────────────
        if mtype == "text":
            user_text = msg["text"]["body"]

        elif mtype == "interactive" and msg["interactive"]["type"] == "button_reply":
            btn_id = msg["interactive"]["button_reply"]["id"]

            # ── Şirkət seçim buttonları ────────────────────────
            company_map = {
                "btn_company_garant": "garant",
                "btn_company_ai":     "ai_system",
                "btn_company_nat":    "nat_psixologiya",
                "btn_company_casa":   "casa_eleganza",
            }

            if btn_id in company_map:
                selected = company_map[btn_id]
                user_company[phone] = selected
                company_info = COMPANIES[selected]
                # Şirkət menyusunu göndər
                menu = get_company_menu(selected)
                send_whatsapp(phone,
                    f"{company_info['emoji']} *{company_info['name']}* seçdiniz!\n"
                    f"_{company_info['subtitle']}_")
                time.sleep(0.5)
                send_buttons(phone, menu["body"], menu["buttons"])
                save_customer(phone, stage="şirkət seçdi", company=selected)
                return jsonify({"status": "ok"})

            elif btn_id == "btn_back_main":
                send_welcome(phone)
                return jsonify({"status": "ok"})

            # ── Şirkət alt-menyular ────────────────────────────
            elif handle_company_submenu(phone, btn_id):
                return jsonify({"status": "ok"})

            # ── Köhnə uyğunluq buttonları ──────────────────────
            else:
                legacy_map = {
                    "btn_xidmetler": "Xidmətləriniz və qiymətlər haqqında məlumat verin",
                    "btn_qeydiyyat": "Müraciət etmək istəyirəm",
                    "btn_elaqe":     "Əlaqə məlumatlarınızı verin",
                }
                user_text = legacy_map.get(btn_id, btn_id)

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

        if not user_text:
            return jsonify({"status": "ok"})

        # ── İlk dəfə yazır ──────────────────────────────────────
        if phone not in conversations:
            conversations[phone] = []
            if phone not in welcomed_phones:
                welcomed_phones.add(phone)
                send_welcome(phone)
                if user_text.startswith("/"):
                    time.sleep(0.5)
                    handle_slash_command(phone, user_text)
                return jsonify({"status": "ok"})

        # ── Slash komanda ────────────────────────────────────────
        if user_text.startswith("/"):
            if handle_slash_command(phone, user_text):
                return jsonify({"status": "ok"})

        # ── AI cavabı ────────────────────────────────────────────
        ai_reply = get_ai_response(phone, user_text)
        process_registration(ai_reply, phone)
        send_whatsapp(phone, ai_reply)

        # Şirkət seçilməyibsə, seçim xatırladılması
        if phone not in user_company or user_company.get(phone) not in COMPANIES:
            company_id = user_company.get(phone, "garant")
            if company_id not in COMPANIES:
                time.sleep(1)
                send_buttons(phone,
                    "💡 Sürətli naviqasiya üçün şirkət seçin:",
                    [{"id": "btn_company_garant", "title": "🏢 Garant"},
                     {"id": "btn_company_ai",     "title": "🤖 AI Sistemlər"},
                     {"id": "btn_company_nat",    "title": "🧠 Psixologiya"}])

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
<title>Multi-Brand AI — Admin Panel</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #0f0f1a; color: #e2e8f0; }
.header { background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
          padding: 20px 30px; display:flex; justify-content:space-between; align-items:center;
          border-bottom: 1px solid #2d3748; }
.header h1 { font-size: 22px; background: linear-gradient(90deg,#667eea,#764ba2,#f093fb);
             -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.header p  { font-size: 12px; opacity:.6; color:#a0aec0; }
.company-tabs { display:flex; gap:8px; padding:16px 24px;
                background:#13131f; border-bottom:1px solid #2d3748; flex-wrap:wrap; }
.tab { padding:8px 16px; border-radius:20px; font-size:12px; font-weight:600;
       cursor:pointer; border:1px solid #2d3748; color:#a0aec0; background:transparent;
       transition:all 0.2s; }
.tab.active, .tab:hover { background:linear-gradient(135deg,#667eea,#764ba2); color:white; border-color:transparent; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
         gap:16px; padding:24px; }
.stat-card { background:#1a1a2e; border-radius:12px; padding:20px;
             border:1px solid #2d3748; text-align:center; }
.stat-n { font-size:36px; font-weight:700;
          background:linear-gradient(135deg,#667eea,#764ba2);
          -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.stat-l { font-size:12px; color:#718096; margin-top:4px; }
.company-stat { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
                gap:16px; padding:0 24px 24px; }
.cs-card { border-radius:12px; padding:16px; border:1px solid; }
.cs-card.garant     { background:#0d1b2a; border-color:#2b6cb0; }
.cs-card.ai_system  { background:#1a0d2e; border-color:#805ad5; }
.cs-card.nat        { background:#0d2a1b; border-color:#2f855a; }
.cs-card.casa       { background:#2a1d0d; border-color:#b7791f; }
.cs-name { font-size:14px; font-weight:700; margin-bottom:8px; }
.cs-num  { font-size:28px; font-weight:700; }
.section { padding:0 24px 24px; }
.section h2 { font-size:16px; font-weight:700; margin-bottom:14px; color:#e2e8f0; }
table { width:100%; background:#1a1a2e; border-radius:12px; overflow:hidden;
        border:1px solid #2d3748; border-collapse:collapse; }
th { background:#13131f; color:#a0aec0; padding:12px 16px; text-align:left;
     font-size:12px; font-weight:600; border-bottom:1px solid #2d3748; }
td { padding:12px 16px; font-size:13px; border-bottom:1px solid #2d3748; color:#e2e8f0; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:#13131f; }
.badge { display:inline-block; padding:3px 10px; border-radius:20px;
         font-size:11px; font-weight:600; }
.badge.yeni   { background:#1a3a2a; color:#68d391; }
.badge.elanib { background:#1a2a4a; color:#63b3ed; }
.badge.vip    { background:#3a2a00; color:#f6ad55; }
.badge.sadiq  { background:#2a1a4a; color:#b794f4; }
.company-badge { padding:2px 8px; border-radius:10px; font-size:10px; font-weight:700; }
.cb-garant  { background:#1a3a5a; color:#63b3ed; }
.cb-ai      { background:#2a1a5a; color:#b794f4; }
.cb-nat     { background:#1a3a2a; color:#68d391; }
.cb-casa    { background:#3a2a0a; color:#f6ad55; }
.refresh { background:linear-gradient(135deg,#667eea,#764ba2); color:white; border:none;
           padding:8px 18px; border-radius:8px; cursor:pointer; font-size:13px; }
.bar { height:16px; background:linear-gradient(90deg,#667eea,#764ba2);
       border-radius:4px; display:inline-block; min-width:4px; }
</style>
</head>
<body>
<div class="header">
  <div><h1>🚀 Multi-Brand AI Platform</h1><p>4 Şirkət — 1 Güclü Sistem</p></div>
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

<div class="company-stat">
  <div class="cs-card garant">
    <div class="cs-name">🏢 Garant Consulting</div>
    <div class="cs-num">{{ garant_sayi }}</div>
    <div style="font-size:11px;color:#718096;margin-top:4px;">müraciət</div>
  </div>
  <div class="cs-card ai_system">
    <div class="cs-name">🤖 AI Sistemlər</div>
    <div class="cs-num">{{ ai_sayi }}</div>
    <div style="font-size:11px;color:#718096;margin-top:4px;">müraciət</div>
  </div>
  <div class="cs-card nat">
    <div class="cs-name">🧠 NAT Psixologiya</div>
    <div class="cs-num">{{ nat_sayi }}</div>
    <div style="font-size:11px;color:#718096;margin-top:4px;">müraciət</div>
  </div>
  <div class="cs-card casa">
    <div class="cs-name">🛋️ Casa Eleganza</div>
    <div class="cs-num">{{ casa_sayi }}</div>
    <div style="font-size:11px;color:#718096;margin-top:4px;">müraciət</div>
  </div>
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
    <tr><th>#</th><th>Şirkət</th><th>Ad</th><th>Telefon</th><th>Xidmət</th><th>Status</th><th>Tarix</th></tr>
    {% for m in muracietler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>
        {% set c = m.company or 'garant' %}
        {% if c == 'garant' %}<span class="company-badge cb-garant">🏢 Garant</span>
        {% elif c == 'ai_system' %}<span class="company-badge cb-ai">🤖 AI</span>
        {% elif c == 'nat_psixologiya' %}<span class="company-badge cb-nat">🧠 NAT</span>
        {% elif c == 'casa_eleganza' %}<span class="company-badge cb-casa">🛋️ Casa</span>
        {% else %}<span class="company-badge">{{ c }}</span>{% endif %}
      </td>
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
    <tr><th>#</th><th>Şirkət</th><th>Ad</th><th>Telefon</th><th>Xidmət</th><th>Mərhələ</th><th>Say</th><th>Seqment</th></tr>
    {% for m in musteriler %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>
        {% set c = m.company or 'garant' %}
        {% if c == 'garant' %}<span class="company-badge cb-garant">🏢</span>
        {% elif c == 'ai_system' %}<span class="company-badge cb-ai">🤖</span>
        {% elif c == 'nat_psixologiya' %}<span class="company-badge cb-nat">🧠</span>
        {% elif c == 'casa_eleganza' %}<span class="company-badge cb-casa">🛋️</span>
        {% else %}—{% endif %}
      </td>
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
        return "<h2 style='color:red;padding:40px'>❌ Giriş qadağandır.</h2>", 403
    try:
        muracietler = supabase.table("muracietler").select("*").order("tarix", desc=True).limit(50).execute().data
        musteriler  = supabase.table("musteriler").select("*").order("son_muraciet", desc=True).execute().data
        bugun_str   = str(date.today())
        bugun       = sum(1 for m in muracietler if m.get("tarix","").startswith(bugun_str))
        yeni        = sum(1 for m in muracietler if m.get("status") == "yeni")
        vip_sayi    = sum(1 for m in musteriler  if m.get("muraciet_sayi",0) >= 5)
        sadiq_sayi  = sum(1 for m in musteriler  if 3 <= m.get("muraciet_sayi",0) < 5)
        funnel      = {"maraqlandı": 0, "sual verdi": 0, "şirkət seçdi": 0, "müraciət etdi": 0}
        for m in musteriler:
            s = m.get("stage", "maraqlandı")
            if s in funnel: funnel[s] += 1

        # Şirkət üzrə statistika
        garant_sayi  = sum(1 for m in muracietler if m.get("company") == "garant")
        ai_sayi      = sum(1 for m in muracietler if m.get("company") == "ai_system")
        nat_sayi     = sum(1 for m in muracietler if m.get("company") == "nat_psixologiya")
        casa_sayi    = sum(1 for m in muracietler if m.get("company") == "casa_eleganza")

        return render_template_string(ADMIN_HTML,
            muracietler=muracietler, musteriler=musteriler,
            cem_muraciet=len(muracietler), yeni_muraciet=yeni,
            cem_musteri=len(musteriler), bugun=bugun,
            vip_sayi=vip_sayi, sadiq_sayi=sadiq_sayi, funnel=funnel,
            garant_sayi=garant_sayi, ai_sayi=ai_sayi,
            nat_sayi=nat_sayi, casa_sayi=casa_sayi)
    except Exception as e:
        return f"<h3 style='padding:40px'>Xəta: {e}</h3>", 500

@app.route("/")
def home():
    return (
        "🚀 <b>Multi-Brand AI Platform</b> — Aktiv!<br><br>"
        "🏢 Garant Consulting | 🤖 AI Sistemlər | 🧠 NAT Psixologiya | 🛋️ Casa Eleganza<br><br>"
        "✅ WhatsApp Bot işləyir!"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
