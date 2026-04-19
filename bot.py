import os, json, uuid, threading, logging, time
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

# ==================== CẤU HÌNH ====================
BOT_TOKEN    = "8051113710:AAFHZuU56KiAtXmraArDkJ4SJL8_r3i28T4"
ADMIN_ID     = 6765618686
CASSO_KEY    = "AK_CS.d01de3f03b2311f1a3ca79c2f1d864cb.iq8UrTh8GJxm4mnJyGm1SKOTOK4S9zR4fbZPeuulOfjcH9O6zlUpGrQEir7AFuD8hFufn8Bz"

SUPABASE_URL = "https://jcspqdbuypxqbkbglnfv.supabase.co"
SUPABASE_KEY = "sb_secret_fVC-_fsQwoz0K-5IK0VFjA_JEzUHwZ0"

BANK_ID      = "MB"
ACCOUNT_NO   = "0399265360"
ACCOUNT_NAME = "LAM VAN THEM"

PRODUCTS = {
    "SP001": {"name": "Mail New Reg Tay - Bao Trial YouTube",      "price": 15000, "emoji": "📧"},
    "SP002": {"name": "Tài Khoản PayPal Trắng - Không Lỗi",        "price": 20000, "emoji": "💳"},
    "SP003": {"name": "Mail Cổ Người Dùng Thật - Có Trial YouTube", "price": 40000, "emoji": "⭐"},
    "SP004": {"name": "Tài Khoản GitHub Trắng - Full Mail",         "price": 20000, "emoji": "🐙"},
    "SP005": {"name": "Mail Cổ Người Dùng Thật - Không Trial",      "price": 20000, "emoji": "📬"},
}

CHOOSING_QTY = 1
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ==================== SUPABASE ====================
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def sb_get(table, params=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=HEADERS, timeout=10)
    return r.json() if r.status_code == 200 else []

def sb_post(table, data):
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, json=data, timeout=10)
    return r.json() if r.status_code in [200, 201] else None

def sb_patch(table, match, data):
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?{match}", headers=HEADERS, json=data, timeout=10)
    return r.status_code in [200, 204]

def sb_delete(table, match):
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?{match}", headers=HEADERS, timeout=10)
    return r.status_code in [200, 204]

# ==================== KHO HÀNG ====================
def get_stock(sp_id):
    items = sb_get("stock", f"sp_id=eq.{sp_id}&select=id,item&limit=1000")
    return items if isinstance(items, list) else []

def get_stock_count(sp_id):
    return len(get_stock(sp_id))

def add_stock(sp_id, items):
    rows = [{"sp_id": sp_id, "item": item} for item in items]
    for row in rows:
        sb_post("stock", row)
    return len(rows)

def pop_stock(sp_id, qty):
    items = get_stock(sp_id)
    if len(items) < qty:
        return None
    chosen = items[:qty]
    for row in chosen:
        sb_delete("stock", f"id=eq.{row['id']}")
    return [row["item"] for row in chosen]

# ==================== ĐƠN HÀNG ====================
def create_order(order):
    return sb_post("orders", order)

def get_order(order_id):
    rows = sb_get("orders", f"order_id=eq.{order_id}")
    return rows[0] if rows else None

def update_order(order_id, data):
    return sb_patch("orders", f"order_id=eq.{order_id}", data)

def get_user_orders(user_id):
    return sb_get("orders", f"user_id=eq.{user_id}&order=created_at.desc&limit=5")

def get_casso_state():
    rows = sb_get("state", "key=eq.last_casso_id")
    return int(rows[0]["value"]) if rows else 0

def set_casso_state(val):
    rows = sb_get("state", "key=eq.last_casso_id")
    if rows:
        sb_patch("state", "key=eq.last_casso_id", {"value": str(val)})
    else:
        sb_post("state", {"key": "last_casso_id", "value": str(val)})

# ==================== VietQR ====================
def get_qr_url(amount, order_id):
    return (f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-compact2.png"
            f"?amount={amount}&addInfo={order_id}"
            f"&accountName={ACCOUNT_NAME.replace(' ', '%20')}")

