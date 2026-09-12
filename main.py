import os
import asyncio
import threading
import sqlite3
import datetime
import urllib.parse
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# -------------------------------------------------------------
# 1. RENDER PORT & HEALTH CHECK
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Sekreter Asistan 7/24 Aktif!")

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=start_health_server, daemon=True).start()

# -------------------------------------------------------------
# 2. VERİTABANI (Kullanıcılar, Notlar, Görevler)
# -------------------------------------------------------------
DB_FILE = "sekreter_final.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        # Botu başlatan kullanıcıları takip eden tablo
        c.execute("""
            CREATE TABLE IF NOT EXISTS active_users (
                chat_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                first_name TEXT,
                last_seen TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task TEXT,
                status TEXT DEFAULT 'PENDING'
            )
        """)
        conn.commit()

init_db()

def register_user(chat_id, user_id, first_name):
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO active_users (chat_id, user_id, first_name, last_seen) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, first_name, now)
        )
        conn.commit()

# -------------------------------------------------------------
# 3. VERİ SERVİSLERİ
# -------------------------------------------------------------
def fetch_fiat():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        rates = r.get("rates", {})
        usd_try = rates.get("TRY", 0)
        eur_usd = rates.get("EUR", 1)
        eur_try = usd_try / eur_usd if eur_usd else 0
        gbp_usd = rates.get("GBP", 1)
        gbp_try = usd_try / gbp_usd if gbp_usd else 0

        return (
            "💵 *Güncel Döviz Kurları*\n\n"
            f"• *Dolar (USD):* ₺{usd_try:.2f}\n"
            f"• *Euro (EUR):* ₺{eur_try:.2f}\n"
            f"• *Sterlin (GBP):* ₺{gbp_try:.2f}"
        )
    except Exception:
        return "⚠️ Döviz kurlarına şu an erişilemiyor."

def fetch_weather(city="Istanbul"):
    try:
        geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=tr&format=json", timeout=5).json()
        if not geo.get("results"):
            return f"❌ '{city}' şehri bulunamadı."
        res = geo["results"][0]
        lat, lon, name = res["latitude"], res["longitude"], res["name"]
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=5).json()
        cw = w.get("current_weather", {})
        return (
            f"🌤 *Hava Durumu: {name}*\n\n"
            f"• Sıcaklık: *{cw.get('temperature', 'N/A')}°C*\n"
            f"• Rüzgar Hızı: *{cw.get('windspeed', 'N/A')} km/s*"
        )
    except Exception:
        return "⚠️ Hava durumu servisine ulaşılamadı."

def fetch_wiki(query):
    try:
        url = f"https://tr.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}"
        headers = {"User-Agent": "TelegramBot/1.0"}
        r = requests.get(url, headers=headers, timeout=5).json()
        if "extract" in r:
            return f"📚 *{r.get('title')}*\n\n{r.get('extract')}"
        return "❌ Bu konu hakkında özet bilgi bulunamadı."
    except Exception:
        return "⚠️ Bilgi servisine ulaşılamadı."

# -------------------------------------------------------------
# 4. KONTROL PANELİ
# -------------------------------------------------------------
def get_main_panel():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Döviz Kurları", callback_data="btn_fiat"),
            InlineKeyboardButton("🌤 Hava Durumu", callback_data="btn_weather"),
        ],
        [
            InlineKeyboardButton("📝 Notlarım", callback_data="btn_notes"),
            InlineKeyboardButton("📋 Görevlerim", callback_data="btn_todos"),
        ],
        [
            InlineKeyboardButton("📖 Komut Rehberi", callback_data="btn_help")
        ]
    ])

# -------------------------------------------------------------
# 5. KOMUT VE İŞLEYİCİLER
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    first_name = update.effective_user.first_name or "Dostum"
    register_user(chat_id, uid, first_name)

    text = (
        f"⚡️ *Sekreter Otonom Asistan Terminali*\n\n"
        f"Selam {first_name}! Görevlerin, notların ve operasyonel araçların hazır. "
        "Aşağıdaki panelden işlemleri yönetebilirsin."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_panel())
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_panel())

