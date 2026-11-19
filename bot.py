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

# প্রোডাক্টের তালিকা ও চ্যানেল আইডি (এখানে আপনার আসল নাম ও চ্যানেল আইডি বসান)
PRODUCTS = {
    "p1": {"name": "Product 1 (Call Record)", "channel_id": -1004459597302, "auto_link": True},
    "p2": {"name": "Product 2", "channel_id": -1001111111111, "auto_link": True},
    "p3": {"name": "Product 3", "channel_id": -1002222222222, "auto_link": True},
    "p4": {"name": "Product 4 (Special)", "channel_id": None, "auto_link": False},
}

conn = sqlite3.connect("payments.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS sms_logs (trx_id TEXT PRIMARY KEY, amount REAL, used INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS pending_users (trx_id TEXT PRIMARY KEY, user_id INTEGER, product_key TEXT DEFAULT 'p1')")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, selected_product TEXT DEFAULT 'p1')")
cursor.execute("CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, expiry_date TEXT, reminded INTEGER DEFAULT 0, channel_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('amount_p1', '50.0')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('amount_group', '100.0')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('days', '500')")
conn.commit()

try:
    cursor.execute("ALTER TABLE pending_users ADD COLUMN product_key TEXT DEFAULT 'p1'")
except sqlite3.OperationalError:
    pass
try:
    cursor.execute("ALTER TABLE users ADD COLUMN selected_product TEXT DEFAULT 'p1'")
except sqlite3.OperationalError:
    pass
try:
    cursor.execute("ALTER TABLE subscriptions ADD COLUMN channel_id INTEGER")
except sqlite3.OperationalError:
    pass
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


def get_product_price(prod_key: str) -> float:
    if prod_key == "p1":
        return float(get_setting("amount_p1", "50.0"))
    return float(get_setting("amount_group", "100.0"))
