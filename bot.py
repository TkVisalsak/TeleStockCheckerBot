import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fuzzywuzzy import fuzz
from PIL import Image, ImageDraw, ImageFont
import io

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets Authentication
def authenticate_google_sheets():
    try:
        scope = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(os.getenv('GOOGLE_SHEET_CREDENTIALS'), scope)
        client = gspread.authorize(creds)
        
        # Replace with your actual Google Sheet ID
        sheet = client.open_by_key(os.getenv('GOOGLE_SHEET_ID')).sheet1
        return sheet
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Sheets: {e}")
        return None

# Function to check for items based on a quantity threshold
async def check_items(update: Update, context: CallbackContext):
    try:
        if not context.args:
            await update.message.reply_text("Please specify a quantity threshold (e.g., /check <20 or /check 30).")
            return
        
        threshold_str = context.args[0]
        comparison = ""
        threshold = 0

        if threshold_str.startswith("<"):
            comparison = "<"
            try:
                threshold = int(threshold_str[1:])
            except ValueError:
                await update.message.reply_text("Invalid number specified after the '<' sign.")
                return
        else:
            try:
                threshold = int(threshold_str)
                comparison = ">="
            except ValueError:
                await update.message.reply_text("Invalid number provided.")
                return
        
        sheet = authenticate_google_sheets()
        if sheet is None:
            await update.message.reply_text("Sorry, there was an issue accessing the data.")
            return

        records = sheet.get_all_records()

        matching_items = []
        for row in records:
            if len(row) < 3:
                continue
            code, item, quantity = row.get('Code', ''), row.get('Item', ''), row.get('Quantity', '')
            
            try:
                quantity_int = int(quantity)
                if comparison == "<" and quantity_int < threshold:
                    matching_items.append(f"Code: {code}, Item: {item}, Quantity: {quantity}")
                elif comparison == ">=" and quantity_int >= threshold:
                    matching_items.append(f"Code: {code}, Item: {item}, Quantity: {quantity}")
            except ValueError:
                continue

        if matching_items:
            await update.message.reply_text(f"Items matching condition {comparison}{threshold}:\n" + "\n".join(matching_items))
        else:
            await update.message.reply_text(f"No items found matching condition {comparison}{threshold}.")
    
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")

# Function to search for an item using fuzzy matching
async def search_item(update: Update, context: CallbackContext):
    item_name = " ".join(context.args).strip()
    if not item_name:
        await update.message.reply_text("Please provide the item name you want to search for.")
        return

    sheet = authenticate_google_sheets()
    if sheet is None:
        await update.message.reply_text("Sorry, there was an issue accessing the data.")
        return

    records = sheet.get_all_records()
    matches = []
    threshold = 70

    for record in records:
        item_in_sheet = record.get('Item', '').strip()
        match_score = fuzz.partial_ratio(item_name.lower(), item_in_sheet.lower())

        if match_score >= threshold:
            record['Match Score'] = match_score
            matches.append(record)

    if matches:
        matches.sort(key=lambda x: x['Match Score'], reverse=True)
        response = "Here are the matching items:\n\n"
        for match in matches:
            response += (
                f"Code: {match.get('Code', 'N/A')} | "
                f"Item: {match.get('Item', 'N/A')} | "
                f"Quantity: {match.get('Quantity', 'N/A')}\n"
            )
        await update.message.reply_text(response)
    else:
        await update.message.reply_text(f"No matches found for '{item_name}'.")

# Function to create an image of the data from the Google Sheet
def create_table_image(data):
    image = Image.new('RGB', (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    y_offset = 10
    for row in data:
        line = f"Code: {row.get('Code', '')} | Item: {row.get('Item', '')} | Quantity: {row.get('Quantity', '')}"
        draw.text((10, y_offset), line, font=font, fill=(0, 0, 0))
        y_offset += 20

    byte_io = io.BytesIO()
    image.save(byte_io, 'PNG')
    byte_io.seek(0)
    return byte_io

# Command to send screenshot of the list
async def send_screenshot(update: Update, context: CallbackContext):
    sheet = authenticate_google_sheets()
    if sheet is None:
        await update.message.reply_text("Sorry, there was an issue accessing the data.")
        return

    records = sheet.get_all_records()
    rows_per_image = 25
    chunks = [records[i:i + rows_per_image] for i in range(0, len(records), rows_per_image)]

    for chunk in chunks:
        image = create_table_image(chunk)
        await update.message.reply_photo(photo=image)

# Start command with inline buttons
async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Search Item", callback_data="search")],
        [InlineKeyboardButton("Check Items", callback_data="check")],
        [InlineKeyboardButton("Get Screenshot", callback_data="screenshot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Welcome! Choose a command to start:', reply_markup=reply_markup)

# Help command
async def help(update: Update, context: CallbackContext):
    help_text = (
        "Here are the available commands:\n\n"
        "/search <item_name> - Search for an item using fuzzy matching.\n"
        "/check <quantity> - Check for items based on quantity (e.g., /check <10).\n"
        "/screenshot - Get a screenshot of the current inventory."
    )
    await update.message.reply_text(help_text)

# Main function to set up the bot
def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("Bot token is missing. Please set the TELEGRAM_BOT_TOKEN environment variable.")
        return

    application = Application.builder().token(bot_token).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("screenshot", send_screenshot))
    application.add_handler(CommandHandler("check", check_items))
    application.add_handler(CommandHandler("search", search_item))

    application.run_polling()

if __name__ == '__main__':
    main()