async def doviz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(fetch_fiat(), parse_mode="Markdown")

async def hava(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Istanbul"
    await update.message.reply_text(fetch_weather(city), parse_mode="Markdown")

async def bilgi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Kullanım: `/bilgi <konu>`\nÖrn: `/bilgi Atatürk`", parse_mode="Markdown")
        return
    await update.message.reply_text(fetch_wiki(query), parse_mode="Markdown")

async def qr_kod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = " ".join(context.args)
    if not content:
        await update.message.reply_text("Kullanım: `/qr <metin veya link>`", parse_mode="Markdown")
        return
    encoded = urllib.parse.quote(content)
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded}"
    await update.message.reply_photo(photo=qr_url, caption=f"🏁 QR Kodunuz:\n`{content}`", parse_mode="Markdown")

async def hesapla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = "".join(context.args)
    if not expr:
        await update.message.reply_text("Kullanım: `/hesapla 125 * 8`", parse_mode="Markdown")
        return
    allowed = set("0123456789+-*/()., ")
    if not set(expr).issubset(allowed):
        await update.message.reply_text("❌ Yalnızca temel matematiksel ifadeler desteklenir.")
        return
    try:
        clean_expr = expr.replace(",", ".")
        res = eval(clean_expr, {"__builtins__": None}, {})
        await update.message.reply_text(f"🔢 *Sonuç:* `{res}`", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ Hatalı işlem.")

async def hatirlat_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"⏰ *ZAMAN DOLDU!*\n\n🔔 Bildirim: *{job.data}*",
        parse_mode="Markdown"
    )

