import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Render Port Koruması
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Otonom bot aktif!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# Bellek Deposu
user_notes = {}
user_todos = {}

# Yardımcı Fonksiyonlar
def get_crypto_prices():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd"
        res = requests.get(url, timeout=5).json()
        btc = res["bitcoin"]["usd"]
        eth = res["ethereum"]["usd"]
        sol = res["solana"]["usd"]
        return f"🪙 *Kripto Piyasası*\n\n• *BTC:* ${btc:,.2f}\n• *ETH:* ${eth:,.2f}\n• *SOL:* ${sol:,.2f}"
    except Exception:
        return "⚠️ Piyasa verisi şu an alınamadı."

# Komut Yöneticileri
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📊 Piyasa", callback_data="btn_piyasa"),
            InlineKeyboardButton("📝 Notlarım", callback_data="btn_notlar"),
        ],
        [
            InlineKeyboardButton("✅ Görevler", callback_data="btn_gorevler"),
            InlineKeyboardButton("ℹ️ Yardım", callback_data="btn_yardim"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = (
        "🤖 *Şevket Otonom Bot'a Hoş Geldiniz!*\n\n"
        "Menü butonlarını kullanabilir veya doğrudan komut gönderebilirsiniz."
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "btn_piyasa":
        await query.message.reply_text(get_crypto_prices(), parse_mode="Markdown")
    elif query.data == "btn_notlar":
        notes = user_notes.get(uid, [])
        text = "📌 *Kayıtlı Notlarınız:*\n\n" + ("\n".join([f"• {n}" for n in notes]) if notes else "Kayıtlı notunuz yok.")
        await query.message.reply_text(text, parse_mode="Markdown")
    elif query.data == "btn_gorevler":
        todos = user_todos.get(uid, [])
        text = "📋 *Yapılacaklar Listeniz:*\n\n" + ("\n".join([f"[{i+1}] {t}" for i, t in enumerate(todos)]) if todos else "Aktif görev bulunmuyor.")
        await query.message.reply_text(text, parse_mode="Markdown")
    elif query.data == "btn_yardim":
        await yardim(update, context)

async def hatirlat_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"⏰ *Zaman Doldu!*\n\nHatırlatıcı: *{job.data}*",
        parse_mode="Markdown",
    )

async def hatirlat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dakika = float(context.args[0])
        mesaj = " ".join(context.args[1:]) or "Süre doldu!"
        saniye = int(dakika * 60)
        context.job_queue.run_once(hatirlat_callback, saniye, chat_id=update.effective_chat.id, data=mesaj)
        await update.message.reply_text(f"✅ *{dakika} dakika* sonra bildirim kuruldu:\n'{mesaj}'", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("Kullanım: `/hatirlat <dakika> <mesaj>`\nÖrn: `/hatirlat 10 Su iç`", parse_mode="Markdown")

async def piyasa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_crypto_prices(), parse_mode="Markdown")

async def not_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    not_metni = " ".join(context.args)
    if not not_metni:
        await update.message.reply_text("Kullanım: `/not_al <metin>`", parse_mode="Markdown")
        return
    uid = update.effective_user.id
    user_notes.setdefault(uid, []).append(not_metni)
    await update.message.reply_text("📌 Not kaydedildi!", parse_mode="Markdown")

async def notlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    notes = user_notes.get(uid, [])
    text = "📌 *Kayıtlı Notlarınız:*\n\n" + ("\n".join([f"• {n}" for n in notes]) if notes else "Kayıtlı not bulunmuyor.")
    await update.message.reply_text(text, parse_mode="Markdown")

async def gorev_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gorev = " ".join(context.args)
    if not gorev:
        await update.message.reply_text("Kullanım: `/gorev_ekle <görev adı>`", parse_mode="Markdown")
        return
    uid = update.effective_user.id
    user_todos.setdefault(uid, []).append(gorev)
    await update.message.reply_text("✅ Görev listenize eklendi!", parse_mode="Markdown")

async def gorevler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    todos = user_todos.get(uid, [])
    text = "📋 *Yapılacaklar Listeniz:*\n\n" + ("\n".join([f"[{i+1}] {t}" for i, t in enumerate(todos)]) if todos else "Listeniz boş.")
    await update.message.reply_text(text, parse_mode="Markdown")

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rehber = (
        "📖 *Otonom Bot Komut Kılavuzu:*\n\n"
        "• `/start` - Menüyü ve kontrol butonlarını açar\n"
        "• `/hatirlat <dk> <not>` - Belirttiğiniz süre dolunca alarm çalar\n"
        "• `/piyasa` - Anlık BTC, ETH ve SOL fiyatlarını çeker\n"
        "• `/not_al <yazı>` - Hafızaya not ekler\n"
        "• `/notlar` - Kaydettiğiniz tüm notları getirir\n"
        "• `/gorev_ekle <iş>` - Yapılacaklar listenize görev ekler\n"
        "• `/gorevler` - Bekleyen görevlerinizi listeler"
    )
    if update.message:
        await update.message.reply_text(rehber, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(rehber, parse_mode="Markdown")

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hatirlat", hatirlat))
    app.add_handler(CommandHandler("piyasa", piyasa))
    app.add_handler(CommandHandler("not_al", not_al))
    app.add_handler(CommandHandler("notlar", notlar))
    app.add_handler(CommandHandler("gorev_ekle", gorev_ekle))
    app.add_handler(CommandHandler("gorevler", gorevler))
    app.add_handler(CommandHandler("yardim", yardim))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
