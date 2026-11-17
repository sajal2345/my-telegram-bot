
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


async def get_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post

    if post:
        channel_id = post.chat.id

        print(f"CHANNEL POST RECEIVED: {channel_id}")

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Channel Name: {post.chat.title}\nChannel ID: {channel_id}"
        )


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("myid", myid))
app.add_handler(CallbackQueryHandler(button))

app.add_handler(
    MessageHandler(
        filters.UpdateType.CHANNEL_POST,
        get_channel_id
    ),
    group=-1
)

app.add_handler(
    MessageHandler(
        filters.PHOTO | filters.Document.ALL,
        payment_screenshot
    )
)

app.run_polling()
