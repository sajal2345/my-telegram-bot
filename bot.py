import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
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

ADMIN_ID = 7500776824
CHANNEL_ID = -1004459597302
NAGAD_NUMBER = "9856000616951329"

conn = sqlite3.connect("payments.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS sms_logs (trx_id TEXT PRIMARY KEY, amount REAL, used INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS pending_users (trx_id TEXT PRIMARY KEY, user_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, expiry_date TEXT, reminded INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('amount', '50.0')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('days', '30')")
conn.commit()


def get_setting(key: str, default: str) -> str:
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row:
        (val,) = row
        return val
    return default


def set_setting(key: str, value: str):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    async def send_invite_to_customer(bot, customer_id: int, trx_id: str, paid_amount: float = 0.0):
    try:
        days = int(get_setting("days", "30"))
        now = datetime.now()

        cursor.execute("SELECT expiry_date FROM subscriptions WHERE user_id = ?", (customer_id,))
        existing = cursor.fetchone()
        if existing:
            (old_expiry_str,) = existing
            old_expiry = datetime.fromisoformat(old_expiry_str)
            base_date = old_expiry if old_expiry > now else now
        else:
            base_date = now

        new_expiry = base_date + timedelta(days=days)
        expiry_str = new_expiry.strftime("%d-%m-%Y %I:%M %p")

        cursor.execute(
            "INSERT OR REPLACE INTO subscriptions (user_id, expiry_date, reminded) VALUES (?, ?, 0)",
            (customer_id, new_expiry.isoformat())
        )
        conn.commit()

        invite = await bot.create_chat_invite_link(chat_id=CHANNEL_ID, member_limit=1)
        await bot.send_message(
            chat_id=customer_id,
            text=(
                f"✅ Payment Verified! (TrxID: {trx_id})\n\n"
                f"📅 মেয়াদ: {days} দিন (শেষ হবে: {expiry_str})\n\n"
                "🔗 আপনার Private Channel Join Link:\n"
                f"{invite.invite_link}\n\n"
                "⚠️ এই Link একজন ব্যবহারকারী একবার ব্যবহার করতে পারবেন।"
            )
        )
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🎉 Auto-Verified!\n"
                f"Customer ID: {customer_id}\n"
                f"TrxID: {trx_id}\n"
                f"Amount: {paid_amount} Tk\n"
                f"Valid Till: {expiry_str}"
            )
        )
    except Exception as e:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Invite Link পাঠাতে সমস্যা হয়েছে (User: {customer_id}, TrxID: {trx_id}): {e}"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        cursor.execute("INSERT OR REPLACE INTO users (user_id, full_name) VALUES (?, ?)", (user.id, user.full_name))
        conn.commit()

    amount = int(float(get_setting("amount", "50.0")))
    days = int(get_setting("days", "30"))

    keyboard = [
        [InlineKeyboardButton(f"💳 Payment ({amount} Tk / {days} Days)", callback_data="payment")],
        [InlineKeyboardButton("📅 আমার মেয়াদ দেখুন (Status)", callback_data="status")]
    ]
    await update.message.reply_text(
        "Welcome to Our Online Shop!\n\n"
        "আমাদের শপে স্বাগতম।\n"
        "নিচের বাটনে ক্লিক করে পেমেন্ট সম্পন্ন করুন অথবা আপনার সাবস্ক্রিপশনের মেয়াদ দেখুন।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "payment":
        amount = int(float(get_setting("amount", "50.0")))
        days = int(get_setting("days", "30"))
        await query.edit_message_text(
            "💳 Payment Details\n\n"
            f"📱 Nagad Personal: {NAGAD_NUMBER}\n"
            f"💰 Amount: {amount} Tk (Send Money)\n"
            f"⏳ মেয়াদ: {days} দিন\n\n"
            "📌 নির্দেশনা:\n"
            f"১. উপরের নম্বরে ঠিক {amount} টাকা Send Money করুন।\n"
            "২. টাকা পাঠানোর পর আপনার Nagad Transaction ID (TrxID) টি কপি করে এখানে মেসেজ হিসেবে পাঠান (যেমন: 71A2B3C4)।"
        )
    elif query.data == "status":
        await check_user_status(query.message, query.from_user.id)
        async def check_user_status(message, user_id: int):
    cursor.execute("SELECT expiry_date FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        await message.reply_text("❌ আপনার কোনো সক্রিয় সাবস্ক্রিপশন নেই। পেমেন্ট করতে /start চাপুন।")
        return

    (expiry_str_raw,) = row
    expiry = datetime.fromisoformat(expiry_str_raw)
    now = datetime.now()
    if expiry > now:
        remaining = expiry - now
        expiry_str = expiry.strftime("%d-%m-%Y %I:%M %p")
        await message.reply_text(
            f"✅ আপনার সাবস্ক্রিপশন সক্রিয় আছে!\n"
            f"⏳ বাকি সময়: {remaining.days} দিন\n"
            f"📅 শেষ হবে: {expiry_str}"
        )
    else:
        await message.reply_text("⚠️ আপনার সাবস্ক্রিপশনের মেয়াদ শেষ হয়ে গেছে। নতুন করে জয়েন করতে /start চাপুন।")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_user_status(update.message, update.effective_user.id)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: {update.effective_user.id}")


async def setamount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/setamount 100")
        return
    try:
        new_amt = float("".join(context.args[:1]))
        if new_amt <= 0:
            raise ValueError
        set_setting("amount", str(new_amt))
        await update.message.reply_text(f"✅ পেমেন্টের পরিমাণ সফলভাবে {int(new_amt)} Tk সেট করা হয়েছে!")
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: /setamount 100")


async def setdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/setdays 30")
        return
    try:
        new_days = int("".join(context.args[:1]))
        if new_days <= 0:
            raise ValueError
        set_setting("days", str(new_days))
        await update.message.reply_text(f"✅ সাবস্ক্রিপশনের মেয়াদ {new_days} দিন সেট করা হয়েছে!")
    except ValueError:
        await update.message.reply_text("❌ সঠিক দিন লিখুন। যেমন: /setdays 30")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/broadcast আজকে বিশেষ অফার চলছে!")
        return

    msg_text = " ".join(context.args)
    cursor.execute("SELECT user_id FROM users")
    all_users = cursor.fetchall()

    sent_count = 0
    failed_count = 0
    status_msg = await update.message.reply_text(f"⏳ মোট {len(all_users)} জন কাস্টমারকে মেসেজ পাঠানো হচ্ছে...")

    for (uid,) in all_users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 নোটিশ / আপডেট\n\n{msg_text}")
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed_count += 1

    await status_msg.edit_text(
        f"✅ Broadcast সম্পন্ন!\n\n"
        f"✔️ সফল হয়েছে: {sent_count} জন\n"
        f"❌ ব্যর্থ হয়েছে: {failed_count} জন"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    (total_users,) = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM sms_logs WHERE used = 1")
    total_sales, total_income = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE expiry_date > ?", (datetime.now().isoformat(),))
    (active_subs,) = cursor.fetchone()

    await update.message.reply_text(
        "📊 বটের বর্তমান হিসাব (Stats)\n\n"
        f"👥 মোট ব্যবহারকারী: {total_users} জন\n"
        f"✅ সক্রিয় সাবস্ক্রাইবার: {active_subs} জন\n"
        f"🛒 মোট সফল পেমেন্ট: {total_sales} টি\n"
        f"💰 মোট আয়: {int(total_income)} Tk"
    )
    async def check_user_status(message, user_id: int):
    cursor.execute("SELECT expiry_date FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        await message.reply_text("❌ আপনার কোনো সক্রিয় সাবস্ক্রিপশন নেই। পেমেন্ট করতে /start চাপুন।")
        return

    (expiry_str_raw,) = row
    expiry = datetime.fromisoformat(expiry_str_raw)
    now = datetime.now()
    if expiry > now:
        remaining = expiry - now
        expiry_str = expiry.strftime("%d-%m-%Y %I:%M %p")
        await message.reply_text(
            f"✅ আপনার সাবস্ক্রিপশন সক্রিয় আছে!\n"
            f"⏳ বাকি সময়: {remaining.days} দিন\n"
            f"📅 শেষ হবে: {expiry_str}"
        )
    else:
        await message.reply_text("⚠️ আপনার সাবস্ক্রিপশনের মেয়াদ শেষ হয়ে গেছে। নতুন করে জয়েন করতে /start চাপুন।")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_user_status(update.message, update.effective_user.id)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: {update.effective_user.id}")


async def setamount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/setamount 100")
        return
    try:
        new_amt = float("".join(context.args[:1]))
        if new_amt <= 0:
            raise ValueError
        set_setting("amount", str(new_amt))
        await update.message.reply_text(f"✅ পেমেন্টের পরিমাণ সফলভাবে {int(new_amt)} Tk সেট করা হয়েছে!")
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: /setamount 100")


async def setdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/setdays 30")
        return
    try:
        new_days = int("".join(context.args[:1]))
        if new_days <= 0:
            raise ValueError
        set_setting("days", str(new_days))
        await update.message.reply_text(f"✅ সাবস্ক্রিপশনের মেয়াদ {new_days} দিন সেট করা হয়েছে!")
    except ValueError:
        await update.message.reply_text("❌ সঠিক দিন লিখুন। যেমন: /setdays 30")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/broadcast আজকে বিশেষ অফার চলছে!")
        return

    msg_text = " ".join(context.args)
    cursor.execute("SELECT user_id FROM users")
    all_users = cursor.fetchall()

    sent_count = 0
    failed_count = 0
    status_msg = await update.message.reply_text(f"⏳ মোট {len(all_users)} জন কাস্টমারকে মেসেজ পাঠানো হচ্ছে...")

    for (uid,) in all_users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 নোটিশ / আপডেট\n\n{msg_text}")
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed_count += 1

    await status_msg.edit_text(
        f"✅ Broadcast সম্পন্ন!\n\n"
        f"✔️ সফল হয়েছে: {sent_count} জন\n"
        f"❌ ব্যর্থ হয়েছে: {failed_count} জন"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    (total_users,) = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM sms_logs WHERE used = 1")
    total_sales, total_income = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE expiry_date > ?", (datetime.now().isoformat(),))
    (active_subs,) = cursor.fetchone()

    await update.message.reply_text(
        "📊 বটের বর্তমান হিসাব (Stats)\n\n"
        f"👥 মোট ব্যবহারকারী: {total_users} জন\n"
        f"✅ সক্রিয় সাবস্ক্রাইবার: {active_subs} জন\n"
        f"🛒 মোট সফল পেমেন্ট: {total_sales} টি\n"
        f"💰 মোট আয়: {int(total_income)} Tk"
    )
