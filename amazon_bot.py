import logging
import asyncio
import re
from urllib.parse import urlparse, quote 
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

AMAZON_SHORT_DOMAINS = {"amzn.to", "a.co", "amzn.eu", "amzn.asia"}

async def resolve_short_url(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return page.url
    except:
        return url

async def handle_initial_popup(page, target_location):
   
    try:
      
        dismiss = await page.query_selector("input[data-action-type='DISMISS'], .glow-toaster-button-dismiss")
        if dismiss: await dismiss.click()

        await page.wait_for_selector("#glow-ingress-line2", timeout=5000)
        current = await page.inner_text("#glow-ingress-line2")
        if target_location.lower() in current.lower(): return

        await page.click("#nav-global-location-popover-link", force=True)
        await page.wait_for_selector("#GLUXZipUpdateInput", timeout=5000)
        
   
        zip_code = "10001" if "New York" in target_location else target_location
        await page.fill("#GLUXZipUpdateInput", zip_code)
        await page.click('input[aria-labelledby="GLUXZipUpdate-announce"]')
        await asyncio.sleep(2)
        await page.click("button:has-text('Done'), #GLUXConfirmClose", timeout=5000)
        await page.wait_for_load_state("networkidle")
    except:
        pass

async def fetch_single_product(original_url, config):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
    
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = await context.new_page()
        
        try:
    
            if urlparse(original_url).netloc in AMAZON_SHORT_DOMAINS:
                original_url = await resolve_short_url(page, original_url)

            logging.info(f"🚀 Accessing: {original_url}")
            
       
            await page.goto(original_url, wait_until="commit", timeout=60000)

           
            popups = ["#sp-cc-accept", "input[data-action-type='DISMISS']", ".glow-toaster-button-dismiss"]
            for selector in popups:
                try:
                    target = await page.query_selector(selector)
                    if target: await target.click()
                except: pass

         
            await handle_initial_popup(page, config['deliver_to'])
            
         
            try:
                variant_li = await page.query_selector('li.inline-twister-swatch:not(.a-button-selected), li[id*="size_name_0"]')
                if variant_li:
                    await variant_li.click(force=True)
                    await asyncio.sleep(3) 
            except: pass

            await page.mouse.wheel(0, 500)
            await asyncio.sleep(2)

          
            product = await page.evaluate("""
                () => {
                    const data = {title: "Unknown", price: "Check on site", old_price: "", category: "Unknown", image: ""};

                 
                    let titleEl = document.querySelector('#productTitle, #title');
                    if (titleEl) {
                        let rawTitle = titleEl.innerText.trim();
                      
                        if (rawTitle.includes('Keyboard shortcut')) {
                           const altTitle = document.querySelector('meta[name="title"]');
                           data.title = altTitle ? altTitle.content : "Amazon Product";
                        } else {
                           data.title = rawTitle.substring(0, 150);
                        }
                    }

               
               
                    const priceSelectors = [
                        '#corePriceDisplay_desktop_feature_div .a-price .a-offscreen',
                        '#corePrice_desktop .a-price .a-offscreen',
                        '#price_inside_buybox',
                        '.priceToPay .a-offscreen',
                        '.a-price:not([data-a-color="price"]) .a-offscreen'
                    ];

                    for (let s of priceSelectors) {
                        let el = document.querySelector(s);
                        if (el && /[0-9]/.test(el.innerText) && !el.innerText.includes('%')) {
                            data.price = el.innerText.trim();
                            break;
                        }
                    }

              
                    const mainImg = document.querySelector('#landingImage') || 
                                   document.querySelector('#imgTagWrapperId img') ||
                                   document.querySelector('.a-button-selected img');
                    
                    if (mainImg) {
                        data.image = mainImg.getAttribute('data-old-hires') || mainImg.src;
                    }

             
                    const crumbs = Array.from(document.querySelectorAll('#wayfinding-breadcrumbs_feature_div a'))
                                        .map(a => a.innerText.trim()).filter(Boolean);
                    data.category = crumbs.slice(0, 3).join(' > ') || "Unknown";

                    return data;
                }
            """)

            product['currency'] = config['currency']
            product['deliver_to'] = config['deliver_to']
            return product

        except Exception as e:
            logging.error(f"❌ Scrape Error: {e}")
            return None
        finally:
            await browser.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url_match = re.search(r'(https?://[^\s]+)', update.message.text)
    if not url_match: return
    
    full_url = url_match.group(0)
    

    amazon_config = {"language": "en", "currency": "USD", "deliver_to": "United States"}
    domain_map = {
        ".eg": {"currency": "EGP", "deliver_to": "Cairo"},
        ".sa": {"currency": "SAR", "deliver_to": "Riyadh"},
        ".ae": {"currency": "AED", "deliver_to": "Dubai"},
        ".es": {"currency": "EUR", "deliver_to": "Madrid"},
        ".de": {"currency": "EUR", "deliver_to": "Berlin"},
        ".uk": {"currency": "GBP", "deliver_to": "London"}
    }

    for domain, cfg in domain_map.items():
        if domain in full_url:
            amazon_config.update(cfg)
            break

    status = await update.message.reply_text(f"🔍 Fetching Global Product ({amazon_config['deliver_to']})...")
    product = await fetch_single_product(full_url, amazon_config)

    if not product or product['title'] == "Unknown":
        await status.edit_text("❌ Failed to load product. Amazon might be blocking this request.")
        return

    caption = (
        f"📦 <b>{product['title']}</b>\n\n"
        f"📂 <b>Category:</b> {product['category']}\n"
        f"💰 <b>Price:</b> <b>{product['price']}</b>\n"
        f"📍 <b>Region:</b> {product['deliver_to']}"
    )

    try:
        if product['image'] and product['image'].startswith('http'):
    
            await update.message.reply_photo(photo=product['image'], caption=caption, parse_mode='HTML')
        else:
            await update.message.reply_text(caption, parse_mode='HTML')
        await status.delete()
    except Exception as e:
        logging.error(f"Send Error: {e}")
        await status.edit_text(caption, parse_mode='HTML')

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    TOKEN = "8275673221:AAFqU7osZUD3_kCdLv8P5FmleNTgLx3sJYE"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 Universal Amazon Bot - Running across all regions!")
    app.run_polling()