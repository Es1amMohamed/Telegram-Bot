import logging
import asyncio
import re
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


AMAZON_SHORT_DOMAINS = {"amzn.to", "a.co", "amzn.eu", "amzn.asia"}

async def resolve_short_url(page, url):
  
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        resolved_url = page.url
        logging.info(f"Resolved short URL: {url} -> {resolved_url}")
        return resolved_url
    except Exception as e:
        logging.warning(f"Failed to resolve short URL {url}: {e}. Using original.")
        return url

async def handle_initial_popup(page, target_location):
    try:
        await page.wait_for_selector("#GLUXSignInWidget, .a-popover-modal", timeout=10000)
        logging.info("Detected initial location popup. Handling...")
        await page.fill("#GLUXZipUpdateInput, input[placeholder*='city']", target_location)
        await asyncio.sleep(2)
        await page.click('input[aria-labelledby="GLUXZipUpdate-announce"], button:has-text("Apply")')
        await asyncio.sleep(3)
        await page.click("button:has-text('Done'), #GLUXConfirmClose", timeout=8000)
        logging.info("Initial popup closed.")
        return True
    except:
        logging.info("No initial popup detected.")
        return False

async def change_delivery_location(page, target_location):
    try:
        await page.wait_for_selector("#glow-ingress-line2", timeout=10000)
        current_loc = await page.inner_text("#glow-ingress-line2")
        if target_location.lower() in current_loc.lower():
            logging.info(f"Location already {current_loc}")
            return True
    except:
        pass

    logging.info(f"Changing location to {target_location}")
    try:
        await page.click("#nav-global-location-popover-link", force=True, timeout=10000)
        await asyncio.sleep(4)
        await page.wait_for_selector("#GLUXZipUpdateInput", timeout=15000)
        await page.fill("#GLUXZipUpdateInput", "")
        await page.type("#GLUXZipUpdateInput", target_location, delay=100)
        await asyncio.sleep(2)
        await page.click('input[aria-labelledby="GLUXZipUpdate-announce"]', timeout=10000)
        await asyncio.sleep(3)
        try:
            await page.click("#GLUXConfirmClose, button:has-text('Done')", timeout=8000)
        except:
            pass
        await asyncio.sleep(3)
        return True
    except Exception as e:
        logging.error(f"Location change failed: {e}")
        await page.screenshot(path="location_error.png")
        return False

async def change_currency_if_needed(page, target_currency):
    currency_map = {
        "AED": "Dubai",
        "SAR": "Riyadh",
        "EGP": "Cairo",
        "USD": "New York"
    }
    target_location = currency_map.get(target_currency, "UAE")
    try:
        currency_symbol = await page.inner_text(".a-price-symbol", timeout=5000)
        if target_currency in currency_symbol:
            logging.info(f"Currency already {target_currency}")
            return True
    except:
        pass

    logging.info(f"Changing location for currency {target_currency}")
    return await change_delivery_location(page, target_location)