# ==================== CASSO POLLING ====================
def check_casso(bot):
    import asyncio
    while True:
        try:
            last_id = get_casso_state()
            headers = {"Authorization": f"Apikey {CASSO_KEY}"}
            resp = requests.get(
                "https://oauth.casso.vn/v2/transactions?sort=DESC&pageSize=20",
                headers=headers, timeout=10)
            if resp.status_code == 200:
                txs = resp.json().get("data", {}).get("records", [])
                for tx in reversed(txs):
                    tx_id = tx.get("id", 0)
                    if tx_id <= last_id:
                        continue
                    set_casso_state(tx_id)
                    desc   = tx.get("description", "").upper()
                    amount = tx.get("amount", 0)
                    # Tìm đơn khớp
                    pending = sb_get("orders", "status=eq.pending&limit=100")
                    for order in (pending if isinstance(pending, list) else []):
                        oid = order.get("order_id", "").upper()
                        if oid in desc and amount >= order.get("total", 0):
                            loop = asyncio.new_event_loop()
                            loop.run_until_complete(deliver_order(order["order_id"], bot))
                            loop.close()
                            break
        except Exception as e:
            logger.warning(f"Casso error: {e}")
        time.sleep(10)

# ==================== GIAO HÀNG ====================
async def deliver_order(order_id, bot):
    order = get_order(order_id)
    if not order or order.get("status") == "paid":
        return
    sp_id = order["product_id"]
    qty   = order["quantity"]
    delivered = pop_stock(sp_id, qty)
    if not delivered:
        await bot.send_message(chat_id=order["user_id"],
            text=f"⚠️ Đơn #{order_id} đã thanh toán nhưng hết hàng. Admin sẽ liên hệ sớm!")
        await bot.send_message(chat_id=ADMIN_ID,
            text=f"🚨 Đơn {order_id} hết hàng! Cần nạp thêm {sp_id}.")
        return
    update_order(order_id, {
        "status": "paid",
        "items_delivered": json.dumps(delivered, ensure_ascii=False),
        "paid_at": datetime.now().isoformat()
    })
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
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Xem sản phẩm",     callback_data="view_products")],
        [InlineKeyboardButton("💰 Bảng giá",          callback_data="price_list")],
        [InlineKeyboardButton("📞 Liên hệ admin",     callback_data="contact_admin")],
        [InlineKeyboardButton("📦 Đơn hàng của tôi", callback_data="my_orders")],
    ])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào mừng đến *Candy Shop*!\nChọn chức năng bên dưới:",
        reply_markup=main_kb(), parse_mode="Markdown")

async def back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👋 Chào mừng đến *Candy Shop*!\nChọn chức năng bên dưới:",
        reply_markup=main_kb(), parse_mode="Markdown")
    return ConversationHandler.END

