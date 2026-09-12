import os
import asyncio
import threading
import sqlite3
import datetime
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

# ==========================================
# 1. RENDER PORT & HEALTH CHECK SUNUCUSU
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Sevket Otonom Bot 7/24 Aktif!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. SQLITE VERİTABANI YÖNETİMİ (KALICI HAFIZA)
# ==========================================
DB_FILE = "bot_database.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Notlar Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content TEXT,
                created_at TEXT
            )
        """)
        # Görevler Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task TEXT,
                status TEXT
            )
        """)
        # Fiyat Alarmları Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                symbol TEXT,
                target_price REAL,
                condition TEXT,
                status TEXT
            )
        """)
        conn.commit()

init_db()

# ==========================================
# 3. VERİ ÇEKME & SERVİSLER
# ==========================================
def get_crypto_summary():
    try:
        symbols = [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL"), ("BNBUSDT", "BNB")]
        lines = ["🪙 *Kripto Para Piyasası (Canlı)*\n"]
        for sym, name in symbols:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
            res = requests.get(url, timeout=5).json()
            p = float(res["price"])
            lines.append(f"• *{name}:* ${p:,.2f}")
        return "\n".join(lines)
    except Exception:
        return "⚠️ Kripto piyasa verisi alınamadı."

def get_fiat_summary():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=5).json()
        rates = res.get("rates", {})
        try_rate = rates.get("TRY", 0)
        eur_usd = rates.get("EUR", 1)
        eur_try = try_rate / eur_usd if eur_usd else 0
        
        return (
            "💵 *Döviz Kurları (Serbest Piyasa)*\n\n"
            f"• *USD / TRY:* ₺{try_rate:.2f}\n"
            f"• *EUR / TRY:* ₺{eur_try:.2f}"
        )
    except Exception:
        return "⚠️ Döviz kuru verisi şu an alınamadı."

def get_weather_report(city_name="Istanbul"):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=tr&format=json"
        geo_res = requests.get(geo_url, timeout=5).json()
        if not geo_res.get("results"):
            return f"❌ '{city_name}' şehri bulunamadı."
        
        loc = geo_res["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = loc["name"]
        country = loc.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_res = requests.get(weather_url, timeout=5).json()
        current = w_res.get("current_weather", {})
        temp = current.get("temperature", "N/A")
        wind = current.get("windspeed", "N/A")

        return f"🌤 *Hava Durumu: {name}, {country}*\n\n• Sıcaklık: *{temp}°C*\n• Rüzgar Hızı: *{wind} km/s*"
    except Exception:
        return "⚠️ Hava durumu servisine ulaşılamadı."

# ==========================================
# 4. KLAVYELER & MENÜLER
# ==========================================
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Kripto", callback_data="m_crypto"),
            InlineKeyboardButton("💵 Döviz", callback_data="m_fiat"),
        ],
        [
            InlineKeyboardButton("📝 Notlarım", callback_data="m_notes"),
            InlineKeyboardButton("📋 Görevler", callback_data="m_todos"),
        ],
        [
            InlineKeyboardButton("🌤 Hava Durumu", callback_data="m_weather"),
            InlineKeyboardButton("⏰ Alarmlar", callback_data="m_alerts"),
        ],
        [
            InlineKeyboardButton("📖 Komut Rehberi", callback_data="m_help")
        ]
    ])

# ==========================================
# 5. KOMUTLAR VE CALLBACK HANDLERLAR
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *Şevket Otonom Asistan Paneline Hoş Geldiniz!*\n\n"
        "Aşağıdaki kontrol panelinden dilediğiniz işlemi başlatabilir, "
        "notlarınızı yönetebilir veya otonom alarmlar kurabilirsiniz."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def callback_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "m_main":
        await start(update, context)
    elif data == "m_crypto":
        await query.message.reply_text(get_crypto_summary(), parse_mode="Markdown")
    elif data == "m_fiat":
        await query.message.reply_text(get_fiat_summary(), parse_mode="Markdown")
    elif data == "m_weather":
        await query.message.reply_text(get_weather_report("Istanbul"), parse_mode="Markdown")
    elif data == "m_notes":
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT id, content FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (uid,))
            rows = c.fetchall()
        if not rows:
            await query.message.reply_text("📌 Henüz kayıtlı notunuz yok.\nEkleme: `/not_al <metin>`", parse_mode="Markdown")
        else:
            text = "📌 *Kayıtlı Notlarınız:*\n\n" + "\n".join([f"• {r[1]}" for r in rows])
            await query.message.reply_text(text, parse_mode="Markdown")
    elif data == "m_todos":
        await show_todos_interactive(query.message, uid)
    elif data == "m_alerts":
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT id, symbol, target_price, condition FROM price_alerts WHERE user_id = ? AND status = 'ACTIVE'", (uid,))
            rows = c.fetchall()
        if not rows:
            await query.message.reply_text("⏰ Aktif fiyat alarmınız bulunmuyor.\nÖrnek alarm: `/alarm btc 65000`", parse_mode="Markdown")
        else:
            text = "🔔 *Aktif Fiyat Alarmlarınız:*\n\n" + "\n".join([f"• #{r[0]} | {r[1].upper()} Hedef: ${r[2]:,.2f} ({r[3]})" for r in rows])
            await query.message.reply_text(text, parse_mode="Markdown")
    elif data == "m_help":
        await yardim(update, context)
    elif data.startswith("del_todo_"):
        todo_id = int(data.split("_")[2])
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM todos WHERE id = ? AND user_id = ?", (todo_id, uid))
            conn.commit()
        await query.message.reply_text("✅ Görev tamamlandı ve silindi!")
        await show_todos_interactive(query.message, uid)

async def show_todos_interactive(message, uid):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, task FROM todos WHERE user_id = ? AND status = 'PENDING'", (uid,))
        rows = c.fetchall()
    
    if not rows:
        await message.reply_text("📋 Bekleyen hiçbir göreviniz yok!\nGörev eklemek için: `/gorev_ekle <iş>`", parse_mode="Markdown")
        return

    text = "📋 *Aktif Yapılacaklar Listeniz:*\n(Tamamlanan görevi silmek için butonuna basabilirsiniz)\n"
    buttons = []
    for r in rows:
        btn_text = f"❌ Sil: {r[1][:20]}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"del_todo_{r[0]}")])
    
    keyboard = InlineKeyboardMarkup(buttons)
    await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

# ==========================================
# 6. ZAMAN AYARLI HATIRLATICI (JOB QUEUE)
# ==========================================
async def hatirlat_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"⏰ *ZAMAN DOLDU!*\n\n🔔 Hatırlatıcı: *{job.data}*",
        parse_mode="Markdown",
    )

async def hatirlat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dk = float(context.args[0])
        mesaj = " ".join(context.args[1:]) or "Süre doldu!"
        saniye = int(dk * 60)
        context.job_queue.run_once(hatirlat_callback, saniye, chat_id=update.effective_chat.id, data=mesaj)
        await update.message.reply_text(f"✅ *{dk} dakika* sonra bildirim kuruldu:\n🎯 '{mesaj}'", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("Kullanım: `/hatirlat <dakika> <mesaj>`\nÖrn: `/hatirlat 15 Spor yap`", parse_mode="Markdown")

# ==========================================
# 7. OTONOM KRİPTO FİYAT ALARMI (ARKAPLAN TAKİP)
# ==========================================
async def alarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].upper()
        target = float(context.args[1])
        symbol = f"{coin}USDT"
        
        # Güncel fiyatı kontrol et
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        res = requests.get(url, timeout=5).json()
        current = float(res["price"])
        condition = "ABOVE" if target > current else "BELOW"

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO price_alerts (user_id, chat_id, symbol, target_price, condition, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
                (update.effective_user.id, update.effective_chat.id, symbol, target, condition)
            )
            conn.commit()

        yon = "üzerine çıktığında" if condition == "ABOVE" else "altına indiğinde"
        await update.message.reply_text(
            f"🎯 *Alarm Kuruldu!*\n\n• Parite: *{symbol}*\n• Şimdiki Fiyat: *${current:,.2f}*\n• Hedef: *${target:,.2f}*\n\nFiyat bu seviyenin {yon} bot otomatik mesaj atacak.",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text("Kullanım: `/alarm <coin> <hedef_fiyat>`\nÖrnek: `/alarm btc 65000`", parse_mode="Markdown")

# Periyodik Takipçi (Job Queue ile 60 saniyede bir çalışır)
async def price_watcher_job(context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, chat_id, symbol, target_price, condition FROM price_alerts WHERE status = 'ACTIVE'")
        alerts = c.fetchall()

    for alert in alerts:
        aid, chat_id, sym, target, cond = alert
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
            res = requests.get(url, timeout=5).json()
            curr = float(res["price"])

            triggered = False
            if cond == "ABOVE" and curr >= target:
                triggered = True
            elif cond == "BELOW" and curr <= target:
                triggered = True

            if triggered:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚨 *FİYAT ALARMI ÇALDI!*\n\n*{sym}* hedefe ulaştı!\n• Güncel Fiyat: *${curr:,.2f}*\n• Hedefiniz: *${target:,.2f}*",
                    parse_mode="Markdown"
                )
                with sqlite3.connect(DB_FILE) as conn2:
                    c2 = conn2.cursor()
                    c2.execute("UPDATE price_alerts SET status = 'TRIGGERED' WHERE id = ?", (aid,))
                    conn2.commit()
        except Exception:
            pass

# ==========================================
# 8. DİĞER KOMUTLAR
# ==========================================
async def not_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = " ".join(context.args)
    if not metin:
        await update.message.reply_text("Kullanım: `/not_al <kaydedilecek not>`", parse_mode="Markdown")
        return
    uid = update.effective_user.id
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)", (uid, metin, now))
        conn.commit()
    await update.message.reply_text("📌 Notunuz kalıcı belleğe kaydedildi!", parse_mode="Markdown")

async def notlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT content, created_at FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (uid,))
        rows = c.fetchall()
    if not rows:
        await update.message.reply_text("📌 Kayıtlı notunuz yok.", parse_mode="Markdown")
    else:
        text = "📌 *Son Notlarınız:*\n\n" + "\n".join([f"• {r[0]} _({r[1]})_" for r in rows])
        await update.message.reply_text(text, parse_mode="Markdown")

async def gorev_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = " ".join(context.args)
    if not task:
        await update.message.reply_text("Kullanım: `/gorev_ekle <görev adı>`", parse_mode="Markdown")
        return
    uid = update.effective_user.id
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO todos (user_id, task, status) VALUES (?, ?, 'PENDING')", (uid, task))
        conn.commit()
    await update.message.reply_text("✅ Görev yapılacaklar listesine eklendi!", parse_mode="Markdown")

async def gorevler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_todos_interactive(update.message, update.effective_user.id)

async def hava(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Istanbul"
    await update.message.reply_text(get_weather_report(city), parse_mode="Markdown")

async def piyasa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_crypto_summary(), parse_mode="Markdown")

async def doviz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_fiat_summary(), parse_mode="Markdown")

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rehber = (
        "📖 *Otonom Bot Komut Kılavuzu:*\n\n"
        "• `/start` - Ana kontrol panelini açar\n"
        "• `/hatirlat <dk> <iş>` - Geri sayım sayacı kurar\n"
        "• `/alarm <coin> <fiyat>` - Otomatik fiyat alarmı kurar (Örn: `/alarm btc 64000`)\n"
        "• `/piyasa` - Kripto piyasa fiyatlarını getirir\n"
        "• `/doviz` - Dolar ve Euro kurlarını getirir\n"
        "• `/hava <şehir>` - Anlık hava durumunu çeker\n"
        "• `/not_al <metin>` - Kalıcı not kaydeder\n"
        "• `/notlar` - Kayıtlı notları listeler\n"
        "• `/gorev_ekle <iş>` - Yapılacaklar listesine iş ekler\n"
        "• `/gorevler` - Görevleri etkileşimli listeler"
    )
    if update.message:
        await update.message.reply_text(rehber, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(rehber, parse_mode="Markdown")

async def echo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.lower()
    if any(w in txt for w in ["selam", "merhaba", "sa", "hey", "naber"]):
        await update.message.reply_text("👋 Selam! Kontrol paneline erişmek için aşağıdaki butonları kullanabilirsin:", reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text("⚙️ İşlem yapmak için menüyü veya `/yardim` komutunu kullanabilirsiniz.", reply_markup=main_menu_keyboard())

# ==========================================
# 9. UYGULAMA MOTORU VE BAŞLATMA
# ==========================================
async def run_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    # Komut Kayıtları
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hatirlat", hatirlat))
    app.add_handler(CommandHandler("alarm", alarm_command))
    app.add_handler(CommandHandler("piyasa", piyasa))
    app.add_handler(CommandHandler("doviz", doviz))
    app.add_handler(CommandHandler("hava", hava))
    app.add_handler(CommandHandler("not_al", not_al))
    app.add_handler(CommandHandler("notlar", notlar))
    app.add_handler(CommandHandler("gorev_ekle", gorev_ekle))
    app.add_handler(CommandHandler("gorevler", gorevler))
    app.add_handler(CommandHandler("yardim", yardim))
    app.add_handler(CallbackQueryHandler(callback_dispatcher))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))

    # Otonom Arka Plan Taraması (Her 60 saniyede bir fiyat kontrolü yapar)
    if app.job_queue:
        app.job_queue.run_repeating(price_watcher_job, interval=60, first=10)

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


