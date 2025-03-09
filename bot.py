import os
import logging
import tempfile
import json
from pathlib import Path
from dotenv import load_dotenv
import base64
from io import BytesIO

from mistralai import Mistral
from mistralai import DocumentURLChunk, ImageURLChunk, TextChunk
from mistralai.models import OCRResponse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# Initialize Mistral client
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "👋 Welcome to the OCR Bot!\n\n"
        "Send me a PDF or image, and I'll extract the text using Mistral OCR.\n\n"
        "Commands:\n"
        "/start - Show this help message\n"
        "/help - Show help information"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "📝 OCR Bot Help:\n\n"
        "This bot uses Mistral's OCR technology to extract text from documents.\n\n"
        "To use it, simply send:\n"
        "- 📸 An image (.jpg, .png, etc.)\n"
        "- 📄 A PDF document\n\n"
        "The bot will process your file and return the extracted text."
    )

async def process_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process document (PDF or image) and extract text using Mistral OCR."""
    message = update.message
    
    # Send a processing message
    processing_message = await message.reply_text("⏳ Processing your document. This may take a moment...")
    
    try:
        # Get file info
        file = await message.document.get_file()
        file_extension = Path(file.file_path).suffix.lower()
        
        # Check if file type is supported
        if file_extension not in ['.pdf', '.jpg', '.jpeg', '.png']:
            await processing_message.edit_text(
                "❌ Unsupported file type. Please send a PDF or image file (jpg, jpeg, png)."
            )
            return
        
        # Download the file
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
            await file.download_to_memory(temp_file)
            temp_file_path = Path(temp_file.name)
        
        # Upload file to Mistral
        with open(temp_file_path, 'rb') as f:
            uploaded_file = mistral_client.files.upload(
                file={
                    "file_name": message.document.file_name,
                    "content": f.read(),
                },
                purpose="ocr",
            )
        
        # Get signed URL
        signed_url = mistral_client.files.get_signed_url(file_id=uploaded_file.id, expiry=5)
        
        # Process using OCR
        ocr_response = mistral_client.ocr.process(
            document=DocumentURLChunk(document_url=signed_url.url), 
            model="mistral-ocr-latest", 
            include_image_base64=True
        )
        
        # Clean up temp file
        if temp_file_path.exists():
            os.unlink(temp_file_path)
        
        # Process response based on format
        await send_ocr_results(update, context, ocr_response, processing_message)
        
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        await processing_message.edit_text(f"❌ Error processing document: {str(e)}")

async def process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process photos and extract text using Mistral OCR."""
    message = update.message
    
    # Send a processing message
    processing_message = await message.reply_text("⏳ Processing your image. This may take a moment...")
    
    try:
        # Get the largest photo
        photo_file = await message.photo[-1].get_file()
        
        # Get the file URL if possible
        if hasattr(photo_file, 'file_path') and photo_file.file_path.startswith('http'):
            # Use image URL directly with Mistral OCR
            ocr_response = mistral_client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "image_url",
                    "image_url": photo_file.file_path
                },
                include_image_base64=True
            )
        else:
            # Download the photo if direct URL not available
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                await photo_file.download_to_memory(temp_file)
                temp_file_path = Path(temp_file.name)
            
            # Upload file to Mistral
            with open(temp_file_path, 'rb') as f:
                uploaded_file = mistral_client.files.upload(
                    file={
                        "file_name": f"telegram_image_{message.message_id}.jpg",
                        "content": f.read(),
                    },
                    purpose="ocr",
                )
            
            # Get signed URL
            signed_url = mistral_client.files.get_signed_url(file_id=uploaded_file.id, expiry=5)
            
            # Process using OCR - for images use the proper format
            ocr_response = mistral_client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": signed_url.url
                },
                include_image_base64=True
            )
            
            # Clean up temp file
            if temp_file_path.exists():
                os.unlink(temp_file_path)
        
        # Process response
        await send_ocr_results(update, context, ocr_response, processing_message)
        
    except Exception as e:
        logger.error(f"Error processing photo: {e}")
        await processing_message.edit_text(f"❌ Error processing photo: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages without files or images."""
    await update.message.reply_text(
        "📤 Please upload your file or image!\n\n"
        "I can process:\n"
        "- 📸 Images (.jpg, .jpeg, .png)\n"
        "- 📄 PDFs (.pdf)\n\n"
        "Just send me the file, and I'll extract the text for you."
    )

async def send_ocr_results(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           ocr_response: OCRResponse, processing_message) -> None:
    """Process OCR results and send back to user in different formats."""
    
    try:
        # Convert OCR response to dictionary
        response_dict = json.loads(ocr_response.json())
        
        # Create a text version by extracting text from paragraphs
        text_content = ""
        for page in ocr_response.pages:
            # The OCR response has paragraphs, not direct text attribute
            if hasattr(page, 'paragraphs'):
                for paragraph in page.paragraphs:
                    text_content += paragraph.text + "\n"
            # Extract from markdown as fallback
            elif hasattr(page, 'markdown'):
                # Simplistic markdown to text conversion (removing markdown syntax)
                md_text = page.markdown
                # Remove headers
                md_text = md_text.replace("# ", "").replace("## ", "").replace("### ", "")
                # Remove image references
                md_text = "\n".join([line for line in md_text.split("\n") if not line.startswith("![") and not line.startswith("<img")])
                text_content += md_text + "\n"
            text_content += "\n"
        
        # Create markdown version
        markdown_content = get_combined_markdown(ocr_response)
        
        # Respond with text first (for immediate feedback)
        if len(text_content) <= 4096:
            await processing_message.edit_text(
                "✅ Text extracted successfully! Here's the content:\n\n" + text_content[:4000] + 
                ("\n\n(Select 'Download as file' below for complete content)" if len(text_content) > 4000 else "")
            )
        else:
            await processing_message.edit_text(
                "✅ Text extracted successfully! The content is too long to display here.\n"
                "Please use the buttons below to get the content as a file."
            )
        
        # Send file options with Cancel button
        keyboard = [
            [
                InlineKeyboardButton("Text (.txt)", callback_data="format_txt"),
                InlineKeyboardButton("Markdown (.md)", callback_data="format_md"),
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data="format_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store the extracted content in user_data for later retrieval
        context.user_data["ocr_text"] = text_content
        context.user_data["ocr_markdown"] = markdown_content
        
        await update.message.reply_text(
            "📝 Choose a download format:", 
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error processing OCR results: {e}")
        await processing_message.edit_text(f"❌ Error processing OCR results: {str(e)}")

def get_combined_markdown(ocr_response: OCRResponse) -> str:
    """Combine markdown from all pages and replace image references with base64 data."""
    markdowns = []
    for page in ocr_response.pages:
        if hasattr(page, 'images'):
            image_data = {}
            for img in page.images:
                image_data[img.id] = img.image_base64
            markdowns.append(replace_images_in_markdown(page.markdown, image_data))
        elif hasattr(page, 'markdown'):
            # If no images, just add the markdown
            markdowns.append(page.markdown)

    return "\n\n".join(markdowns)

def replace_images_in_markdown(markdown_str: str, images_dict: dict) -> str:
    """Replace image references with base64 data."""
    for img_name, base64_str in images_dict.items():
        markdown_str = markdown_str.replace(f"![{img_name}]({img_name})", f"![{img_name}]({base64_str})")
    return markdown_str

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks for format selection."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("format_"):
        format_type = query.data.split("_")[1]
        
        if format_type == "txt":
            # Send text file
            with BytesIO(context.user_data["ocr_text"].encode('utf-8')) as file:
                await query.message.reply_document(
                    document=file,
                    filename="extracted_text.txt",
                    caption="📄 Here's your extracted file! 🎉"
                )
        
        elif format_type == "md":
            # Send markdown file
            with BytesIO(context.user_data["ocr_markdown"].encode('utf-8')) as file:
                await query.message.reply_document(
                    document=file,
                    filename="extracted_content.md",
                    caption="📄 Here's your extracted file! 🎉"
                )
        
        elif format_type == "cancel":
            # Cancel the operation and remove the keyboard
            await query.message.edit_text("❌ Operation cancelled")

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO, process_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, process_document))
    application.add_handler(CallbackQueryHandler(button_callback))
    # Add handler for text messages without attachments
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main() 