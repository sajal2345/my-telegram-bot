
import os
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

ADMIN_ID = 7500776824
CHANNEL_ID = -1004459597302


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 Payment", callback_data="payment")]
    ]

    await update.message.reply_text(
        "Welcome to Our Online Shop!\n\n"
        "আমাদের শপে স্বাগতম।\n"
        "আপনার পছন্দের অপশন নির্বাচন করুন।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "payment":
        await query.edit_message_text(
            "💳 Payment Details\n\n"
            "Nagad: 9856000616951329\n\n"
            "Payment করার পর Screenshot পাঠান।"
        )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: {update.effective_user.id}"
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
        "আপনার Payment Screenshot পেয়েছি। "
        "Payment যাচাই করে জানানো হবে।"
    )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "ব্যবহার করুন:\n/approve CUSTOMER_ID"
        )
        return

    try:
        customer_id = int(context.args[0])

        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1
        )

        await context.bot.send_message(
            chat_id=customer_id,
            text=(
                "✅ Payment Verified!\n\n"
                "আপনার Channel Join Link:\n"
                f"{invite.invite_link}\n\n"
                "এই Link একজন ব্যবহারকারী একবার ব্যবহার করতে পারবেন।"
            )
        )

        await update.message.reply_text(
            "✅ Customer-কে Invite Link পাঠানো হয়েছে।"
        )

    except Exception as e:
        await update.message.reply_text(
            f"Error: {e}"
        )


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("myid", myid))
app.add_handler(CommandHandler("approve", approve))
app.add_handler(CallbackQueryHandler(button))

app.add_handler(
    MessageHandler(
        filters.PHOTO | filters.Document.ALL,
        payment_screenshot
    )
)

app.run_polling()
