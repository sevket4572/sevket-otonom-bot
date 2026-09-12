import os
import asyncio
import threading
import sqlite3
import datetime
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import pytz
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
# 1. RENDER PORT VE CANLILIK KORUMASI (HEALTH CHECK)
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Sekreter Multi-Tool Engine Aktif!")

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=start_health_server, daemon=True).start()

# -------------------------------------------------------------
# 2. ÇOK KULLANICILI SQLITE VERİTABANI
# -------------------------------------------------------------
DB_FILE = "sekreter_v2.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        # Kullanıcı tercihleri
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                city TEXT DEFAULT 'Istanbul',
                daily_report INTEGER DEFAULT 0,
                report_time TEXT DEFAULT '08:30'
            )
        """)
        # Notlar
        c.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                created_at TEXT
            )
        """)
        # Görevler
        c.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task TEXT,
                status TEXT DEFAULT 'PENDING'
            )
        """)
        # Fiyat Alarmları
        c.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                symbol TEXT,
                target_price REAL,
                direction TEXT,
                status TEXT DEFAULT 'ACTIVE'
            )
        """)
        conn.commit()

init_db()

# -------------------------------------------------------------
# 3. VERİ & API YARDIMCILARI
# -------------------------------------------------------------
def fetch_crypto():
    symbols = [("BTCUSDT", "Bitcoin"), ("ETHUSDT", "Ethereum"), ("SOLUSDT", "Solana"), ("BNBUSDT", "BNB")]
    lines = ["🪙 *Kripto Piyasası (Canlı)*\n"]
    for sym, name in symbols:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=4).json()
            lines.append(f"• *{name} ({sym[:3]}):* ${float(r['price']):,.2f}")
        except Exception:
            lines.append(f"• *{name}:* Veri alınamadı")
    return "\n".join(lines)

def fetch_fiat():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=4).json()
        rates = r.get("rates", {})
        usd_try = rates.get("TRY", 0)
        eur_usd = rates.get("EUR", 1)
        eur_try = usd_try / eur_usd if eur_usd else 0
        gbp_usd = rates.get("GBP", 1)
        gbp_try = usd_try / gbp_usd if gbp_usd else 0
        
        return (
            "💵 *Döviz Piyasası*\n\n"
            f"• *USD / TRY:* ₺{usd_try:.2f}\n"
            f"• *EUR / TRY:* ₺{eur_try:.2f}\n"
            f"• *GBP / TRY:* ₺{gbp_try:.2f}"
        )
    except Exception:
        return "⚠️ Döviz kurlarına erişilemedi."

def fetch_weather(city="Istanbul"):
    try:
        geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=tr&format=json", timeout=4).json()
        if not geo.get("results"):
            return f"❌ '{city}' bulunamadı."
        res = geo["results"][0]
        lat, lon, name = res["latitude"], res["longitude"], res["name"]
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=4).json()
        cw = w.get("current_weather", {})
        return (
            f"🌤 *Hava Durumu: {name}*\n\n"
            f"• Sıcaklık: *{cw.get('temperature', 'N/A')}°C*\n"
            f"• Rüzgar Hızı: *{cw.get('windspeed', 'N/A')} km/s*"
        )
    except Exception:
        return "⚠️ Hava durumu servisine ulaşılamadı."

# -------------------------------------------------------------
# 4. ARAYÜZ (İNTERAKTİF BUTONLAR)
# -------------------------------------------------------------
def get_main_panel():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Kripto", callback_data="btn_crypto"),
            InlineKeyboardButton("💵 Döviz", callback_data="btn_fiat"),
        ],
        [
            InlineKeyboardButton("📝 Notlar", callback_data="btn_notes"),
            InlineKeyboardButton("📋 Görevler", callback_data="btn_todos"),
        ],
        [
            InlineKeyboardButton("🌤 Hava Durumu", callback_data="btn_weather"),
            InlineKeyboardButton("⚙️ Otonom Rapor", callback_data="btn_toggle_report"),
        ],
        [
            InlineKeyboardButton("ℹ️ Tüm Komutlar", callback_data="btn_help")
        ]
    ])

