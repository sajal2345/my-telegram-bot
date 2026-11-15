
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("💰 Price", callback_data="price"),
            InlineKeyboardButton("💳 Payment", callback_data="payment")
        ]
    ]

    await update.message.reply_photo(
    photo="YOUR_IMAGE_URL",
    caption="Welcome to Our Online Shop!\n\n"
            "Detective team এ আপনাকে স্বাগতম\n"
            "আপনার পছন্দের অপশন নির্বাচন করুন।",
    reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "price":
        await query.edit_message_text(
            "💰 Price Details\n\n"
            "50% অফারে মাত্র: 50 Tk\n\n"
            "Order করতে Admin-কে Message করুন."
        )

    elif query.data == "payment":
        await query.edit_message_text(
            "💳 Payment Details\n\n"
            "Nagad: 9856000616951329\n\n"
            "Payment করার পর Screenshot দিন."
        )


app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))

app.run_polling()