async def view_products(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = []
    for sp_id, sp in PRODUCTS.items():
        cnt = get_stock_count(sp_id)
        kb.append([InlineKeyboardButton(
            f"{sp['emoji']} {sp['name']} — {sp['price']:,}đ ({cnt} còn)",
            callback_data=f"buy_{sp_id}")])
    kb.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")])
    await query.edit_message_text("🛍 *Danh sách sản phẩm:*",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def price_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💰 *Bảng giá:*\n\n"
    for sp_id, sp in PRODUCTS.items():
        cnt = get_stock_count(sp_id)
        text += f"{sp['emoji']} *{sp['name']}*\n   💵 {sp['price']:,}đ | 📦 Còn: {cnt}\n\n"
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
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    orders  = get_user_orders(user_id)
    if not orders:
        text = "📦 Bạn chưa có đơn hàng nào."
    else:
        text = "📦 *Đơn hàng của bạn:*\n\n"
        for o in orders:
            emoji = "✅" if o["status"] == "paid" else "⏳"
            text += f"{emoji} `{o['order_id']}` — {o['product_name']}\n   {o['quantity']} cái — {o['total']:,}đ\n\n"
    kb = [[InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def buy_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sp_id = query.data.replace("buy_", "")
    sp    = PRODUCTS.get(sp_id)
    if not sp:
        await query.edit_message_text("❌ Sản phẩm không tồn tại.")
        return ConversationHandler.END
    stock = get_stock_count(sp_id)
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
    query = update.callback_query
    await query.answer()
    qty   = int(query.data.replace("qty_", ""))
    sp_id = ctx.user_data.get("selected_product")
    sp    = PRODUCTS.get(sp_id)
    if not sp:
        await query.edit_message_text("❌ Lỗi sản phẩm!")
        return ConversationHandler.END
    stock = get_stock_count(sp_id)
    if stock < qty:
        await query.edit_message_text("❌ Không đủ hàng!")
        return ConversationHandler.END
    order_id = "ORD" + uuid.uuid4().hex[:8].upper()
    total    = sp["price"] * qty
    order = {
        "order_id":    order_id,
        "user_id":     query.from_user.id,
        "username":    query.from_user.username or "",
        "product_id":  sp_id,
        "product_name": sp["name"],
        "quantity":    qty,
        "total":       total,
        "status":      "pending",
        "created_at":  datetime.now().isoformat(),
        "items_delivered": "[]"
    }
    create_order(order)
    qr_url  = get_qr_url(total, order_id)
    caption = (f"📋 *Đơn hàng #{order_id}*\n\n"
               f"{sp['emoji']} {sp['name']}\n"
               f"Số lượng: {qty} | Tổng: *{total:,}đ*\n\n"
               f"🏦 *Thông tin chuyển khoản:*\n"
               f"• Ngân hàng: MB BANK\n"
               f"• Số TK: `{ACCOUNT_NO}`\n"
               f"• Chủ TK: {ACCOUNT_NAME}\n"
               f"• Số tiền: *{total:,}đ*\n"
               f"• Nội dung CK: `{order_id}`\n\n"
               f"📱 *Quét QR bên trên để thanh toán tự động!*\n\n"
               f"⏳ Bot tự xác nhận và giao hàng ngay sau khi nhận tiền!")
    kb = [[InlineKeyboardButton("🔙 Menu chính", callback_data="back_main")]]
    await query.message.reply_photo(photo=qr_url, caption=caption,
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    await query.delete_message()
    await query.message.bot.send_message(chat_id=ADMIN_ID,
        text=(f"🛒 *Đơn mới:* `{order_id}`\n"
              f"👤 @{order['username']}\n"
              f"📦 {sp['name']} x{qty}\n💰 {total:,}đ"),
        parse_mode="Markdown")
    return ConversationHandler.END

# ==================== ADMIN ====================
async def cmd_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = "📦 *Kho hàng:*\n\n"
    for sp_id, sp in PRODUCTS.items():
        cnt = get_stock_count(sp_id)
        text += f"{sp['emoji']} {sp_id} — {sp['name']}: *{cnt}* cái\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    pending = sb_get("orders", "status=eq.pending&limit=10")
    if not pending:
        await update.message.reply_text("✅ Không có đơn nào chờ.")
        return
    text = f"📋 *{len(pending)} đơn chờ:*\n\n"
    for o in pending:
        text += f"• `{o['order_id']}` — {o['product_name']} x{o['quantity']} — {o['total']:,}đ\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_addstock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("❌ Dùng: /addstock SP001 item1|item2")
        return
    sp_id = args[0]
    if sp_id not in PRODUCTS:
        await update.message.reply_text(f"❌ Không tìm thấy {sp_id}")
        return
    items = "|".join(args[1:]).split("|")
    items = [i.strip() for i in items if i.strip()]
    count = add_stock(sp_id, items)
    total = get_stock_count(sp_id)
    await update.message.reply_text(
        f"✅ Đã nạp *{count}* items vào {sp_id}. Kho: *{total}*",
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
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