async def hatirlat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dk = float(context.args[0])
        mesaj = " ".join(context.args[1:]) or "Süre doldu!"
        saniye = int(dk * 60)
        context.job_queue.run_once(hatirlat_callback, saniye, chat_id=update.effective_chat.id, data=mesaj)
        await update.message.reply_text(f"✅ *{dk} dakika* sonra alarm kuruldu:\n🎯 '{mesaj}'", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("Kullanım: `/hatirlat <dakika> <mesaj>`\nÖrn: `/hatirlat 10 Su iç`", parse_mode="Markdown")

async def not_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Kullanım: `/not_al <kaydedilecek not>`", parse_mode="Markdown")
        return
    uid = update.effective_user.id
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_db() as conn:
        conn.execute("INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)", (uid, text, now))
        conn.commit()
    await update.message.reply_text("📌 Not kalıcı olarak kaydedildi!", parse_mode="Markdown")

async def notlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with get_db() as conn:
        rows = conn.execute("SELECT content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
    if not rows:
        await update.message.reply_text("📌 Kayıtlı notunuz yok.", parse_mode="Markdown")
    else:
        text = "📌 *Son Notlarınız:*\n\n" + "\n".join([f"• {r['content']} _({r['created_at']})_" for r in rows])
        await update.message.reply_text(text, parse_mode="Markdown")

async def gorev_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = " ".join(context.args)
    if not task:
        await update.message.reply_text("Kullanım: `/gorev_ekle <görev adı>`", parse_mode="Markdown")
        return
    uid = update.effective_user.id
    with get_db() as conn:
        conn.execute("INSERT INTO todos (user_id, task, status) VALUES (?, ?, 'PENDING')", (uid, task))
        conn.commit()
    await update.message.reply_text("✅ Görev eklendi!", parse_mode="Markdown")

async def render_todos(message, uid):
    with get_db() as conn:
        rows = conn.execute("SELECT id, task FROM todos WHERE user_id = ? AND status = 'PENDING'", (uid,)).fetchall()
    if not rows:
        await message.reply_text("📋 Bekleyen hiçbir göreviniz yok!")
        return
    buttons = [[InlineKeyboardButton(f"✅ Bitir: {r['task'][:24]}", callback_data=f"done_todo_{r['id']}")] for r in rows]
    await message.reply_text("📋 *Aktif Görevleriniz:*\n(Tamamlanan görevi silmek için dokunun)", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def gorevler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await render_todos(update.message, update.effective_user.id)

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Sekreter Asistan Komutları:*\n\n"
        "• `/start` - Kontrol panelini açar\n"
        "• `/doviz` - Güncel piyasa döviz kurları\n"
        "• `/hava <şehir>` - Şehir hava durumu raporu\n"
        "• `/bilgi <konu>` - Wikipedia hızlı özeti\n"
        "• `/hatirlat <dk> <mesaj>` - Geri sayım alarmı kurar\n"
        "• `/qr <yazı veya link>` - Taranabilir karekod üretir\n"
        "• `/hesapla <işlem>` - Hızlı hesap makinesi\n"
        "• `/not_al <not>` & `/notlar` - Kalıcı not yöneticisi\n"
        "• `/gorev_ekle <iş>` & `/gorevler` - Butonlu görev listesi"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "btn_fiat":
        await query.message.reply_text(fetch_fiat(), parse_mode="Markdown")
    elif data == "btn_weather":
        await query.message.reply_text(fetch_weather("Istanbul"), parse_mode="Markdown")
    elif data == "btn_notes":
        await notlar(update, context)
    elif data == "btn_todos":
        await render_todos(query.message, uid)
    elif data == "btn_help":
        await yardim(update, context)
    elif data.startswith("done_todo_"):
        tid = int(data.split("_")[2])
        with get_db() as conn:
            conn.execute("DELETE FROM todos WHERE id = ? AND user_id = ?", (tid, uid))
            conn.commit()
        await query.message.reply_text("✅ Görev tamamlandı!")
        await render_todos(query.message, uid)

async def echo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_chat.id, update.effective_user.id, update.effective_user.first_name or "Dostum")
    await update.message.reply_text("⚙️ İşlem yapmak için menüyü veya `/yardim` komutunu kullanabilirsiniz.", reply_markup=get_main_panel())

# -------------------------------------------------------------
# 6. OTONOM SELAM & HATIRLATMA MOTORU (BACKGROUND WORKER)
# -------------------------------------------------------------
async def periodic_checkin_job(context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcılara periyodik olarak kendini hatırlatır."""
    messages = [
        "👋 Selam! Arada bir kendimi hatırlatayım dedim, yardımcı olabileceğim bir iş veya not var mı?",
        "⚡️ Merhaba! Görev listeni kontrol etmek veya yeni bir hatırlatıcı kurmak ister misin?",
        "🤖 Selam! Sistemler aktif, her şey yolunda. Bir komut veya hesaplama gerekirse buradayım."
    ]
    with get_db() as conn:
        users = conn.execute("SELECT chat_id, first_name FROM active_users").fetchall()
    
    for user in users:
        try:
            msg = random.choice(messages)
            await context.bot.send_message(
                chat_id=user["chat_id"],
                text=msg,
                reply_markup=get_main_panel()
            )
        except Exception:
            pass

# -------------------------------------------------------------
# 7. MOTOR
# -------------------------------------------------------------
async def run_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("doviz", doviz))
    app.add_handler(CommandHandler("hava", hava))
    app.add_handler(CommandHandler("bilgi", bilgi))
    app.add_handler(CommandHandler("qr", qr_kod))
    app.add_handler(CommandHandler("hesapla", hesapla))
    app.add_handler(CommandHandler("hatirlat", hatirlat))
    app.add_handler(CommandHandler("not_al", not_al))
    app.add_handler(CommandHandler("notlar", notlar))
    app.add_handler(CommandHandler("gorev_ekle", gorev_ekle))
    app.add_handler(CommandHandler("gorevler", gorevler))
    app.add_handler(CommandHandler("yardim", yardim))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))

    # Otonom bildirim: Her 6 saatte bir (21600 saniye) selam verip kendini hatırlatır
    if app.job_queue:
        app.job_queue.run_repeating(periodic_checkin_job, interval=21600, first=10)


    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        await asyncio.sleep(3600)

def main():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

if __name__ == "__main__":
    main()