# -------------------------------------------------------------
# 5. KOMUTLAR
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()

    text = (
        "⚡️ *Sekreter Otonom Asistan Terminali*\n\n"
        "Gelişmiş piyasa takibi, zamanlayıcılar, kalıcı veritabanı ve genel araçlar devrede. "
        "Doğrudan butonlardan veya komut listesinden yönetebilirsiniz."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_panel())
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_panel())

async def piyasa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{fetch_crypto()}\n\n{fetch_fiat()}", parse_mode="Markdown")

async def hava(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Istanbul"
    await update.message.reply_text(fetch_weather(city), parse_mode="Markdown")

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
        await update.message.reply_text("Kullanım: `/hesapla 25*4 + 10`", parse_mode="Markdown")
        return
    allowed = set("0123456789+-*/()., ")
    if not set(expr).issubset(allowed):
        await update.message.reply_text("❌ Geçersiz karakter! Yalnızca temel matematiksel ifadeler desteklenir.")
        return
    try:
        clean_expr = expr.replace(",", ".")
        res = eval(clean_expr, {"__builtins__": None}, {})
        await update.message.reply_text(f"🔢 *Sonuç:* `{res}`", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("❌ Hatalı matematik ifadesi.")

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
        await update.message.reply_text(f"✅ *{dk} dakika* sonra bildirim kuruldu:\n🎯 '{mesaj}'", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("Kullanım: `/hatirlat <dakika> <mesaj>`\nÖrn: `/hatirlat 10 Su iç`", parse_mode="Markdown")

async def alarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].upper()
        target = float(context.args[1])
        symbol = f"{coin}USDT"
        
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=4).json()
        current = float(r["price"])
        direction = "ABOVE" if target > current else "BELOW"

        with get_db() as conn:
            conn.execute(
                "INSERT INTO price_alerts (user_id, chat_id, symbol, target_price, direction, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
                (update.effective_user.id, update.effective_chat.id, symbol, target, direction)
            )
            conn.commit()

        txt_dir = "üzerine çıktığında" if direction == "ABOVE" else "altına indiğinde"
        await update.message.reply_text(
            f"🎯 *Alarm Kaydedildi!*\n\n• Parite: *{symbol}*\n• Şimdiki Değer: *${current:,.2f}*\n• Hedef Değer: *${target:,.2f}*\n\nFiyat hedefe vardığında otomatik bildirim gelecektir.",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("Kullanım: `/alarm <coin> <hedef_fiyat>`\nÖrn: `/alarm btc 68000`", parse_mode="Markdown")

async def not_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Kullanım: `/not_al <metin>`", parse_mode="Markdown")
        return
    uid = update.effective_user.id
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_db() as conn:
        conn.execute("INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)", (uid, text, now))
        conn.commit()
    await update.message.reply_text("📌 Not kalıcı veritabanına kaydedildi!", parse_mode="Markdown")

async def notlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with get_db() as conn:
        rows = conn.execute("SELECT id, content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
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
    await update.message.reply_text("✅ Görev listenize eklendi!", parse_mode="Markdown")

async def render_todos(message, uid):
    with get_db() as conn:
        rows = conn.execute("SELECT id, task FROM todos WHERE user_id = ? AND status = 'PENDING'", (uid,)).fetchall()
    if not rows:
        await message.reply_text("📋 Bekleyen hiçbir göreviniz yok!")
        return
    buttons = [[InlineKeyboardButton(f"✅ Bitir: {r['task'][:22]}", callback_data=f"done_todo_{r['id']}")] for r in rows]
    await message.reply_text("📋 *Aktif Görevleriniz:*\n(Tamamlamak için tıklayın)", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def gorevler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await render_todos(update.message, update.effective_user.id)

async def oto_rapor_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with get_db() as conn:
        row = conn.execute("SELECT daily_report FROM users WHERE user_id = ?", (uid,)).fetchone()
        current = row["daily_report"] if row else 0
        new_val = 0 if current == 1 else 1
        conn.execute("UPDATE users SET daily_report = ? WHERE user_id = ?", (new_val, uid))
        conn.commit()
    status_str = "AÇILDI 🟢" if new_val == 1 else "KAPATILDI 🔴"
    msg = f"⚙️ Günlük otomatik sabah raporu: *{status_str}*"
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown")

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Sekreter Multi-Tool Komut Listesi:*\n\n"
        "• `/start` - Ana butonlu paneli açar\n"
        "• `/piyasa` - Kripto ve döviz piyasalarını listeler\n"
        "• `/alarm <coin> <fiyat>` - Otonom fiyat alarmı kurar\n"
        "• `/hatirlat <dk> <mesaj>` - Geri sayım sayacı kurar\n"
        "• `/hava <şehir>` - Anlık hava durumunu çeker\n"
        "• `/qr <yazı veya link>` - Taranabilir QR kod üretir\n"
        "• `/hesapla <işlem>` - Matematiksel işlem yapar\n"
        "• `/not_al <not>` & `/notlar` - Kalıcı not yöneticisi\n"
        "• `/gorev_ekle <iş>` & `/gorevler` - Butonlu görev listesi\n"
        "• `/oto_rapor` - Otomatik sabah brifingini açar/kapatır"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown")

# -------------------------------------------------------------
# 6. BUTON YÖNLENDİRİCİSİ
# -------------------------------------------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "btn_crypto":
        await query.message.reply_text(fetch_crypto(), parse_mode="Markdown")
    elif data == "btn_fiat":
        await query.message.reply_text(fetch_fiat(), parse_mode="Markdown")
    elif data == "btn_weather":
        await query.message.reply_text(fetch_weather("Istanbul"), parse_mode="Markdown")
    elif data == "btn_notes":
        await notlar(update, context)
    elif data == "btn_todos":
        await render_todos(query.message, uid)
    elif data == "btn_toggle_report":
        await oto_rapor_toggle(update, context)
    elif data == "btn_help":
        await yardim(update, context)
    elif data.startswith("done_todo_"):
        tid = int(data.split("_")[2])
        with get_db() as conn:
            conn.execute("UPDATE todos SET status = 'COMPLETED' WHERE id = ? AND user_id = ?", (tid, uid))
            conn.commit()
        await query.message.reply_text("✅ Görev tamamlandı!")
        await render_todos(query.message, uid)

# -------------------------------------------------------------
# 7. PERİYODİK OTONOM GÖREVLER (BACKGROUND WORKER)
# -------------------------------------------------------------
async def price_alert_worker(context: ContextTypes.DEFAULT_TYPE):
    with get_db() as conn:
        alerts = conn.execute("SELECT id, chat_id, symbol, target_price, direction FROM price_alerts WHERE status = 'ACTIVE'").fetchall()
    
    for a in alerts:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={a['symbol']}", timeout=3).json()
            curr = float(r["price"])
            triggered = False
            if a["direction"] == "ABOVE" and curr >= a["target_price"]:
                triggered = True
            elif a["direction"] == "BELOW" and curr <= a["target_price"]:
                triggered = True

            if triggered:
                await context.bot.send_message(
                    chat_id=a["chat_id"],
                    text=f"🚨 *FİYAT ALARMI!*\n\nParite: *{a['symbol']}*\nGüncel: *${curr:,.2f}*\nHedef: *${a['target_price']:,.2f}*",
                    parse_mode="Markdown"
                )
                with get_db() as conn:
                    conn.execute("UPDATE price_alerts SET status = 'DONE' WHERE id = ?", (a["id"],))
                    conn.commit()
        except Exception:
            pass

# -------------------------------------------------------------
# 8. ÇALIŞTIRMA MOTORU
# -------------------------------------------------------------
async def run_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    # Komut bağlamaları
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("piyasa", piyasa))
    app.add_handler(CommandHandler("hava", hava))
    app.add_handler(CommandHandler("qr", qr_kod))
    app.add_handler(CommandHandler("hesapla", hesapla))
    app.add_handler(CommandHandler("hatirlat", hatirlat))
    app.add_handler(CommandHandler("alarm", alarm_command))
    app.add_handler(CommandHandler("not_al", not_al))
    app.add_handler(CommandHandler("notlar", notlar))
    app.add_handler(CommandHandler("gorev_ekle", gorev_ekle))
    app.add_handler(CommandHandler("gorevler", gorevler))
    app.add_handler(CommandHandler("oto_rapor", oto_rapor_toggle))
    app.add_handler(CommandHandler("yardim", yardim))

    app.add_handler(CallbackQueryHandler(callback_handler))

    # 45 saniyede bir otonom fiyat kontrolü
    if app.job_queue:
        app.job_queue.run_repeating(price_alert_worker, interval=45, first=10)

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
