import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import storage

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---- Conversation states (order flow) ----
CATEGORY, ITEM_DESC, QTY, FULLNAME, PHONE, CITY_NP, CONFIRM = range(7)

# ---- Conversation states (admin: add category) ----
ADD_CATEGORY_NAME = 100


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛍 Створити замовлення", callback_data="start_order")]]
    )


def categories_keyboard():
    categories = storage.get_categories()
    buttons = [
        [InlineKeyboardButton(name, callback_data=f"cat_{i}")]
        for i, name in enumerate(categories)
    ]
    return InlineKeyboardMarkup(buttons)


# ---------------- Client flow ----------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вітаємо у нашому магазині матеріалів для манікюру! 💅\n\n"
        "Щоб оформити замовлення, натисніть кнопку нижче.",
        reply_markup=main_menu_keyboard(),
    )


async def start_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    categories = storage.get_categories()
    if not categories:
        await query.message.reply_text(
            "На жаль, каталог поки що порожній. Спробуйте пізніше."
        )
        return ConversationHandler.END
    context.user_data.clear()
    await query.message.reply_text(
        "Оберіть категорію товару:", reply_markup=categories_keyboard()
    )
    return CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("_")[1])
    categories = storage.get_categories()
    if index >= len(categories):
        await query.message.reply_text("Ця категорія більше недоступна, спробуйте ще раз /start")
        return ConversationHandler.END
    context.user_data["category"] = categories[index]
    await query.message.reply_text(
        f"Категорія: {categories[index]}\n\n"
        "Напишіть, що саме ви хочете замовити (назва, колір, номер відтінку тощо):"
    )
    return ITEM_DESC


async def item_desc_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["item_desc"] = update.message.text.strip()
    await update.message.reply_text("Вкажіть кількість (наприклад: 2):")
    return QTY


async def qty_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["qty"] = update.message.text.strip()
    await update.message.reply_text("Введіть ваше ПІБ (Прізвище Ім'я По батькові):")
    return FULLNAME


async def fullname_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fullname"] = update.message.text.strip()
    contact_button = KeyboardButton("📱 Надіслати мій номер", request_contact=True)
    keyboard = ReplyKeyboardMarkup(
        [[contact_button]], one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        "Вкажіть номер телефону (натисніть кнопку або введіть вручну):",
        reply_markup=keyboard,
    )
    return PHONE


async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    context.user_data["phone"] = phone
    await update.message.reply_text(
        "Вкажіть місто і номер відділення Нової пошти одним повідомленням.\n"
        "Наприклад: Вінниця, відділення 15",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CITY_NP


async def city_np_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["city_np"] = update.message.text.strip()
    d = context.user_data
    summary = (
        "Перевірте, будь ласка, ваше замовлення:\n\n"
        f"🛍 Категорія: {d['category']}\n"
        f"📦 Товар: {d['item_desc']}\n"
        f"🔢 Кількість: {d['qty']}\n"
        f"👤 ПІБ: {d['fullname']}\n"
        f"📱 Телефон: {d['phone']}\n"
        f"📍 Місто/НП: {d['city_np']}\n"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Підтвердити", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Скасувати", callback_data="confirm_no"),
            ]
        ]
    )
    await update.message.reply_text(summary, reply_markup=keyboard)
    return CONFIRM


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        context.user_data.clear()
        await query.message.reply_text(
            "Замовлення скасовано. Щоб почати знову, натисніть /start"
        )
        return ConversationHandler.END

    d = context.user_data
    user = query.from_user
    order = {
        "category": d["category"],
        "item_desc": d["item_desc"],
        "qty": d["qty"],
        "fullname": d["fullname"],
        "phone": d["phone"],
        "city_np": d["city_np"],
        "user_id": user.id,
        "username": user.username,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    order_id = storage.save_order(order)

    who = f"@{user.username}" if user.username else f"id {user.id}"

    admin_text = (
        f"🔔 НОВЕ ЗАМОВЛЕННЯ №{order_id}\n\n"
        f"👤 ПІБ: {d['fullname']}\n"
        f"📱 Телефон: {d['phone']}\n"
        f"📍 {d['city_np']}\n\n"
        f"🛍 Категорія: {d['category']}\n"
        f"📦 Товар: {d['item_desc']}\n"
        f"🔢 Кількість: {d['qty']}\n\n"
        f"Хто оформив: {who}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception as e:
            logger.warning("Не вдалось надіслати адміну %s: %s", admin_id, e)

    await query.message.reply_text(
        f"✅ Замовлення №{order_id} прийнято!\nМи зв'яжемось з вами найближчим часом."
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Скасовано. Щоб почати знову, натисніть /start",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ---------------- Admin flow ----------------


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 Переглянути каталог", callback_data="admin_list")],
            [InlineKeyboardButton("➕ Додати категорію", callback_data="admin_add")],
            [InlineKeyboardButton("➖ Видалити категорію", callback_data="admin_del")],
        ]
    )
    await update.message.reply_text("Адмін-панель каталогу:", reply_markup=keyboard)


async def admin_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    categories = storage.get_categories()
    if not categories:
        text = "Каталог порожній."
    else:
        text = "Поточний каталог:\n\n" + "\n".join(
            f"{i + 1}. {name}" for i, name in enumerate(categories)
        )
    await query.message.reply_text(text)


async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END
    await query.message.reply_text("Напишіть назву нової категорії:")
    return ADD_CATEGORY_NAME


async def admin_add_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    storage.add_category(name)
    await update.message.reply_text(f"✅ Категорію «{name}» додано до каталогу.")
    return ConversationHandler.END


async def admin_del_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    categories = storage.get_categories()
    if not categories:
        await query.message.reply_text("Каталог порожній, видаляти нічого.")
        return
    buttons = [
        [InlineKeyboardButton(f"🗑 {name}", callback_data=f"admin_delidx_{i}")]
        for i, name in enumerate(categories)
    ]
    await query.message.reply_text(
        "Оберіть категорію для видалення:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_del_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    index = int(query.data.split("_")[2])
    removed = storage.remove_category(index)
    if removed:
        await query.message.reply_text(f"🗑 Категорію «{removed}» видалено.")
    else:
        await query.message.reply_text("Не вдалось видалити, спробуйте ще раз.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не знайдено. Перевірте файл .env")
    if not ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS порожній — сповіщення про замовлення нікуди не надсилатимуться!"
        )

    application = Application.builder().token(BOT_TOKEN).build()

    order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_order_callback, pattern="^start_order$")],
        states={
            CATEGORY: [CallbackQueryHandler(category_chosen, pattern="^cat_")],
            ITEM_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, item_desc_received)],
            QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, qty_received)],
            FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fullname_received)],
            PHONE: [
                MessageHandler(
                    (filters.TEXT & ~filters.COMMAND) | filters.CONTACT, phone_received
                )
            ],
            CITY_NP: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_np_received)],
            CONFIRM: [CallbackQueryHandler(confirm_callback, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    admin_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_start, pattern="^admin_add$")],
        states={
            ADD_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name_received)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(order_conv)
    application.add_handler(admin_add_conv)
    application.add_handler(CallbackQueryHandler(admin_list_callback, pattern="^admin_list$"))
    application.add_handler(CallbackQueryHandler(admin_del_start, pattern="^admin_del$"))
    application.add_handler(
        CallbackQueryHandler(admin_del_confirm, pattern="^admin_delidx_")
    )

    logger.info("Бот запущено.")
    application.run_polling()


if __name__ == "__main__":
    main()
