import os
import sqlite3
import asyncio
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.environ["BOT_TOKEN"]
SECRET_KEY = "MY_SUPER_SECRET_KEY_123"
REQUIRED_AMOUNT = 50.0

ADMIN_ID = 7500776824
CHANNEL_ID = -1004459597302
NAGAD_NUMBER = "9856000616951329"

conn = sqlite3.connect("payments.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS sms_logs (
        trx_id TEXT PRIMARY KEY,
        amount REAL,
        used INTEGER DEFAULT 0
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_users (
        trx_id TEXT PRIMARY KEY,
        user_id INTEGER
    )
""")
conn.commit()


async def send_invite_to_customer(bot, customer_id: int, trx_id: str):
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1
        )
        await bot.send_message(
            chat_id=customer_id,
            text=(
                f"✅ Payment Verified! (TrxID: {trx_id})\n\n"
                "আপনার Private Channel Join Link:\n"
                f"{invite.invite_link}\n\n"
                "⚠️ এই Link একজন ব্যবহারকারী শুধুমাত্র একবার ব্যবহার করতে পারবেন।"
            )
        )
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🎉 Auto-Verified!\nCustomer ID: {customer_id}\nTrxID: {trx_id}\nAmount: {REQUIRED_AMOUNT} Tk"
        )
    except Exception as e:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Invite Link পাঠাতে সমস্যা হয়েছে (User: {customer_id}, TrxID: {trx_id}): {e}"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 Payment (50 Tk)", callback_data="payment")]
    ]
    await update.message.reply_text(
        "Welcome to Our Online Shop!\n\n"
        "আমাদের শপে স্বাগতম।\n"
        "নিচের বাটনে ক্লিক করে পেমেন্ট সম্পন্ন করুন।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "payment":
        await query.edit_message_text(
            "💳 *Payment Details*\n\n"
            f"📱 Nagad Personal: `{NAGAD_NUMBER}`\n"
            f"💰 Amount: *{int(REQUIRED_AMOUNT)} Tk* (Send Money)\n\n"
            "📌 *নির্দেশনা:*\n"
            "১. উপরের নম্বরে ঠিক *৫০ টাকা* Send Money করুন।\n"
            "২. টাকা পাঠানোর পর আপনার Nagad **Transaction ID (TrxID)** টি কপি করে এখানে মেসেজ হিসেবে পাঠান (যেমন: `71A2B3C4`)।",
            parse_mode="Markdown"
        )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: {update.effective_user.id}"
    )


async def handle_trx_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None or not update.message or not update.message.text:
        return

    text = update.message.text.strip().upper()

    if " " in text or len(text) < 6 or len(text) > 15 or not text.isalnum():
        await update.message.reply_text(
            "❌ সঠিক Transaction ID (TrxID) পাঠান। উদাহরণ: `71A2B3C4`",
            parse_mode="Markdown"
        )
        return

    trx_id = text

    cursor.execute("SELECT amount, used FROM sms_logs WHERE trx_id = ?", (trx_id,))
    row = cursor.fetchone()

    if row:
        amount, used = row
        if used == 1:
            await update.message.reply_text("⚠️ এই Transaction ID টি ইতিমধ্যে ব্যবহার করা হয়েছে!")
            return
        if amount < REQUIRED_AMOUNT:
            await update.message.reply_text(
                f"❌ কম টাকা পাঠানো হয়েছে ({amount} Tk)। অনুগ্রহ করে পুরো {int(REQUIRED_AMOUNT)} Tk পাঠান।"
            )
            return

        cursor.execute("UPDATE sms_logs SET used = 1 WHERE trx_id = ?", (trx_id,))
        conn.commit()
        await send_invite_to_customer(context.bot, user.id, trx_id)
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO pending_users (trx_id, user_id) VALUES (?, ?)",
            (trx_id, user.id)
        )
        conn.commit()
        await update.message.reply_text(
            f"⏳ আপনার TrxID (`{trx_id}`) জমা হয়েছে।\n"
            "Nagad থেকে কনফার্মেশন SMS পাওয়ার সাথে সাথেই আপনাকে অটোমেটিক Invite Link পাঠিয়ে দেওয়া হবে!",
            parse_mode="Markdown"
        )


async def payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None:
        return

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "New Payment Screenshot Received!\n\n"
            f"Customer Name: {user.full_name}\n"
            f"Username: @{user.username or 'Not available'}\n"
            f"Telegram ID: {user.id}"
        )
    )
    await context.bot.copy_message(
        chat_id=ADMIN_ID,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id
    )
    await update.message.reply_text(
        "আপনার Payment Screenshot পেয়েছি। TrxID টেক্সট হিসেবে পাঠালে দ্রুত অটো-ভেরিফাই হবে।"
    )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/approve CUSTOMER_ID")
        return
    try:
        customer_id = int(context.args[0])
        await send_invite_to_customer(context.bot, customer_id, "MANUAL_ADMIN")
        await update.message.reply_text("✅ Customer-কে Invite Link পাঠানো হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def verify_sms_endpoint(request):
    if request.method == "GET":
        secret_key = request.query.get("secret_key", "")
        trx_id = request.query.get("trx_id", "").strip().upper()
        amount_str = request.query.get("amount", "0")
    else:
        try:
            data = await request.json()
            secret_key = data.get("secret_key", "")
            trx_id = str(data.get("trx_id", "")).strip().upper()
            amount_str = str(data.get("amount", "0"))
        except Exception:
            return web.json_response({"status": "invalid json"}, status=400)

    if secret_key != SECRET_KEY:
        return web.json_response({"status": "unauthorized"}, status=403)

    try:
        amount = float(amount_str)
    except ValueError:
        amount = 0.0

    if not trx_id or amount <= 0:
        return web.json_response({"status": "bad data"}, status=400)

    cursor.execute("SELECT used FROM sms_logs WHERE trx_id = ?", (trx_id,))
    existing = cursor.fetchone()
    if not existing:
        cursor.execute(
            "INSERT INTO sms_logs (trx_id, amount, used) VALUES (?, ?, 0)",
            (trx_id, amount)
        )
        conn.commit()

    cursor.execute("SELECT user_id FROM pending_users WHERE trx_id = ?", (trx_id,))
    pending = cursor.fetchone()

    if pending and amount >= REQUIRED_AMOUNT:
        customer_id = pending[0]
        cursor.execute("UPDATE sms_logs SET used = 1 WHERE trx_id = ?", (trx_id,))
        cursor.execute("DELETE FROM pending_users WHERE trx_id = ?", (trx_id,))
        conn.commit()

        ptb_app = request.app["ptb_app"]
        await send_invite_to_customer(ptb_app.bot, customer_id, trx_id)

    return web.json_response({"status": "ok", "trx_id": trx_id})


async def health_check(request):
    return web.Response(text="Bot & Payment Server Running!")


async def main():
    ptb_app = Application.builder().token(TOKEN).build()

    ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CommandHandler("myid", myid))
    ptb_app.add_handler(CommandHandler("approve", approve))
    ptb_app.add_handler(CallbackQueryHandler(button))
    ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trx_id))
    ptb_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, payment_screenshot))

    web_app = web.Application()
    web_app["ptb_app"] = ptb_app
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/verify-sms", verify_sms_endpoint)
    web_app.router.add_post("/verify-sms", verify_sms_endpoint)

    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.updater.start_polling()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
