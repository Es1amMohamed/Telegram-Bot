# 🛍️ Trendyol Product Scraper Bot

An intelligent Telegram Bot designed to fetch product details (Name, Price, Image) from **Trendyol** automatically. It supports both long URLs and short links (`ty.gl`), with built-in logic to bypass country selection and splash screens.

---

## ✨ Features
* **Smart Link Support:** Handles short links (`ty.gl`) and full Trendyol URLs.
* **Anti-Bot Bypass:** Powered by `Playwright` to simulate real browser behavior and bypass protections.
* **Automatic Country Handling:** Pre-injected with cookies to bypass "Welcome" and "Select Country" screens.
* **Dynamic Data Extraction:** Intelligent price and name detection for international markets.
* **Clean UI:** Sends professional messages with product photos and direct Markdown links.

---

## 🚀 Installation & Setup

### 1. Prerequisites
Make sure you have **Python 3.8+** installed on your system.

### 2. Install Dependencies
Open your terminal in VS Code and run:
```bash
pip install -r requirements.txt
playwright install chromium

4. Configure Bot Token
Open my_bot.py.

Locate the line: TOKEN = "YOUR_BOT_TOKEN_HERE".

Replace it with your actual token from @BotFather.


🛠️ Usage
Start the bot by running:
python my_bot.py