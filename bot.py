
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("💳 Payment", callback_data="payment")
        ]
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
            "Payment করার পর Screenshot দিন."
        )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: {update.effective_user.id}"
    )


app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("myid", myid))
app.add_handler(CallbackQueryHandler(button))

app.run_polling()
