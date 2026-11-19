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

ADMIN_ID = 5653843581
NAGAD_NUMBER = "\n\n9856000616951329\n"

PRODUCTS = {
    "p1": {"name": "Premium Call/Live Record\n(নভেম্বর ২০২৬)", "channel_id": -1004459597302, "auto_link": True},
    "p2": {"name": "Tango Videos", "channel_id": -1002829173374, "auto_link": True},
    "p3": {"name": "Chamet Videos", "channel_id": -1002609377697, "auto_link": True},
    "p4": {"name": "বাচ্চাদের ভিডিও/Cp Vides", "channel_id": None, "auto_link": False},
}

conn = sqlite3.connect("payments.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS sms_logs (trx_id TEXT PRIMARY KEY, amount REAL, used INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS pending_users (trx_id TEXT PRIMARY KEY, user_id INTEGER, product_key TEXT DEFAULT 'p1')")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, selected_product TEXT DEFAULT '')")
cursor.execute("CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, expiry_date TEXT, reminded INTEGER DEFAULT 0, channel_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('amount_p1', '50.0')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('amount_group', '100.0')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('days', '500')")
conn.commit()

for col_sql in [
    "ALTER TABLE pending_users ADD COLUMN product_key TEXT DEFAULT 'p1'",
    "ALTER TABLE users ADD COLUMN selected_product TEXT DEFAULT ''",
    "ALTER TABLE subscriptions ADD COLUMN channel_id INTEGER"
]:
    try:
        cursor.execute(col_sql)
    except sqlite3.OperationalError:
        pass
conn.commit()


def get_setting(key: str, default: str) -> str:
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row:
        (val,) = row
        return str(val)
    return default


def set_setting(key: str, value: str):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()


def get_product_price(prod_key: str) -> float:
    if prod_key == "p1":
        return float(get_setting("amount_p1", "50.0"))
    return float(get_setting("amount_group", "100.0"))


def get_cart_total(cart_str: str):
    if not cart_str or not isinstance(cart_str, str):
        return [], 0.0
    keys = [k.strip() for k in cart_str.split(",") if k.strip() in PRODUCTS]
    unique_keys = list(dict.fromkeys(keys))
    total = sum(get_product_price(k) for k in unique_keys)
    return unique_keys, total

async def send_invite_to_customer(bot, customer_id: int, trx_id: str, paid_amount: float = 0.0, cart_str: str = "p1"):
    try:
        keys, _ = get_cart_total(cart_str)
        if not keys:
            keys = ["p1"]

        days = int(get_setting("days", "30"))
        now = datetime.now()
        new_expiry = now + timedelta(days=days)
        expiry_str = new_expiry.strftime("%d-%m-%Y %I:%M %p")

        auto_links_text = []
        has_p4 = False
        bought_names = []

        for k in keys:
            product = PRODUCTS[k]
            bought_names.append(product["name"])

            if product["auto_link"] and product["channel_id"]:
                target_ch = product["channel_id"]
                cursor.execute(
                    "INSERT OR REPLACE INTO subscriptions (user_id, expiry_date, reminded, channel_id) VALUES (?, ?, 0, ?)",
                    (customer_id, new_expiry.isoformat(), target_ch)
                )
                conn.commit()
                invite = await bot.create_chat_invite_link(chat_id=target_ch, member_limit=1)
                auto_links_text.append(f"🔗 {product['name']}:\n{invite.invite_link}")
            else:
                has_p4 = True

        msg = (
            f"✅ Payment Verified! (TrxID: {trx_id})\n"
            f"📦 প্যাকেজসমূহ: {', '.join(bought_names)}\n"
            f"📅 মেয়াদ: {days} দিন (শেষ হবে: {expiry_str})\n\n"
        )
        if auto_links_text:
            msg += "\n\n".join(auto_links_text) + "\n\n⚠️ প্রতিটি লিংক শুধুমাত্র একবার ব্যবহারযোগ্য।"
        if has_p4:
            msg += f"\n\n⏳ {PRODUCTS['p4']['name']}-এর লিংক অ্যাডমিন শীঘ্রই আপনাকে ইনবক্সে পাঠিয়ে দেবেন।"

        await bot.send_message(chat_id=customer_id, text=msg)

        admin_msg = (
            f"🎉 নতুন পেমেন্ট ভেরিফাই হয়েছে!\n"
            f"👤 Customer ID: {customer_id}\n"
            f"📦 প্যাকেজ: {', '.join(bought_names)}\n"
            f"🧾 TrxID: {trx_id}\n"
            f"💰 Amount: {paid_amount} Tk"
        )
        if has_p4:
            admin_msg += f"\n\n🔔 লিংক পাঠান:\n/sendlink {customer_id} https://your-link"

        await bot.send_message(chat_id=ADMIN_ID, text=admin_msg)

    except Exception as e:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Invite Link পাঠাতে সমস্যা হয়েছে (User: {customer_id}, TrxID: {trx_id}): {e}"
        )