async def fetch_amazon_universal(original_url, config):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 4000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
           
            parsed_url = urlparse(original_url)
            if parsed_url.netloc in AMAZON_SHORT_DOMAINS:
                original_url = await resolve_short_url(page, original_url)

           
            target_lang = "en_AE" if config['language'] == "en" else "ar_AE"
            base_url = original_url.split('?')[0].rstrip('/')
            base_url = re.sub(r'/-[a-z]{2}/', '', base_url)  
            rh_match = re.search(r'rh=([^&]+)', original_url)
            query_parts = []
            if rh_match:
                query_parts.append(f"rh={rh_match.group(1)}")

            if '.sa' in original_url:
                final_url = base_url + ('?' + '&'.join(query_parts) if query_parts else '')
                logging.info(f"SA detected - no language param: {final_url}")
            else:
                query_parts.append(f"language={target_lang}")
                final_url = base_url + ('?' + '&'.join(query_parts) if query_parts else '')
                logging.info(f"Navigating to: {final_url}")

            await page.goto(final_url, wait_until="domcontentloaded", timeout=60000)

          
            await handle_initial_popup(page, config['deliver_to'])

      
            await change_currency_if_needed(page, config['currency'])
            await change_delivery_location(page, config['deliver_to'])

 
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 1500)")
                await asyncio.sleep(3)

        
            result = await page.evaluate("""
                () => {
                    const products = [];
                    let category = "General";
                    const catEl = document.querySelector('h1, .a-color-state, .zg-banner-landing-page-header, #zg_banner_text');
                    if (catEl) category = catEl.innerText.trim().replace(/[<>]/g, "");

                    const items = document.querySelectorAll(
                        '.zg-grid-general-faceout, #gridItemRoot, .zg-item, .octopus-pc-item-block, .p13n-sc-uncoverable-faceout, [data-component-type="s-search-result"], .s-result-item[data-asin]'
                    );
                    const seen = new Set();
                    for (const el of items) {
                        if (products.length >= 4) break;
                        let name = "", price = "0", oldPrice = "0", image = "", asin = "";
                 
                        const quickLook = el.querySelector('[data-octopus-quick-look]');
                        if (quickLook) {
                            try {
                                const data = JSON.parse(quickLook.getAttribute('data-octopus-quick-look'));
                                name = data.title;
                                price = data.price ? data.price.replace(/[^\\d.]/g, '') : "0";
                                oldPrice = data.strikePrice ? data.strikePrice.replace(/[^\\d.]/g, '') : "0";
                                image = data.image;
                                asin = data.asin;
                            } catch(e) {}
                        }
               
                        if (!name) {
                            const nEl = el.querySelector('h2, .octopus-pc-asin-title, .p13n-sc-truncate-desktop-type2, .a-size-base, .zg-title a');
                            name = nEl ? nEl.innerText.trim() : "";
                        }
                        if (price === "0") {
                            const pEl = el.querySelector('.a-price-whole, ._cDEzb_p13n-sc-price_3mJ9Z, .a-color-price, .a-offscreen');
                            price = pEl ? pEl.innerText.replace(/[^\\d.]/g, '') : "0";
                        }
                        if (oldPrice === "0") {
                            const opEl = el.querySelector('.a-text-price .a-offscreen');
                            oldPrice = opEl ? opEl.innerText.replace(/[^\\d.]/g, '') : "0";
                        }
                        if (!image.startsWith('http')) {
                            const iEl = el.querySelector('img');
                            image = iEl ? iEl.src : "";
                        }
                        asin = asin || el.getAttribute('data-asin') || el.id;
                        if (name && price !== "0" && !seen.has(asin)) {
                            seen.add(asin);
                            products.push({
                                name: name.replace(/[<>]/g, "").substring(0, 100),
                                price: price,
                                old_price: oldPrice,
                                image: image,
                                category: category
                            });
                        }
                    }
                    return products;
                }
            """)
            return result
        except Exception as e:
            logging.error(f"Global Scraper Error: {e}")
            await page.screenshot(path="scraper_error.png")
            return []
        finally:
            await browser.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_config: dict = None):
    url_text = update.message.text
    url_match = re.search(r'(https?://[^\s]+)', url_text)
    if not url_match: return
    full_url = url_match.group(0)

    amazon_config = {
        "language": "en",
        "currency": "AED",
        "deliver_to": "Dubai"
    }

    if custom_config:
        amazon_config.update(custom_config)
        logging.info(f"Custom config: {amazon_config}")
    else:
        if ".eg" in full_url:
            amazon_config.update({"currency": "EGP", "deliver_to": "Cairo", "language": "en"})
        elif ".sa" in full_url:
            amazon_config.update({"currency": "SAR", "deliver_to": "Riyadh", "language": "ar"})
        elif ".ae" in full_url:
            amazon_config.update({"currency": "AED", "deliver_to": "Dubai", "language": "en"})
        elif ".com" in full_url and "amazon.com" in full_url:
            amazon_config.update({"currency": "USD", "deliver_to": "New York", "language": "en"})

    status = await update.message.reply_text(f"🌍 Checking Amazon ({amazon_config['deliver_to']})...")

    products = await fetch_amazon_universal(full_url, amazon_config)
    if not products:
        await status.edit_text("❌ No products found. Check the link.")
        return

    media = []
    for p in products:
        caption = f"📦 <b>{p['name']}...</b>\n\n📂 <b>Category:</b> {p['category']}\n💰 <b>Price:</b> {p['price']} {amazon_config['currency']}\n"
        if p['old_price'] != "0":
            caption += f"<s>❌ Was: {p['old_price']}</s>\n"
        caption += f"📍 <b>Deliver to:</b> {amazon_config['deliver_to']}"
        if p['image']:
            media.append(InputMediaPhoto(p['image'], caption=caption, parse_mode='HTML'))

    try:
        if media:
            await update.message.reply_media_group(media)
            await status.delete()
    except Exception as e:
        logging.error(f"Media error: {e}")
        await status.edit_text(f"⚠️ Error: {e}")

if __name__ == "__main__":
    TOKEN = "Your Telegram Bot Token"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), 
                                  lambda u, c: handle_message(u, c, None)))
    print("🚀 Bot running...")
    app.run_polling()