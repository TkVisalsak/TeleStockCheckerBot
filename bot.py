import logging
import os
import json
from telegram import Update
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

        # Fetch credentials JSON from environment variable
        creds_json = os.getenv("GOOGLE_SHEET_CREDENTIALS")
        if not creds_json:
            logger.error("Google Sheets credentials are not set. Please set the GOOGLE_SHEETS_CREDENTIALS_JSON environment variable.")
            return None

        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        # Retrieve Google Sheet ID from environment variable
        sheet_id = os.getenv('GOOGLE_SHEET_ID')
        if not sheet_id:
            logger.error("Google Sheets ID is not set. Please set the GOOGLE_SHEET_ID environment variable.")
            return None

        # Open the sheet by its ID
        sheet = client.open_by_key(sheet_id).sheet1
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

# Start command
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text('Welcome! Use /screenshot to get a screenshot of the current inventory. Use /check <quantity> to check item quantities. Use /search <item_name> to search for an item.')

# Main function to set up the bot
def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")  # Get bot token from environment variable
    if not bot_token:
        logger.error("Bot token is missing. Please set the TELEGRAM_BOT_TOKEN environment variable.")
        return
      
# Use webhook instead of polling
application.run_webhook(
    listen="0.0.0.0",
    port=int(os.getenv("PORT", 5000)),  # Bind to the required port
    webhook_url=f"https://<your-render-app-url>/webhook"
)

    application = Application.builder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("screenshot", send_screenshot))
    application.add_handler(CommandHandler("check", check_items))
    application.add_handler(CommandHandler("search", search_item))

    application.run_polling()

if __name__ == '__main__':
    main()