def build_product_keyboard(selected_keys: list) -> InlineKeyboardMarkup:
    p1_price = int(get_product_price("p1"))
    group_price = int(get_product_price("p2"))

    prices = {"p1": p1_price, "p2": group_price, "p3": group_price, "p4": group_price}
    keyboard = []

    for k in ["p1", "p2", "p3", "p4"]:
        icon = "✅" if k in selected_keys else "⬜"
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {PRODUCTS[k]['name']} - {prices[k]} Tk",
                callback_data=f"toggle_{k}"
            )
        ])

    total_price = sum(prices[k] for k in selected_keys)
    if selected_keys:
        keyboard.append([
            InlineKeyboardButton(f"🔰 পেমেন্ট করুন total({total_price} Tk) 🔰", callback_data="checkout")
        ])

    return InlineKeyboardMarkup(keyboard)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("toggle_"):
        prod_key = query.data.replace("toggle_", "")
        cursor.execute("SELECT selected_product FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        (current_cart,) = row if row else ("",)
        selected_keys, _ = get_cart_total(current_cart)

        if prod_key in selected_keys:
            selected_keys.remove(prod_key)
        else:
            selected_keys.append(prod_key)

        new_cart_str = ",".join(selected_keys)
        cursor.execute("UPDATE users SET selected_product = ? WHERE user_id = ?", (new_cart_str, user_id))
        conn.commit()

        await query.edit_message_reply_markup(reply_markup=build_product_keyboard(selected_keys))

    elif query.data == "back_to_products":
        cursor.execute("SELECT selected_product FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        (current_cart,) = row if row else ("",)
        selected_keys, _ = get_cart_total(current_cart)

        await query.edit_message_text(
            "🕵️ <b>Welcome to Detective Ai!</b>\n\n"
            "🔰 নিচের Group থেকে আপনার পছন্দের group-টি সিলেক্ট করুন। তারপর <b>🔰পেমেন্ট করুন🔰</b> বাটনে ক্লিক করুন:",
            reply_markup=build_product_keyboard(selected_keys),
            parse_mode="HTML"
        )

    elif query.data == "checkout":
        cursor.execute("SELECT selected_product FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        (current_cart,) = row if row else ("",)
        selected_keys, total_amount = get_cart_total(current_cart)

        if not selected_keys:
            await query.message.reply_text("⚠️ দয়া করে আগে অন্তত ১টি Group সিলেক্ট করুন!")
            return

        names = "\n".join([f"• <b>{PRODUCTS[k]['name']}</b>" for k in selected_keys])
        keyboard = [
            [
                InlineKeyboardButton("🪪 বিকাশ (bKash)", callback_data="pay_bkash"),
                InlineKeyboardButton("🪪 নগদ (Nagad)", callback_data="pay_nagad")
            ],
            [
                InlineKeyboardButton("🔙 Back to Products", callback_data="back_to_products")
            ]
        ]
        await query.edit_message_text(
            f"🛒 <b>আপনার সিলেক্ট করা group সমূহ:</b>\n\n{names}\n\n"
            f"💰 <b>সর্বমোট মূল্য: {int(total_amount)} Tk</b>\n\n"
            "💳 পেমেন্ট মাধ্যম সিলেক্ট করুন:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    elif query.data in ["pay_nagad", "pay_bkash"]:
        cursor.execute("SELECT selected_product FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        (current_cart,) = row if row else ("",)
        selected_keys, total_amount = get_cart_total(current_cart)

        if not selected_keys:
            await query.message.reply_text("⚠️ কোনো প্রোডাক্ট সিলেক্ট করা নেই। আবার /start চাপুন।")
            return

        days = int(get_setting("days", "500"))
        names = ", ".join([PRODUCTS[k]["name"] for k in selected_keys])

        if query.data == "pay_nagad":
            video_id = "BAACAgUAAxkBAAIBpmr9jeQYdMyAWRC_demevFaqCsLEAAIEKgACwTHxV5Nqev6BuXZNPQQ"
            caption_text = (
                f"💳 <b>Nagad Payment Details:</b>\n (🌟পেমেন্ট এর আগে উপরের ভিডিওটি অবশ্যই দেখবেন)\n\n"
                f"📦 প্যাকেজ: <b>{names}</b>\n\n"
                f"📱 Nagad Personal: <code>{NAGAD_NUMBER.strip()}</code>\n\n"
                f"💰 মোট দাম: <b>{int(total_amount)} Tk</b> (Send Money)\n"
                f"⏳ মেয়াদ: <b>{days} দিন</b>\n\n"
                "📌 <b>নির্দেশনা:</b>\n"
                "১. টাকা পাঠানোর পর আপনার Transaction ID (TrxID) টি কপি করে মেসেজ করুন (যেমন:<code>71A2B3C4</code>)।"
            )
        else:
            video_id = "BAACAgUAAxkBAAIBrWr9kzpL0zPNbtDNhZVHZd4jeFDlAAINKgACwTHxVzN1OjuVRxvtPQQ"
            caption_text = (
                f"💳 <b>BKash Payment Details:</b>\n(⚠️ আমাদের নিজস্ব বিকাশ একাউন্ট নেই। তাই উপরের ভিডিওটি দেখে আপনার বিকাশ একাউন্ট থেকে আমাদের নগদ একাউন্টে সেন্ড মানি করুন)\n\n"
                f"📦 প্যাকেজ: <b>{names}</b>\n\n"
                f"📱 Nagad Personal: <code>{NAGAD_NUMBER.strip()}</code>\n"
                f"💰 মোট দাম: <b>{int(total_amount)} Tk</b> (Send Money)\n"
                f"⏳ মেয়াদ: <b>{days} দিন</b>\n\n"
                "📌 <b>নির্দেশনা:</b>\n"
                "১. টাকা পাঠানোর পর আপনার Transaction ID (TrxID) টি কপি করে মেসেজ করুন (যেমন: <code>9H7G6F5D</code>)।"
            )

        try:
            await query.message.reply_video(video=video_id, caption=caption_text, parse_mode="HTML")
        except Exception as e:
            await query.message.reply_text(caption_text, parse_mode="HTML")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Video Error: {e}")

    elif query.data == "status":
        await check_user_status(query.message, user_id)
               
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name, selected_product) VALUES (?, ?, '')", (user.id, user.full_name))
        cursor.execute("UPDATE users SET full_name = ?, selected_product = '' WHERE user_id = ?", (user.full_name, user.id))
        conn.commit()

    await update.message.reply_text(
        "🕵️ <b>Welcome to Detective Ai!</b>\n\n"
        "🔰 যে গ্রুপ নিতে চান সেটায় ক্লিক করে নির্বাচন করুন। এর পর Checkout বাটনে ক্লিক করুন:",
        reply_markup=build_product_keyboard([]),
        parse_mode="HTML" 
    )

async def check_user_status(message, user_id: int):
    cursor.execute("SELECT expiry_date FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        await message.reply_text("❌ আপনি কোনো গ্রুপ কিনেন নি তাই সাবস্ক্রিপশন নেই। গ্রুপ কিনতে /start চাপুন।")
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


async def setamount1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/setamount1 50")
        return
    try:
        new_amt = float("".join(context.args[:1]))
        if new_amt <= 0:
            raise ValueError
        set_setting("amount_p1", str(new_amt))
        await update.message.reply_text(f"✅ Product 1-এর দাম সফলভাবে {int(new_amt)} Tk সেট করা হয়েছে!")
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: /setamount1 50")


async def setamount2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/setamount2 100")
        return
    try:
        new_amt = float("".join(context.args[:1]))
        if new_amt <= 0:
            raise ValueError
        set_setting("amount_group", str(new_amt))
        await update.message.reply_text(f"✅ বাকি ৩টি প্রোডাক্টের দাম একসাথে {int(new_amt)} Tk সেট করা হয়েছে!")
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: /setamount2 100")


async def sendlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("ব্যবহার করুন:\n/sendlink <user_id> <link>")
        return
    try:
        target_user_id = int("".join(context.args[:1]))
        link_text = " ".join(context.args[1:])
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎉 অ্যাডমিন আপনার {PRODUCTS['p4']['name']}-এর লিংক পাঠিয়েছেন:\n\n🔗 {link_text}"
        )
        await update.message.reply_text(f"✅ ইউজার ({target_user_id})-কে লিংক পাঠানো হয়েছে!")
    except Exception as e:
        await update.message.reply_text(f"❌ এরর: {e}")


async def setdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার করুন:\n/setdays 500")
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


async def handle_trx_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None or not update.message or not update.message.text:
        return

    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)", (user.id, user.full_name))
    conn.commit()

    cursor.execute("SELECT selected_product FROM users WHERE user_id = ?", (user.id,))
    u_row = cursor.fetchone()
    (cart_str,) = u_row if u_row else ("",)
    selected_keys, required_amount = get_cart_total(cart_str)

    if not selected_keys:
        await update.message.reply_text("⚠️ আপনি কোনো প্রোডাক্ট সিলেক্ট করেননি। আগে /start দিয়ে প্রোডাক্ট সিলেক্ট করুন।")
        return

    text = update.message.text.strip().upper()
    if " " in text or len(text) < 6 or len(text) > 15 or not text.isalnum():
        await update.message.reply_text("❌ সঠিক Transaction ID (TrxID) পাঠান। উদাহরণ: 71A2B3C4")
        return

    trx_id = text
    cursor.execute("SELECT amount, used FROM sms_logs WHERE trx_id = ?", (trx_id,))
    row = cursor.fetchone()

    if row:
        amount, used = row
        if used == 1:
            await update.message.reply_text("⚠️ এই Transaction ID টি ইতিমধ্যে ব্যবহার করা হয়েছে!")
            return
        if amount < required_amount:
            await update.message.reply_text(
                f"❌ কম টাকা পাঠানো হয়েছে ({int(amount)} Tk)। আপনার সিলেক্ট করা প্যাকেজগুলোর জন্য মোট {int(required_amount)} Tk পাঠান।"
            )
            return

        cursor.execute("UPDATE sms_logs SET used = 1 WHERE trx_id = ?", (trx_id,))
        conn.commit()
        await send_invite_to_customer(context.bot, user.id, trx_id, amount, cart_str)
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO pending_users (trx_id, user_id, product_key) VALUES (?, ?, ?)",
            (trx_id, user.id, cart_str)
        )
        conn.commit()
        await update.message.reply_text(
            f"⏳ আপনার TrxID ({trx_id}) জমা হয়েছে।\n"
            "Nagad থেকে কনফার্মেশন SMS পাওয়ার সাথে সাথেই ভেরিফাই হয়ে যাবে!"
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
    await context.bot.copy_message(chat_id=ADMIN_ID, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
    await update.message.reply_text("আপনার Payment Screenshot পেয়েছি। TrxID টেক্সট হিসেবে পাঠালে দ্রুত অটো-ভেরিফাই হবে।")


async def get_video_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and update.message.video:
        file_id = update.message.video.file_id
        await update.message.reply_text(f"Video File ID:\n\n`{file_id}`", parse_mode="Markdown")


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and context.args:
        target_id = int("".join(context.args[:1]))
        cart_str = "".join(context.args[1:2]) if len(context.args) > 1 else "p1"
        _, total_amt = get_cart_total(cart_str)
        await send_invite_to_customer(context.bot, target_id, "MANUAL_ADMIN", total_amt, cart_str)


async def subscription_checker(bot):
    while True:
        try:
            now = datetime.now()
            cursor.execute("SELECT user_id, expiry_date, reminded, channel_id FROM subscriptions")
            rows = cursor.fetchall()

            for user_id, expiry_str, reminded, ch_id in rows:
                expiry = datetime.fromisoformat(expiry_str)
                target_ch = ch_id if ch_id else PRODUCTS["p1"]["channel_id"]

                if now >= expiry:
                    try:
                        await bot.ban_chat_member(chat_id=target_ch, user_id=user_id)
                        await bot.unban_chat_member(chat_id=target_ch, user_id=user_id)
                        await bot.send_message(
                            chat_id=user_id,
                            text="⚠️ আপনার সাবস্ক্রিপশনের মেয়াদ শেষ হয়ে যাওয়ায় চ্যানেল থেকে রিমুভ করা হয়েছে। পুনরায় জয়েন করতে /start চাপুন।"
                        )
                        await bot.send_message(
                            chat_id=ADMIN_ID,
                            text=f"🚫 মেয়াদ শেষ হওয়ায় ইউজার {user_id}-কে চ্যানেল থেকে রিমুভ করা হয়েছে।"
                        )
                    except Exception as e:
                        print(f"Kick error for {user_id}: {e}")

                    cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
                    conn.commit()

                elif (expiry - now) <= timedelta(days=2) and reminded == 0:
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text="⏳ রিমাইন্ডার: আপনার সাবস্ক্রিপশনের মেয়াদ আর ২ দিনেরও কম বাকি আছে! রিনিউ করতে /start চাপুন।"
                        )
                        cursor.execute("UPDATE subscriptions SET reminded = 1 WHERE user_id = ?", (user_id,))
                        conn.commit()
                    except Exception:
                        pass
        except Exception as e:
            print(f"Subscription checker error: {e}")

        await asyncio.sleep(3600)


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
        cursor.execute("INSERT INTO sms_logs (trx_id, amount, used) VALUES (?, ?, 0)", (trx_id, amount))
        conn.commit()

    cursor.execute("SELECT user_id, product_key FROM pending_users WHERE trx_id = ?", (trx_id,))
    pending = cursor.fetchone()

    if pending:
        customer_id, cart_str = pending
        _, required_amount = get_cart_total(cart_str)

        if amount >= required_amount:
            cursor.execute("UPDATE sms_logs SET used = 1 WHERE trx_id = ?", (trx_id,))
            cursor.execute("DELETE FROM pending_users WHERE trx_id = ?", (trx_id,))
            conn.commit()

            ptb_app = request.app["ptb_app"]
            await send_invite_to_customer(ptb_app.bot, customer_id, trx_id, amount, cart_str)

    return web.json_response({"status": "ok", "trx_id": trx_id})


async def health_check(request):
    return web.Response(text="Bot & Subscription Server Running!")

async def main():
    ptb_app = Application.builder().token(TOKEN).build()

    ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CommandHandler("status", status_cmd))
    ptb_app.add_handler(CommandHandler("myid", myid))
    ptb_app.add_handler(CommandHandler("approve", approve))
    ptb_app.add_handler(CommandHandler("setamount1", setamount1))
    ptb_app.add_handler(CommandHandler("setamount2", setamount2))
    ptb_app.add_handler(CommandHandler("sendlink", sendlink))
    ptb_app.add_handler(CommandHandler("setdays", setdays))
    ptb_app.add_handler(CommandHandler("broadcast", broadcast))
    ptb_app.add_handler(CommandHandler("stats", stats))
    ptb_app.add_handler(CallbackQueryHandler(button))
    ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trx_id))
    ptb_app.add_handler(MessageHandler(filters.VIDEO, get_video_id))
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

    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.updater.start_polling()

    asyncio.create_task(subscription_checker(ptb_app.bot))

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
