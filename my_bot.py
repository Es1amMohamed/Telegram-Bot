import logging
import asyncio
import re
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def fetch_trendyol_data(url):
    browser = None
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            
            iphone_13 = p.devices["iPhone 13 Pro Max"]
            context = await browser.new_context(**iphone_13, locale="en-US")
            page = await context.new_page()

            await context.add_cookies([
                {'name': 'countryCode', 'value': 'SA', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'language', 'value': 'en', 'domain': '.trendyol.com', 'path': '/'},
                {'name': 'storefrontId', 'value': '30', 'domain': '.trendyol.com', 'path': '/'}
            ])

            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            
            await page.evaluate("window.scrollBy(0, 300)")
            await asyncio.sleep(2) 

            image_url = await page.evaluate("""
                () => {
               
                    const selectors = ['.sp-img', '.product-detail-image img', '.product-image-container img'];
                    for (let s of selectors) {
                        const img = document.querySelector(s);
                        if (img && img.src && img.src.startsWith('http')) return img.src;
                    }
                
                    const allImgs = Array.from(document.querySelectorAll('img'));
                    const mainImg = allImgs.find(i => i.width > 200) || allImgs[0];
                    return mainImg ? mainImg.src : null;
                }
            """)

            product_name = await page.locator("h1").first.inner_text() if await page.locator("h1").count() > 0 else "N/A"
            
            price_data = await page.evaluate("""
                () => {
                    const priceWrapper = document.querySelector('.price-wrapper') || document.querySelector('.p-price-wrapper');
                    
                    if (priceWrapper) {
                        const currencyEl = priceWrapper.querySelector('.p-currency');
                        const currency = currencyEl ? currencyEl.innerText.trim() : 'SAR';

                        const saleEl = priceWrapper.querySelector('.p-sale-price');
                        let salePrice = "N/A";
                        if (saleEl) {
                            salePrice = saleEl.innerText.replace(/\\n/g, '').trim(); 
                        }

               
                        const oldEl = priceWrapper.querySelector('.p-strikethrough-price');
                        let oldPrice = oldEl ? oldEl.innerText.trim() : salePrice;

                        if (salePrice !== "N/A") {
                            return { 
                                original: oldPrice, 
                                discounted: salePrice, 
                                currency: currency,
                                method: 'specific' 
                            };
                        }
                    }

               
                    const parseVal = (str) => {
                        if (!str) return 0;
                        return parseFloat(str.replace(/[^0-9.]/g, '')) || 0;
                    };
                    const currencyKeywords = ['SAR', 'SR', 'ريال'];
                    const allElements = Array.from(document.querySelectorAll('.product-price, .prc-dsc, .prc-org, span'));
                    let foundPrices = [];
                    let foundCurrency = 'SAR';

                    for (let el of allElements) {
                        if (el.children.length === 0) {
                            const txt = el.innerText.trim();
                            if (currencyKeywords.some(curr => txt.includes(curr)) && /\\d/.test(txt) && txt.length < 30) {
                                foundPrices.push(txt);
            
                                if(txt.includes('SAR')) foundCurrency = 'SAR';
                                else if(txt.includes('SR')) foundCurrency = 'SR';
                            }
                        }
                    }
                    foundPrices = [...new Set(foundPrices)];
                    if (foundPrices.length === 0) return { original: "N/A", discounted: "N/A", currency: "SAR", method: 'fail' };
                    
                    foundPrices.sort((a, b) => parseVal(b) - parseVal(a));
                    
                    const clean = (p) => p.replace(/[^\d.,]/g, '');
                    
                    return { 
                        original: clean(foundPrices[0]), 
                        discounted: clean(foundPrices[foundPrices.length - 1]),
                        currency: foundCurrency,
                        method: 'generic'
                    };
                }
            """)

            final_url = page.url
            return {
                "success": True,
                "name": product_name.strip(),
                "price_original": price_data['original'],
                "price_discounted": price_data['discounted'],
                "currency": price_data['currency'],
                "image": image_url,
                "url": final_url
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if browser: await browser.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Welcome to Trendyol Smart Bot**\nSend me a link.")

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "trendyol" in url or "ty.gl" in url:
        waiting_msg = await update.message.reply_text("⏳ Processing...")
        data = await fetch_trendyol_data(url)
        
        if data["success"]:
            
            curr = data['currency']
            p_before = data['price_original']
            p_after = data['price_discounted']

            if p_before == p_after:
                price_block = (
                    f"💱 **Currency:** {curr}\n"
                    f"✅ **Price:** {p_after}"
                )
            else:
                price_block = (
                    f"💱 **Currency:** {curr}\n"
                    f"❌ **Before:** {p_before}\n"
                    f"✅ **After:** {p_after}"
                )

            caption = (
                f"📦 **Product:** {data['name']}\n\n"
                f"{price_block}\n\n"
                f"🔗 [Direct Link]({data['url']})"
            )
       
            if data["image"] and data["image"].startswith("http"):
                await update.message.reply_photo(photo=data["image"], caption=caption, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"⚠️ Image not found, but here are details:\n\n{caption}", parse_mode='Markdown')

            last_scraped_product = {
                "product_id": re.search(r"-p-(\d+)", data['url']).group(1) if "-p-" in data['url'] else "unknown",
                "name": data['name'],
                "price_before": p_before,
                "price_after": p_after,
                "currency": curr,
                "image_url": data['image'],
                "link": data['url']
            }
            logging.info(f"✅ Product saved to dictionary: {last_scraped_product['name']}")
        else:
            await update.message.reply_text(f"❌ Error: {data['error']}")
        await waiting_msg.delete()

if __name__ == '__main__':
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_link))
    print("🚀 Bot is running in Hybrid Mode...")
    app.run_polling()
