import os, json, uuid, threading, logging, time
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

# ==================== CẤU HÌNH ====================
BOT_TOKEN   = "8051113710:AAFtKIznsuXQMegca66tPX1bbTLXAmsZalM"
ADMIN_ID    = 6765618686
CASSO_KEY   = "AK_CS.d01de3f03b2311f1a3ca79c2f1d864cb.iq8UrTh8GJxm4mnJyGm1SKOTOK4S9zR4fbZPeuulOfjcH9O6zlUpGrQEir7AFuD8hFufn8Bz"

# Thông tin ngân hàng để tạo QR
BANK_ID     = "MB"           # Mã ngân hàng MB Bank
ACCOUNT_NO  = "0399265360"   # Số tài khoản
ACCOUNT_NAME = "LAM VAN THEN"

PAYMENT_INFO = """🏦 *Thông tin chuyển khoản:*
• Ngân hàng: MB BANK
• Số TK: `{account_no}`
• Chủ TK: {account_name}
• Số tiền: *{total:,}đ*
• Nội dung CK: `{order_id}`

📱 *Quét QR bên trên để thanh toán tự động!*"""

PRODUCTS = {
    "SP001": {"name": "Mail New Reg Tay - Bao Trial YouTube",      "price": 15000, "items": [], "emoji": "📧"},
    "SP002": {"name": "Tài Khoản PayPal Trắng - Không Lỗi",        "price": 20000, "items": [], "emoji": "💳"},
    "SP003": {"name": "Mail Cổ Người Dùng Thật - Có Trial YouTube", "price": 40000, "items": [], "emoji": "⭐"},
    "SP004": {"name": "Tài Khoản GitHub Trắng - Full Mail",         "price": 20000, "items": [], "emoji": "🐙"},
    "SP005": {"name": "Mail Cổ Người Dùng Thật - Không Trial",      "price": 20000, "items": [], "emoji": "📬"},
}

DATA_FILE    = "shop_data.json"
CHOOSING_QTY = 1

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ==================== VietQR ====================
def get_qr_url(amount: int, order_id: str) -> str:
    """Tạo URL ảnh QR VietQR với số tiền và nội dung CK sẵn"""
    return (
        f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-compact2.png"
        f"?amount={amount}"
        f"&addInfo={order_id}"
        f"&accountName={ACCOUNT_NAME.replace(' ', '%20')}"
    )

# ==================== DỮ LIỆU ====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"orders": {}, "products": PRODUCTS, "last_casso_id": 0}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================== CASSO POLLING ====================
def check_casso(bot):
    import asyncio
    while True:
        try:
            data    = load_data()
            last_id = data.get("last_casso_id", 0)
            headers = {"Authorization": f"Apikey {CASSO_KEY}"}
            resp    = requests.get(
                "https://oauth.casso.vn/v2/transactions?sort=DESC&pageSize=10",
                headers=headers, timeout=10
            )
            if resp.status_code == 200:
                txs = resp.json().get("data", {}).get("records", [])
                for tx in txs:
                    tx_id = tx.get("id", 0)
                    if tx_id <= last_id:
                        continue
                    data = load_data()
                    if tx_id > data.get("last_casso_id", 0):
                        data["last_casso_id"] = tx_id
                        save_data(data)
                    desc   = tx.get("description", "").upper()
                    amount = tx.get("amount", 0)
                    data   = load_data()
                    for order_id, order in data["orders"].items():
                        if (order_id.upper() in desc
                                and order["status"] == "pending"
                                and amount >= order["total"]):
                            loop = asyncio.new_event_loop()
                            loop.run_until_complete(deliver_order(order_id, bot))
                            loop.close()
                            break
        except Exception as e:
            logger.warning(f"Casso error: {e}")
        time.sleep(10)

# ==================== GIAO HÀNG ====================
async def deliver_order(order_id: str, bot):
    data  = load_data()
    order = data["orders"].get(order_id)
    if not order or order["status"] == "paid":
        return
    sp_id = order["product_id"]
    sp    = data["products"].get(sp_id)
    qty   = order["quantity"]
    if not sp or len(sp["items"]) < qty:
        await bot.send_message(chat_id=order["user_id"],
            text=f"⚠️ Đơn #{order_id} đã thanh toán nhưng hết hàng. Admin sẽ liên hệ sớm!")
        await bot.send_message(chat_id=ADMIN_ID,
            text=f"🚨 Đơn {order_id} hết hàng! Cần nạp thêm {sp_id}.")
        return
    delivered       = sp["items"][:qty]
    sp["items"]     = sp["items"][qty:]
    order["status"] = "paid"
    order["items_delivered"] = delivered
    order["paid_at"] = datetime.now().isoformat()
    save_data(data)
    items_text = "\n".join([f"`{item}`" for item in delivered])
    await bot.send_message(
        chat_id=order["user_id"],
        text=(f"✅ *Thanh toán xác nhận! Đây là hàng của bạn:*\n\n"
              f"📦 {order['product_name']} x{qty}\n\n{items_text}\n\n"
              f"Cảm ơn bạn đã mua hàng tại Candy Shop! 🎉"),
        parse_mode="Markdown")
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💰 Đơn `{order_id}` đã thanh toán!\n{order['product_name']} x{qty} — {order['total']:,}đ",
        parse_mode="Markdown")

