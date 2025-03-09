# Telegram OCR Bot

A Telegram bot that uses Mistral's OCR technology to extract text from images and PDF documents.

## Features

- Process PDF documents and images sent by users
- Extract text using Mistral's advanced OCR capabilities
- Return results in different formats (text and markdown with embedded images)
- User-friendly interface with buttons for selecting output format

## Setup

1. **Install dependencies**

```bash
pip install -r requirements.txt
```

2. **Configure environment variables**

Create a `.env` file in the project root with the following variables:

```
MISTRAL_API_KEY=your_mistral_api_key
BOT_TOKEN=your_telegram_bot_token
```

- To get a Telegram bot token, talk to [@BotFather](https://t.me/BotFather) on Telegram
- For a Mistral API key, sign up at [mistral.ai](https://mistral.ai) and create an API key

3. **Run the bot**

```bash
python bot.py
```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to get started
3. Send any image or PDF document to the bot
4. The bot will process the file and extract text using OCR
5. Choose your preferred download format (Text or Markdown)

## Supported File Types

- PDF documents (.pdf)
- Images (.jpg, .jpeg, .png)

## Notes

- The Telegram bot uses the python-telegram-bot library
- OCR processing is done using Mistral's OCR API
- For large files, processing may take some time
- Markdown output preserves the document layout and includes embedded images 