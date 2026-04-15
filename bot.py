from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

TOKEN = "8051113710:AAHy25DgNhU6Hhdu3Jcsjc0DYE39T-ZLSns"

# Nếu bạn biết chat_id Telegram của bạn thì điền vào để bot báo đơn tự động cho bạn.
# Không biết thì cứ để None, bot vẫn chạy bình thường.
ADMIN_CHAT_ID = None

ADMIN_TEXT = """
📞 Liên hệ admin:
Telegram: @lvt3011
SĐT: 0335931572
"""

MAIN_MENU, ASK_QTY = range(2)

PRODUCTS = {
    "Gmail 6 tháng trial": {
        "name": "Gmail người dùng thật trên 6 tháng có trial",
        "price": 40000
    },
    "Gmail 6 tháng no trial": {
        "name": "Gmail người dùng thật trên 6 tháng không trial",
        "price": 20000
    },
    "Gmail new 1-2 tuần trial": {
        "name": "Gmail new ngâm 1-2 tuần vô trial",
        "price": 15000
    },
    "Gmail new no trial": {
        "name": "Gmail new không bao trial",
        "price": 8000
    },
    "Paypal trắng TT": {
        "name": "Paypal trắng TT",
        "price": 20000
    }
}

main_keyboard = ReplyKeyboardMarkup(
    [
        ["Xem sản phẩm", "Bảng giá"],
        ["Đặt hàng", "Liên hệ admin"]
    ],
    resize_keyboard=True
)

product_keyboard = ReplyKeyboardMarkup(
    [
        ["Gmail 6 tháng trial", "Gmail 6 tháng no trial"],
        ["Gmail new 1-2 tuần trial", "Gmail new no trial"],
        ["Paypal trắng TT"],
        ["⬅️ Quay lại menu"]
    ],
    resize_keyboard=True
)

buy_keyboard = ReplyKeyboardMarkup(
    [
        ["Mua ngay", "⬅️ Quay lại DS"],
        ["🏠 Menu chính"]
    ],
    resize_keyboard=True
)


def format_vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "đ"


def get_price_text() -> str:
    lines = ["📦 Bảng giá:\n"]
    for key, item in PRODUCTS.items():
        lines.append(f"- {item['name']}: {format_vnd(item['price'])}")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Xin chào!\n\n🛒 Bot bán hàng tự động 24/7\n👇 Chọn chức năng bên dưới:",
        reply_markup=main_keyboard
    )
    return MAIN_MENU


async def handle_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Xem sản phẩm":
        await update.message.reply_text(
            "📂 Danh sách sản phẩm của shop:\n👇 Chọn sản phẩm bên dưới:",
            reply_markup=product_keyboard
        )
        return MAIN_MENU

    elif text in PRODUCTS:
        product = PRODUCTS[text]
        context.user_data["selected_product"] = text

        await update.message.reply_text(
            f"📦 Sản phẩm: {product['name']}\n"
            f"💰 Giá: {format_vnd(product['price'])}\n\n"
            f"👇 Chọn thao tác:",
            reply_markup=buy_keyboard
        )
        return MAIN_MENU

    elif text == "Mua ngay":
        selected = context.user_data.get("selected_product")
        if not selected:
            await update.message.reply_text(
                "Bạn chưa chọn sản phẩm.\nHãy bấm 'Xem sản phẩm' trước.",
                reply_markup=main_keyboard
            )
            return MAIN_MENU

        product = PRODUCTS[selected]
        await update.message.reply_text(
            f"✍️ Bạn đang mua: {product['name']}\n"
            f"💰 Đơn giá: {format_vnd(product['price'])}\n\n"
            f"Nhập số lượng cần mua:",
            reply_markup=ReplyKeyboardMarkup(
                [["1", "2", "3"], ["5", "10"], ["❌ Hủy"]],
                resize_keyboard=True
            )
        )
        return ASK_QTY

    elif text == "⬅️ Quay lại DS":
        await update.message.reply_text(
            "📂 Danh sách sản phẩm của shop:\n👇 Chọn sản phẩm bên dưới:",
            reply_markup=product_keyboard
        )
        return MAIN_MENU

    elif text == "🏠 Menu chính" or text == "⬅️ Quay lại menu":
        context.user_data.pop("selected_product", None)
        await update.message.reply_text(
            "🏠 Đã quay về menu chính.",
            reply_markup=main_keyboard
        )
        return MAIN_MENU

    elif text == "Bảng giá":
        await update.message.reply_text(get_price_text(), reply_markup=main_keyboard)
        return MAIN_MENU

    elif text == "Liên hệ admin":
        await update.message.reply_text(ADMIN_TEXT, reply_markup=main_keyboard)
        return MAIN_MENU

    elif text == "Đặt hàng":
        await update.message.reply_text(
            "Bạn hãy bấm 'Xem sản phẩm' rồi chọn đúng mặt hàng trước nhé.",
            reply_markup=product_keyboard
        )
        return MAIN_MENU

    await update.message.reply_text(
        "❗ Hãy bấm đúng các nút bên dưới nhé.",
        reply_markup=main_keyboard
    )
    return MAIN_MENU


async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "❌ Hủy":
        await update.message.reply_text(
            "Đã hủy đặt hàng.",
            reply_markup=main_keyboard
        )
        return MAIN_MENU

    if not text.isdigit():
        await update.message.reply_text(
            "Vui lòng nhập số lượng bằng số. Ví dụ: 1, 2, 3...",
            reply_markup=ReplyKeyboardMarkup(
                [["1", "2", "3"], ["5", "10"], ["❌ Hủy"]],
                resize_keyboard=True
            )
        )
        return ASK_QTY

    qty = int(text)
    if qty <= 0:
        await update.message.reply_text(
            "Số lượng phải lớn hơn 0.",
            reply_markup=ReplyKeyboardMarkup(
                [["1", "2", "3"], ["5", "10"], ["❌ Hủy"]],
                resize_keyboard=True
            )
        )
        return ASK_QTY

    selected = context.user_data.get("selected_product")
    if not selected:
        await update.message.reply_text(
            "Không tìm thấy sản phẩm đã chọn. Hãy chọn lại.",
            reply_markup=main_keyboard
        )
        return MAIN_MENU

    product = PRODUCTS[selected]
    total = product["price"] * qty

    order_msg = (
        "✅ XÁC NHẬN ĐƠN HÀNG\n\n"
        f"📦 Sản phẩm: {product['name']}\n"
        f"🔢 Số lượng: {qty}\n"
        f"💰 Đơn giá: {format_vnd(product['price'])}\n"
        f"🧾 Tổng tiền: {format_vnd(total)}\n\n"
        "📞 Admin sẽ liên hệ bạn sớm."
    )

    await update.message.reply_text(order_msg, reply_markup=main_keyboard)

    if ADMIN_CHAT_ID:
        user = update.effective_user
        admin_msg = (
            "📥 CÓ ĐƠN HÀNG MỚI\n\n"
            f"👤 User: @{user.username if user.username else 'không có username'}\n"
            f"🆔 ID: {user.id}\n"
            f"📦 Sản phẩm: {product['name']}\n"
            f"🔢 Số lượng: {qty}\n"
            f"💰 Tổng tiền: {format_vnd(total)}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg)
        except Exception:
            pass

    context.user_data.pop("selected_product", None)
    return MAIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Đã hủy.", reply_markup=main_keyboard)
    return MAIN_MENU


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main)],
            ASK_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