# ==================== HANDLERS ====================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🛍 Xem sản phẩm",     callback_data="view_products")],
        [InlineKeyboardButton("💰 Bảng giá",          callback_data="price_list")],
        [InlineKeyboardButton("📞 Liên hệ admin",     callback_data="contact_admin")],
        [InlineKeyboardButton("📦 Đơn hàng của tôi", callback_data="my_orders")],
    ]
    await update.message.reply_text(
        "👋 Chào mừng đến *Candy Shop*!\nChọn chức năng bên dưới:",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("🛍 Xem sản phẩm",     callback_data="view_products")],
        [InlineKeyboardButton("💰 Bảng giá",          callback_data="price_list")],
        [InlineKeyboardButton("📞 Liên hệ admin",     callback_data="contact_admin")],
        [InlineKeyboardButton("📦 Đơn hàng của tôi", callback_data="my_orders")],
    ]
    await query.edit_message_text(
        "👋 Chào mừng đến *Candy Shop*!\nChọn chức năng bên dưới:",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ConversationHandler.END

async def view_products(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data  = load_data()
    query = update.callback_query
    await query.answer()
    kb = []
    for sp_id, sp in data["products"].items():
        kb.append([InlineKeyboardButton(
            f"{sp['emoji']} {sp['name']} — {sp['price']:,}đ ({len(sp['items'])} còn)",
            callback_data=f"buy_{sp_id}")])
    kb.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")])
    await query.edit_message_text("🛍 *Danh sách sản phẩm:*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def price_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data  = load_data()
    query = update.callback_query
    await query.answer()
    text = "💰 *Bảng giá:*\n\n"
    for sp_id, sp in data["products"].items():
        text += f"{sp['emoji']} *{sp['name']}*\n   💵 {sp['price']:,}đ | 📦 Còn: {len(sp['items'])}\n\n"
    kb = [[InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def contact_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [[InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")]]
    await query.edit_message_text(
        "📞 *Liên hệ admin:*\n@lvt3011\n\nHỗ trợ 8:00 - 22:00 hàng ngày",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def my_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data    = load_data()
    query   = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    user_orders = [o for o in data["orders"].values() if str(o["user_id"]) == user_id]
    if not user_orders:
        text = "📦 Bạn chưa có đơn hàng nào."
    else:
        text = "📦 *Đơn hàng của bạn:*\n\n"
        for o in user_orders[-5:]:
            emoji = "✅" if o["status"] == "paid" else "⏳"
            text += f"{emoji} `{o['order_id']}` — {o['product_name']}\n   {o['quantity']} cái — {o['total']:,}đ\n\n"
    kb = [[InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def buy_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data  = load_data()
    query = update.callback_query
    await query.answer()
    sp_id = query.data.replace("buy_", "")
    sp    = data["products"].get(sp_id)
    if not sp:
        await query.edit_message_text("❌ Sản phẩm không tồn tại.")
        return ConversationHandler.END
    stock = len(sp["items"])
    if stock == 0:
        kb = [[InlineKeyboardButton("🔙 Quay lại", callback_data="view_products")]]
        await query.edit_message_text("❌ Sản phẩm này đã hết hàng!", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    ctx.user_data["selected_product"] = sp_id
    btns = [InlineKeyboardButton(str(q), callback_data=f"qty_{q}") for q in [1,2,3,5] if q <= stock]
    kb   = [btns, [InlineKeyboardButton("🔙 Quay lại", callback_data="view_products")]]
    await query.edit_message_text(
        f"{sp['emoji']} *{sp['name']}*\n💵 {sp['price']:,}đ/cái | 📦 Còn: {stock}\n\nChọn số lượng:",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return CHOOSING_QTY

async def choose_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data  = load_data()
    query = update.callback_query
    await query.answer()
    qty   = int(query.data.replace("qty_", ""))
    sp_id = ctx.user_data.get("selected_product")
    sp    = data["products"].get(sp_id)
    if not sp or len(sp["items"]) < qty:
        await query.edit_message_text("❌ Không đủ hàng!")
        return ConversationHandler.END

    order_id = "ORD" + uuid.uuid4().hex[:8].upper()
    total    = sp["price"] * qty
    order    = {
        "order_id": order_id, "user_id": query.from_user.id,
        "username": query.from_user.username or "",
        "product_id": sp_id, "product_name": sp["name"],
        "quantity": qty, "total": total,
        "status": "pending", "created_at": datetime.now().isoformat(),
        "items_delivered": []
    }
    data["orders"][order_id] = order
    save_data(data)

    # Tạo QR VietQR
    qr_url   = get_qr_url(total, order_id)
    pay_text = PAYMENT_INFO.format(
        account_no=ACCOUNT_NO,
        account_name=ACCOUNT_NAME,
        total=total,
        order_id=order_id
    )
    caption = (f"📋 *Đơn hàng #{order_id}*\n\n"
               f"{sp['emoji']} {sp['name']}\n"
               f"Số lượng: {qty} | Tổng: *{total:,}đ*\n\n"
               f"{pay_text}\n\n"
               f"⏳ Bot tự xác nhận và giao hàng ngay sau khi nhận tiền!")

    kb = [[InlineKeyboardButton("🔙 Menu chính", callback_data="back_main")]]

    # Gửi ảnh QR kèm thông tin
    await query.message.reply_photo(
        photo=qr_url,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    await query.delete_message()

    # Thông báo admin
    await query.message.bot.send_message(
        chat_id=ADMIN_ID,
        text=(f"🛒 *Đơn mới:* `{order_id}`\n"
              f"👤 @{order['username']}\n"
              f"📦 {sp['name']} x{qty}\n"
              f"💰 {total:,}đ"),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ==================== ADMIN ====================
async def cmd_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    data = load_data()
    text = "📦 *Kho hàng:*\n\n"
    for sp_id, sp in data["products"].items():
        text += f"{sp['emoji']} {sp_id} — {sp['name']}: *{len(sp['items'])}* cái\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    data    = load_data()
    pending = [o for o in data["orders"].values() if o["status"] == "pending"]
    if not pending:
        await update.message.reply_text("✅ Không có đơn nào chờ.")
        return
    text = f"📋 *{len(pending)} đơn chờ:*\n\n"
    for o in pending[-10:]:
        text += f"• `{o['order_id']}` — {o['product_name']} x{o['quantity']} — {o['total']:,}đ\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_addstock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    data = load_data()
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("❌ Dùng: /addstock SP001 item1|item2")
        return
    sp_id = args[0]
    if sp_id not in data["products"]:
        await update.message.reply_text(f"❌ Không tìm thấy {sp_id}")
        return
    items = "|".join(args[1:]).split("|")
    items = [i.strip() for i in items if i.strip()]
    data["products"][sp_id]["items"].extend(items)
    save_data(data)
    await update.message.reply_text(
        f"✅ Đã nạp *{len(items)}* items vào {sp_id}. Kho: *{len(data['products'][sp_id]['items'])}*",
        parse_mode="Markdown")

async def cmd_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not ctx.args:
        await update.message.reply_text("❌ Dùng: /confirm ORDER_ID")
        return
    await deliver_order(ctx.args[0], ctx.bot)
    await update.message.reply_text(f"✅ Đã xác nhận đơn {ctx.args[0]}")

# ==================== MAIN ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_product, pattern="^buy_")],
        states={CHOOSING_QTY: [CallbackQueryHandler(choose_qty, pattern="^qty_")]},
        fallbacks=[CallbackQueryHandler(back_main, pattern="^back_main$")],
    )
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("stock",    cmd_stock))
    app.add_handler(CommandHandler("orders",   cmd_orders))
    app.add_handler(CommandHandler("addstock", cmd_addstock))
    app.add_handler(CommandHandler("confirm",  cmd_confirm))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(view_products, pattern="^view_products$"))
    app.add_handler(CallbackQueryHandler(price_list,    pattern="^price_list$"))
    app.add_handler(CallbackQueryHandler(contact_admin, pattern="^contact_admin$"))
    app.add_handler(CallbackQueryHandler(my_orders,     pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(back_main,     pattern="^back_main$"))

    t = threading.Thread(target=check_casso, args=(app.bot,), daemon=True)
    t.start()

    print("🚀 Bot dang chay... Tu dong kiem tra Casso moi 10 giay!")
    app.run_polling()

if __name__ == "__main__":
    main()s
