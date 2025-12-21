import logging
import asyncio
import httpx
import re
from playwright.async_api import async_playwright
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def expand_url(url):
    logging.info(f"[DEBUG] Starting URL expansion for: {url}")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
            logging.info(f"[DEBUG] Sending HTTP request to expand URL...")
            response = await client.get(url)
            final_url = str(response.url)
            logging.info(f"[DEBUG] URL expanded successfully: {url} -> {final_url}")
            return final_url
    except Exception as e:
        logging.warning(f"[DEBUG] URL expansion failed, using original URL: {e}")
        return url

async def fetch_amazon_dynamic(url):
    logging.info(f"[DEBUG] ===== Starting Amazon data fetch for URL: {url} =====")
    async with async_playwright() as p:
        # محاكاة متصفح ديسكتوب حقيقي لتجنب الحظر ولضمان ظهور السعر القديم
        logging.info("[DEBUG] Launching Chromium browser...")
        browser = await p.chromium.launch(headless=False)
        logging.info("[DEBUG] Browser launched successfully")
        
        logging.info("[DEBUG] Creating browser context with viewport and user agent...")
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        logging.info("[DEBUG] Browser context created")
        
        logging.info("[DEBUG] Creating new page...")
        page = await context.new_page()
        logging.info("[DEBUG] New page created")

        try:
            logging.info("[DEBUG] Step 1: Expanding URL...")
            final_url = await expand_url(url)
            logging.info(f"[DEBUG] Step 2: Navigating to final URL: {final_url}")
            await page.goto(final_url, wait_until="domcontentloaded", timeout=20000)
            logging.info("[DEBUG] Page loaded successfully, waiting for network idle")
            
            logging.info("[DEBUG] Step 3: Scrolling page to load dynamic content...")
            await page.evaluate("window.scrollBy(0, 800)")
            logging.info("[DEBUG] Page scrolled, waiting 3 seconds for content to load...")
            await asyncio.sleep(3)
            logging.info("[DEBUG] Wait completed, starting data extraction...")

            logging.info("[DEBUG] Step 4: Executing JavaScript to extract category and products...")
            result = await page.evaluate("""
                () => {
                    console.log('[JS DEBUG] Starting data extraction...');
                    const result = {
                        category: '',
                        products: []
                    };
                    
                    // Detect page type
                    const isSearchPage = window.location.pathname.includes('/s');
                    const isBestsellersPage = window.location.pathname.includes('/gp/bestsellers');
                    console.log('[JS DEBUG] Page type - Search:', isSearchPage, 'Bestsellers:', isBestsellersPage);
                    
                    // Extract category based on page type
                    if (isBestsellersPage) {
                        // Bestsellers page - look for "Best Sellers in" heading
                        console.log('[JS DEBUG] Looking for category headings...');
                        const headings = Array.from(document.querySelectorAll('h2'));
                        console.log('[JS DEBUG] Found', headings.length, 'h2 headings');
                        const categoryHeading = headings.find(h => h.textContent.includes('Best Sellers in'));
                        
                        if (categoryHeading) {
                            result.category = categoryHeading.textContent.replace('Best Sellers in', '').trim();
                            console.log('[JS DEBUG] Category found:', result.category);
                        }
                    } else if (isSearchPage) {
                        // Search results page - get category from URL parameter
                        const urlParams = new URLSearchParams(window.location.search);
                        const categoryParam = urlParams.get('i') || 'Search Results';
                        result.category = categoryParam.charAt(0).toUpperCase() + categoryParam.slice(1);
                        console.log('[JS DEBUG] Category from URL:', result.category);
                    } else {
                        result.category = 'Products';
                        console.log('[JS DEBUG] Using default category');
                    }
                    
                    // Find products based on page type
                    let productItems = [];
                    
                    if (isBestsellersPage) {
                        // Bestsellers page - find carousel/list
                        const headings = Array.from(document.querySelectorAll('h2'));
                        const categoryHeading = headings.find(h => h.textContent.includes('Best Sellers in'));
                        
                        if (categoryHeading) {
                            let current = categoryHeading.parentElement;
                            let productContainer = null;
                            
                            for (let i = 0; i < 15 && current; i++) {
                                const carousel = current.querySelector('ol.a-carousel, ul');
                                if (carousel) {
                                    productContainer = carousel;
                                    break;
                                }
                                current = current.parentElement;
                            }
                            
                            if (productContainer) {
                                productItems = Array.from(productContainer.querySelectorAll('li'));
                            }
                        }
                    } else {
                        // Search results page - find all items with data-asin
                        const allAsinItems = Array.from(document.querySelectorAll('[data-asin]'));
                        productItems = allAsinItems.map(item => {
                            const container = item.closest('li, div[data-component-type="s-search-result"]') || item.parentElement;
                            return container;
                        }).filter(c => c !== null);
                    }
                    
                    console.log('[JS DEBUG] Found', productItems.length, 'product items');
                    const seenAsins = new Set();
                    
                    for (const item of productItems) {
                        if (result.products.length >= 4) {
                            console.log('[JS DEBUG] Reached limit of 4 products');
                            break;
                        }
                        
                        // Get ASIN
                        const asinEl = item.querySelector('[data-asin]') || item;
                        const asin = asinEl.getAttribute('data-asin');
                        if (!asin || asin.length < 5 || seenAsins.has(asin)) {
                            continue;
                        }
                        seenAsins.add(asin);
                        console.log('[JS DEBUG] Processing product with ASIN:', asin);
                        
                        // Get product name
                        let name = '';
                        if (isSearchPage) {
                            // Search page - get name from h2
                            const h2 = item.querySelector('h2');
                            if (h2) {
                                name = h2.textContent.replace(/Sponsored.*?Ad\\s*–?\\s*/i, '').trim();
                            }
                        } else {
                            // Bestsellers page - get name from link
                            const nameLinks = Array.from(item.querySelectorAll('a[href*="/dp/"]'));
                            for (const link of nameLinks) {
                                const text = link.textContent.trim();
                                if (text && text.length > 3 && !text.includes('stars') && !text.includes('rating')) {
                                    name = text;
                                    break;
                                }
                            }
                        }
                        
                        if (!name || name.length < 10) {
                            console.log('[JS DEBUG] No valid product name found');
                            continue;
                        }
                        console.log('[JS DEBUG] Product name:', name.substring(0, 50));
                        
                        // Get image
                        const img = item.querySelector('img[data-image-latency], img.s-image, img');
                        const image = img ? img.src : '';
                        console.log('[JS DEBUG] Image found:', image ? 'Yes' : 'No');
                        
                        // Get price
                        let currentPrice = '0.00';
                        let oldPrice = '0.00';
                        let discountPercent = '0';
                        let currency = 'EGP';
                        
                        // Get all text content for price extraction
                        const itemText = item.textContent || '';
                        
                        // Extract all EGP prices from text
                        const priceMatches = itemText.match(/EGP\\s*([\\d,]+\\.?\\d*)/g);
                        if (priceMatches && priceMatches.length > 0) {
                            // First price is current price
                            const firstPriceMatch = priceMatches[0].match(/EGP\\s*([\\d,]+\\.?\\d*)/);
                            if (firstPriceMatch) {
                                currentPrice = firstPriceMatch[1].replace(/,/g, '');
                            }
                            
                            // Check for List: or Was: for old price
                            const oldPricePatterns = [
                                /List:\\s*EGP\\s*([\\d,]+\\.?\\d*)/i,
                                /Was:\\s*EGP\\s*([\\d,]+\\.?\\d*)/i
                            ];
                            
                            for (const pattern of oldPricePatterns) {
                                const oldMatch = itemText.match(pattern);
                                if (oldMatch) {
                                    oldPrice = oldMatch[1].replace(/,/g, '');
                                    break;
                                }
                            }
                            
                            // If multiple prices and no old price found, check if second is higher
                            if (priceMatches.length > 1 && oldPrice === '0.00') {
                                const secondPriceMatch = priceMatches[1].match(/EGP\\s*([\\d,]+\\.?\\d*)/);
                                if (secondPriceMatch) {
                                    const secondPriceVal = parseFloat(secondPriceMatch[1].replace(/,/g, ''));
                                    const currentPriceVal = parseFloat(currentPrice);
                                    if (secondPriceVal > currentPriceVal && secondPriceVal > 0) {
                                        oldPrice = secondPriceMatch[1].replace(/,/g, '');
                                    }
                                }
                            }
                        }
                        
                        // For search results page, also check .a-price elements
                        if (isSearchPage && currentPrice === '0.00') {
                            const currentPriceEl = item.querySelector('.a-price:not(.a-text-price)');
                            if (currentPriceEl) {
                                const priceOffscreen = currentPriceEl.querySelector('.a-offscreen');
                                if (priceOffscreen) {
                                    const priceText = priceOffscreen.textContent;
                                    const priceMatch = priceText.match(/EGP\\s*([\\d,]+\\.?\\d*)/);
                                    if (priceMatch) {
                                        currentPrice = priceMatch[1].replace(/,/g, '');
                                    }
                                }
                            }
                            
                            const oldPriceEl = item.querySelector('.a-price.a-text-price');
                            if (oldPriceEl) {
                                const oldPriceOffscreen = oldPriceEl.querySelector('.a-offscreen');
                                if (oldPriceOffscreen) {
                                    const oldPriceText = oldPriceOffscreen.textContent;
                                    const oldPriceMatch = oldPriceText.match(/EGP\\s*([\\d,]+\\.?\\d*)/);
                                    if (oldPriceMatch) {
                                        oldPrice = oldPriceMatch[1].replace(/,/g, '');
                                    }
                                }
                            }
                        }
                        
                        // Calculate discount percentage
                        if (oldPrice !== '0.00' && currentPrice !== '0.00') {
                            const oldPriceNum = parseFloat(oldPrice);
                            const currentPriceNum = parseFloat(currentPrice);
                            if (oldPriceNum > currentPriceNum && oldPriceNum > 0) {
                                const discount = ((oldPriceNum - currentPriceNum) / oldPriceNum) * 100;
                                discountPercent = discount.toFixed(0);
                            }
                        }
                        
                        result.products.push({
                            name: name.substring(0, 200),
                            image: image,
                            current_price: currentPrice || '0.00',
                            old_price: oldPrice || '0.00',
                            discount_percent: discountPercent,
                            currency: currency
                        });
                        console.log('[JS DEBUG] Product added. Total products:', result.products.length);
                    }
                    
                    console.log('[JS DEBUG] Extraction complete. Category:', result.category, 'Products:', result.products.length);
                    return result;
                }
            """)
            
            logging.info(f"[DEBUG] Step 5: JavaScript execution completed")
            logging.info(f"[DEBUG] Raw result received: category='{result.get('category', '')}', products_count={len(result.get('products', []))}")
            
            # Extract category and products from result
            category = result.get('category', '')
            products = result.get('products', [])
            logging.info(f"[DEBUG] Step 6: Extracted category: '{category}', found {len(products)} products")
            
            # Add category to each product
            for idx, product in enumerate(products):
                product['category'] = category if category else 'Unknown'
                price = product.get('current_price') or product.get('price', 'N/A')
                old_price = product.get('old_price', 'N/A')
                discount = product.get('discount_percent', '0')
                logging.info(f"[DEBUG] Product {idx+1}: {product.get('name', 'N/A')[:50]}... | Price: {price} {product.get('currency', 'N/A')} | Old: {old_price} | Discount: {discount}%")
            
            logging.info(f"[DEBUG] ===== Amazon data fetch completed successfully. Returning {len(products)} products =====")
            return products
        except Exception as e:
            logging.error(f"[DEBUG] ===== ERROR in fetch_amazon_dynamic =====")
            logging.error(f"[DEBUG] Error type: {type(e).__name__}")
            logging.error(f"[DEBUG] Error message: {str(e)}")
            import traceback
            logging.error(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
            return []
        finally:
            logging.info("[DEBUG] Closing browser...")
            await browser.close()
            logging.info("[DEBUG] Browser closed")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"[DEBUG] ===== New message received =====")
    logging.info(f"[DEBUG] User ID: {update.effective_user.id}")
    logging.info(f"[DEBUG] Username: {update.effective_user.username}")
    
    text = update.message.text
    logging.info(f"[DEBUG] Message text: {text[:100]}...")
    
    logging.info("[DEBUG] Step 1: Searching for URL in message...")
    url_match = re.search(r'(https?://[^\s]+)', text)
    if not url_match:
        logging.info("[DEBUG] No URL found in message, ignoring...")
        return

    url = url_match.group(0)
    custom_category = text.replace(url, "").strip()
    logging.info(f"[DEBUG] Step 2: URL extracted: {url}")
    logging.info(f"[DEBUG] Custom category: '{custom_category}'")

    logging.info("[DEBUG] Step 3: Sending status message to user...")
    status_msg = await update.message.reply_text("⏳ جاري سحب الأسعار والتفاصيل...")
    logging.info("[DEBUG] Status message sent")
    
    logging.info("[DEBUG] Step 4: Calling fetch_amazon_dynamic...")
    products = await fetch_amazon_dynamic(url)
    logging.info(f"[DEBUG] Step 5: Received {len(products)} products from fetch_amazon_dynamic")

    if not products:
        logging.warning("[DEBUG] No products returned, sending error message...")
        await status_msg.edit_text("❌ فشل سحب البيانات.")
        return

    logging.info("[DEBUG] Step 6: Preparing media group...")
    media = []
    for idx, p in enumerate(products):
        logging.info(f"[DEBUG] Processing product {idx+1}/{len(products)}: {p.get('name', 'N/A')[:50]}...")
        cat = custom_category if custom_category else p.get('category', 'Unknown')
        
        # Get price field (could be 'current_price' or 'price')
        price = p.get('current_price') or p.get('price', '0.00')
        old_price = p.get('old_price', '0.00')
        discount_percent = p.get('discount_percent', '0')
        currency = p.get('currency', 'EGP')
        
        # تنسيق الكابشن لعرض السعر القديم ونسبة الخصم
        old_price_str = f"~~{old_price} {currency}~~" if old_price != "0.00" else ""
        discount_str = f"🎯 **{discount_percent}% OFF**" if discount_percent != "0" and old_price != "0.00" else ""
        
        caption = (
            f"📦 **{p['name']}**\n\n"
            f"📂 **Category:** {cat}\n"
            f"💰 **Price:** {price} {currency} {old_price_str}\n"
        )
        
        if discount_str:
            caption += f"{discount_str}\n"
        
        if p['image']:
            logging.info(f"[DEBUG] Adding product {idx+1} to media group with image: {p['image'][:50]}...")
            media.append(InputMediaPhoto(p['image'], caption=caption, parse_mode='MarkdownV2' if old_price_str else 'Markdown'))
        else:
            logging.warning(f"[DEBUG] Product {idx+1} has no image, skipping...")

    logging.info(f"[DEBUG] Step 7: Sending media group with {len(media)} items...")
    await update.message.reply_media_group(media)
    logging.info("[DEBUG] Media group sent successfully")
    
    logging.info("[DEBUG] Step 8: Deleting status message...")
    await status_msg.delete()
    logging.info("[DEBUG] ===== Message handling completed successfully =====")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"[DEBUG] /start command received from user {update.effective_user.id}")
    await update.message.reply_text("🚀 أرسل رابط أمازون وسأقوم بجلب المنتجات مع السعر قبل وبعد الخصم.")
    logging.info("[DEBUG] Start message sent")

if __name__ == "__main__":
    logging.info("[DEBUG] ===== Starting Amazon Category Bot =====")
    TOKEN = "8500333549:AAFPuoh8434zWRFf-9g3N8jxPvCn2ZNjJFw"
    logging.info("[DEBUG] Initializing Telegram application...")
    app = ApplicationBuilder().token(TOKEN).build()
    logging.info("[DEBUG] Application initialized")
    
    logging.info("[DEBUG] Registering command handlers...")
    app.add_handler(CommandHandler("start", start))
    logging.info("[DEBUG] /start handler registered")
    
    logging.info("[DEBUG] Registering message handlers...")
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logging.info("[DEBUG] Message handler registered")
    
    print("🚀 Amazon Price Bot is running...")
    logging.info("[DEBUG] Starting bot polling...")
    logging.info("[DEBUG] Bot is now listening for messages...")
    app.run_polling(drop_pending_updates=True)