async def send_invite_to_customer(bot, customer_id: int, trx_id: str, paid_amount: float = 0.0, prod_key: str = "p1"):
    try:
        product = PRODUCTS.get(prod_key, PRODUCTS["p1"])
        days = int(get_setting("days", "30"))
        now = datetime.now()

        if not product["auto_link"]:
            await bot.send_message(
                chat_id=customer_id,
                text=(
                    f"✅ Payment Verified! (TrxID: {trx_id})\n"
                    f"📦 প্যাকেজ: {product['name']}\n\n"
                    "⏳ আপনার পেমেন্ট সফলভাবে ভেরিফাই হয়েছে। অ্যাডমিন খুব শীঘ্রই আপনাকে এই প্রোডাক্টের লিংকটি পাঠিয়ে দেবেন।"
                )
            )
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🔔 **নতুন অর্ডার - লিংক পাঠান (Product 4)**\n\n"
                    f"👤 Customer ID: `{customer_id}`\n"
                    f"🧾 TrxID: `{trx_id}`\n"
                    f"💰 Amount: {paid_amount} Tk\n\n"
                    f"👉 লিংক পাঠাতে নিচের কমান্ডটি কপি করে লিংকসহ পাঠান:\n"
                    f"`/sendlink {customer_id} https://your-link-here`"
                ),
                parse_mode="Markdown"
            )
            return

        target_channel_id = product["channel_id"]
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
            "INSERT OR REPLACE INTO subscriptions (user_id, expiry_date, reminded, channel_id) VALUES (?, ?, 0, ?)",
            (customer_id, new_expiry.isoformat(), target_channel_id)
        )
        conn.commit()

        invite = await bot.create_chat_invite_link(chat_id=target_channel_id, member_limit=1)
        await bot.send_message(
            chat_id=customer_id,
            text=(
                f"✅ Payment Verified! (TrxID: {trx_id})\n"
                f"📦 প্যাকেজ: {product['name']}\n"
                f"📅 মেয়াদ: {days} দিন (শেষ হবে: {expiry_str})\n\n"
                "🔗 আপনার Private Channel Join Link:\n"
                f"{invite.invite_link}\n\n"
                "⚠️ এই Link একজন ব্যবহারকারী একবার ব্যবহার করতে পারবেন।"
            )
        )
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🎉 Auto-Verified ({product['name']})!\n"
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
        cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)", (user.id, user.full_name))
        cursor.execute("UPDATE users SET full_name = ? WHERE user_id = ?", (user.full_name, user.id))
        conn.commit()

    p1_price = int(get_product_price("p1"))
    group_price = int(get_product_price("p2"))

    keyboard = [
        [InlineKeyboardButton(f"1️⃣ {PRODUCTS['p1']['name']} - {p1_price} Tk", callback_data="select_p1")],
        [InlineKeyboardButton(f"2️⃣ {PRODUCTS['p2']['name']} - {group_price} Tk", callback_data="select_p2")],
        [InlineKeyboardButton(f"3️⃣ {PRODUCTS['p3']['name']} - {group_price} Tk", callback_data="select_p3")],
        [InlineKeyboardButton(f"4️⃣ {PRODUCTS['p4']['name']} - {group_price} Tk", callback_data="select_p4")],
        [InlineKeyboardButton("📅 মেয়াদ দেখুন (Status)", callback_data="status")]
    ]
    await update.message.reply_text(
        "🕵️ Welcome to Detective Ai!\n\n"
        "🔰 নিচের তালিকা থেকে আপনার পছন্দের প্রোডাক্টটি সিলেক্ট করুন:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("select_"):
        prod_key = query.data.split("_")
        cursor.execute("UPDATE users SET selected_product = ? WHERE user_id = ?", (prod_key, user_id))
        conn.commit()

        product = PRODUCTS[prod_key]
        amount = int(get_product_price(prod_key))

        keyboard = [
            [
                InlineKeyboardButton("🪪 বিকাশ (bKash)", callback_data=f"pay_bkash_{prod_key}"),
                InlineKeyboardButton("🪪 নগদ (Nagad)", callback_data=f"pay_nagad_{prod_key}")
            ]
        ]
        await query.message.reply_text(
            f"📦 সিলেক্টেড প্যাকেজ: **{product['name']}**\n"
            f"💰 পরিশোধযোগ্য মূল্য: **{amount} Tk**\n\n"
            "💳 আপনি কোন মাধ্যমে পেমেন্ট করতে চান তা সিলেক্ট করুন:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data.startswith("pay_nagad_"):
        prod_key = query.data.split("_")
        amount = int(get_product_price(prod_key))
        days = int(get_setting("days", "500"))
        product = PRODUCTS[prod_key]

        caption_text = (
            f"💳 Payment Details ({product['name']})\n(🌟পেমেন্ট এর আগে উপরের ভিডিওটি অবশ্যই দেখবেন)\n\n"
            f"📱 Nagad Personal: {NAGAD_NUMBER}\n"
            f"💰 দাম: {amount} Tk (Send Money)\n"
            f"⏳ মেয়াদ: {days} দিন\n\n"
            "📌 নির্দেশনা:\n"
            "১. টাকা পাঠানোর পর আপনার Transaction ID (TrxID) টি কপি করে মেসেজ করুন (যেমন: 71A2B3C4)।\n"
        )

        try:
            await query.message.reply_video(
                video="BAACAgUAAxkBAAIBpmr9jeQYdMyAWRC_demevFaqCsLEAAIEKgACwTHxV5Nqev6BuXZNPQQ",
                caption=caption_text
            )
        except Exception as e:
            await query.message.reply_text(caption_text)
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Nagad Video Error: {e}")

    elif query.data.startswith("pay_bkash_"):
        prod_key = query.data.split("_")
        amount = int(get_product_price(prod_key))
        days = int(get_setting("days", "500"))
        product = PRODUCTS[prod_key]

        bkash_text = (
            f"💳 bKash Payment Details ({product['name']})\n"
            "(⚠️ আমাদের নিজস্ব বিকাশ একাউন্ট নেই। তাই উপরের ভিডিওটি দেখে আপনার বিকাশ একাউন্ট থেকে আমাদের নগদ একাউন্টে সেন্ড মানি করুন)\n\n"
            f"📱 Nagad Personal: {NAGAD_NUMBER}\n"
            f"💰 দাম: {amount} Tk (Send Money)\n"
            f"⏳ মেয়াদ: {days} দিন\n\n"
            "📌 নির্দেশনা:\n"
            "১. টাকা পাঠানোর পর আপনার Transaction ID (TrxID) টি কপি করে মেসেজ করুন (যেমন: 9H7G6F5D)।\n"
        )

        try:
            await query.message.reply_video(
                video="BAACAgUAAxkBAAIBrWr9kzpL0zPNbtDNhZVHZd4jeFDlAAINKgACwTHxVzN1OjuVRxvtPQQ",
                caption=bkash_text
            )
        except Exception as e:
            await query.message.reply_text(bkash_text)
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ bKash Video Error: {e}")

    elif query.data == "status":
        await check_user_status(query.message, user_id)
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
        await update.message.reply_text(f"✅ Product 2, 3 এবং 4-এর দাম একসাথে {int(new_amt)} Tk সেট করা হয়েছে!")
    except ValueError:
        await update.message.reply_text("❌ সঠিক সংখ্যা লিখুন। যেমন: /setamount2 100")


async def sendlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("ব্যবহার করুন:\n/sendlink <user_id> <link>\nউদাহরণ: /sendlink 123456789 https://t.me")
        return
    try:
        target_user_id = int(context.args)
        link_text = " ".join(context.args[1:])
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎉 অ্যাডমিন আপনার **{PRODUCTS['p4']['name']}**-এর লিংক পাঠিয়েছেন:\n\n🔗 {link_text}",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ ইউজার (`{target_user_id}`)-কে লিংক সফলভাবে পাঠানো হয়েছে!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ লিংক পাঠানো যায়নি। এরর: {e}")


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
    prod_key = u_row if (u_row and u_row in PRODUCTS) else "p1"
    required_amount = get_product_price(prod_key)

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
                f"❌ কম টাকা পাঠানো হয়েছে ({int(amount)} Tk)। {PRODUCTS[prod_key]['name']}-এর জন্য পুরো {int(required_amount)} Tk পাঠান।"
            )
            return

        cursor.execute("UPDATE sms_logs SET used = 1 WHERE trx_id = ?", (trx_id,))
        conn.commit()
        await send_invite_to_customer(context.bot, user.id, trx_id, amount, prod_key)
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO pending_users (trx_id, user_id, product_key) VALUES (?, ?, ?)",
            (trx_id, user.id, prod_key)
        )
        conn.commit()
        await update.message.reply_text(
            f"⏳ আপনার TrxID ({trx_id}) জমা হয়েছে ({PRODUCTS[prod_key]['name']})।\n"
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
        target_id = int(context.args)
        prod_key = context.args if len(context.args) > 1 and context.args in PRODUCTS else "p1"
        await send_invite_to_customer(context.bot, target_id, "MANUAL_ADMIN", get_product_price(prod_key), prod_key)


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
        customer_id, prod_key = pending
        prod_key = prod_key if prod_key in PRODUCTS else "p1"
        required_amount = get_product_price(prod_key)

        if amount >= required_amount:
            cursor.execute("UPDATE sms_logs SET used = 1 WHERE trx_id = ?", (trx_id,))
            cursor.execute("DELETE FROM pending_users WHERE trx_id = ?", (trx_id,))
            conn.commit()

            ptb_app = request.app["ptb_app"]
            await send_invite_to_customer(ptb_app.bot, customer_id, trx_id, amount, prod_key)

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
    
