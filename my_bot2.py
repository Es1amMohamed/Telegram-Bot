import logging
import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def fetch_trendyol_all_images(url):
    browser = None
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            device_config = p.devices["iPhone 13 Pro Max"]
            device_config["user_agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            
            context = await browser.new_context(**device_config)
            await context.add_cookies([
                {'name': 'countryCode', 'value': 'SA', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'language', 'value': 'ar', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'storefrontId', 'value': '30', 'domain': '.trendyol.com', 'path': '/'}
            ])
            
            page = await context.new_page()
            print(f"Opening URL: {url}")
            
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(5) 

            products_data = await page.evaluate("""
                () => {
                    const cards = Array.from(document.querySelectorAll('.product-card'));
                    cards.sort((a, b) => (parseInt(a.getAttribute('data-product-index')) || 0) - (parseInt(b.getAttribute('data-product-index')) || 0));

                    let results = [];
            
                    cards.slice(0, 4).forEach(card => {
           
                        const allImages = Array.from(card.querySelectorAll('.image-slider img.image, img.image, .image-wrapper img'));
                        
                        let mainImage = null;
                        if (allImages.length > 0) {
       
                            const firstImg = allImages[1];
                            mainImage = firstImg.src || firstImg.getAttribute('data-src');
                        }

                        const name = card.querySelector('.product-name')?.innerText.trim() || "N/A";
                        
                   
                        const category = card.querySelector('.category-name')?.innerText.trim() || "General";

                        const salePriceEl = card.querySelector('.sale-price');
                        const strikethroughEl = card.querySelector('.strikethrough-price');
                        const currencyEl = card.querySelector('.currency');

                  
                        const priceAfter = salePriceEl ? salePriceEl.innerText.replace(/\\s+/g, '').trim() : "N/A";
                        
                       
                        const priceBefore = strikethroughEl ? strikethroughEl.innerText.replace(/\\s+/g, '').trim() : "";
                        const currency = currencyEl ? currencyEl.innerText.trim() : "SAR";
                        
                        if (mainImage && mainImage.includes('http')) {
                            results.push({
                                'image': mainImage,
                                'name': name,
                                'category': category,
                                'price_before': priceBefore,
                                'price_after': priceAfter,
                                'currency': currency
                            });
                        }
                    });
                    return results;
                }
            """)

            return {"success": True, "products": products_data}

        except Exception as e:
            print(f"Error occurred: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if browser:
                await browser.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "http" in url:
        status_msg = await update.message.reply_text("📸 Fetching products collection... Please wait.")
        data = await fetch_trendyol_all_images(url)
        
        if data["success"] and data["products"]:
            media_group = []
            last_scraped_products = []
            for i, item in enumerate(data["products"]):
            
                caption = (
                    f"📦 **Product {i+1}:** {item['name']}\n"
                    f"🗂 **Category:** {item['category']}\n"
                    f"❌ **Before:** {item['price_before']}\n"
                    f"✅ **After:** {item['price_after']}\n"
                    f"💱 **Currency:** {item['currency']}"
                )
                
                media_group.append(InputMediaPhoto(item['image'], caption=caption, parse_mode='Markdown'))
                product_dict = {
                    "name": item['name'],
                    "price_before": item['price_before'],
                    "price_after": item['price_after'],
                    "currency": item['currency'],
                    "image_url": item['image']
                }
                last_scraped_products.append(product_dict)
                
    
                logging.info(f"✅ Product saved to dictionary: {product_dict}")
            if media_group:
                try:
            
                    await update.message.reply_media_group(media=media_group)
                except Exception as e:
                    await update.message.reply_text(f"❌ Failed to send images: {str(e)}")
            else:
                await update.message.reply_text("❌ No valid products found on this page.")
        else:
            await update.message.reply_text("❌ Error: Could not retrieve data. Page might be empty or restricted.")
        
        await status_msg.delete()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Welcome to Trendyol Collection Bot!**\nSend a category link to get summary.", parse_mode='Markdown')

if __name__ == '__main__':

    TOKEN = "YOUR_BOT_TOKEN_HERE"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 Collection Bot is running...")
    app.run_polling(drop_pending_updates=True)
