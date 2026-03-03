import logging
import json
import requests
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# -------------------- إعداد التسجيل (logging) --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- حالات المحادثة --------------------
PHONE, PASSWORD, TARGET_PHONE = range(3)

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

# -------------------- بداية المحادثة --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يرسل رسالة ترحيب ويطلب الرقم."""
    user = update.effective_user
    await update.message.reply_text(
        f"مرحباً {user.first_name}!\n"
        "أهلاً بك في بوت إرسال هدايا فودافون.\n"
        "الرجاء إرسال رقم فودافون الخاص بك (مثال: 01012345678):"
    )
    return PHONE

# -------------------- استقبال الرقم --------------------
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يخزن الرقم ويطلب كلمة المرور."""
    phone = update.message.text.strip()
    # تحقق بسيط: الرقم يجب أن يتكون من أرقام فقط وطوله 11 رقم (تقريباً)
    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text("الرجاء إدخال رقم صحيح (أرقام فقط، 11 رقم مثلاً).")
        return PHONE
    context.user_data['phone'] = phone
    await update.message.reply_text("تم استلام الرقم. الآن الرجاء إرسال كلمة المرور:")
    return PASSWORD

# -------------------- استقبال كلمة المرور --------------------
async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يخزن كلمة المرور ويطلب الرقم المستهدف."""
    password = update.message.text.strip()
    if not password:
        await update.message.reply_text("كلمة المرور لا يمكن أن تكون فارغة. حاول مرة أخرى:")
        return PASSWORD
    context.user_data['password'] = password
    await update.message.reply_text("تم استلام كلمة المرور. الآن أرسل الرقم الذي تريد إرسال الهدية إليه:")
    return TARGET_PHONE

# -------------------- استقبال الرقم المستهدف وتنفيذ العملية --------------------
async def get_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يخزن الرقم المستهدف ويقوم بتنفيذ طلبات HTTP."""
    target = update.message.text.strip()
    if not target.isdigit() or len(target) < 10:
        await update.message.reply_text("الرجاء إدخال رقم صحيح.")
        return TARGET_PHONE

    context.user_data['target'] = target
    phone = context.user_data['phone']
    password = context.user_data['password']

    await update.message.reply_text("جاري تسجيل الدخول والحصول على البيانات... ⏳")

    # ---------- الخطوة 1: الحصول على access_token ----------
    auth_payload = {
        'grant_type': "password",
        'username': phone,
        'password': password,
        'client_secret': CLIENT_SECRET,
        'client_id': CLIENT_ID
    }
    try:
        response1 = requests.post(TOKEN_URL, data=auth_payload, headers=HEADERS_AUTH, timeout=30)
    except Exception as e:
        logger.error(f"خطأ في الاتصال بخدمة التوثيق: {e}")
        await update.message.reply_text("حدث خطأ في الاتصال بالخادم. حاول مرة أخرى لاحقاً.")
        return ConversationHandler.END

    if response1.status_code != 200:
        await update.message.reply_text("❌ رقم الهاتف أو كلمة المرور غير صحيحة. أعد المحاولة باستخدام /start")
        return ConversationHandler.END

    try:
        access_token = response1.json()['access_token']
    except (KeyError, json.JSONDecodeError):
        await update.message.reply_text("❌ استجابة غير متوقعة من الخادم. أعد المحاولة.")
        return ConversationHandler.END

    # ---------- الخطوة 2: جلب تفاصيل الهدية ----------
    params = {
        '@type': "Promo",
        '$.context.type': "nearbyRamadan26"
    }
    headers_promo = HEADERS_API.copy()
    headers_promo['Authorization'] = f"Bearer {access_token}"
    headers_promo['msisdn'] = phone
    headers_promo['x-dtpc'] = "8$7781247_562h50vPHEBDRMPUAFUMABJNUMWMBLCNOCMGLGU-0e0"  # قد يتغير لكن نتركه كما هو

    try:
        response2 = requests.get(PROMO_URL, params=params, headers=headers_promo, timeout=30)
    except Exception as e:
        logger.error(f"خطأ في جلب الهدية: {e}")
        await update.message.reply_text("حدث خطأ أثناء جلب الهدية. حاول مجدداً.")
        return ConversationHandler.END

    if response2.status_code != 200:
        await update.message.reply_text("❌ فشل في الحصول على بيانات الهدية. تأكد من اتصالك.")
        return ConversationHandler.END

    try:
        data = response2.json()
        # في السكربت الأصلي يتم استخدام data[1]، لكن يجب التأكد من وجوده
        if len(data) < 2:
            raise ValueError("لا توجد هدية متاحة")
        promo_item = data[1]
    except (IndexError, ValueError, json.JSONDecodeError) as e:
        logger.warning(f"لا توجد هدية أو استجابة غير متوقعة: {e}")
        await update.message.reply_text("🚫 لا يوجد لديك هدية متاحة حالياً.")
        return ConversationHandler.END

    # استخراج التفاصيل (المبلغ، الصلاحية، إلخ)
    amount = None
    validity = None
    validity_unit = None
    promo_id = promo_item.get("id")
    channel_id = promo_item.get("channel", {}).get("id")

    for char in promo_item.get("characteristics", []):
        name = char.get("name")
        if name == "amount":
            amount = char.get("value")
            amount_type = char.get("@type", "")
        elif name == "OfferValidity":
            validity = char.get("value")
        elif name == "OfferValidityUnit":
            validity_unit = char.get("value")

    if amount is None or promo_id is None or channel_id is None:
        await update.message.reply_text("❌ بيانات الهدية غير مكتملة.")
        return ConversationHandler.END

    # عرض تفاصيل الهدية للمستخدم
    details_msg = f"💰 الهدية: {amount}{amount_type} لمدة {validity}{validity_unit}"
    await update.message.reply_text(details_msg)

    # ---------- الخطوة 3: إرسال الهدية للرقم المستهدف ----------
    payload_send = {
        "@type": "Promo",
        "channel": {"id": channel_id},
        "context": {"type": "nearbyRamadan26"},
        "pattern": [{
            "id": promo_id,
            "characteristics": [
                {"name": "redemptionFlag", "value": "0"},
                {"name": "BMsisdn", "value": target}
            ]
        }]
    }

    try:
        response3 = requests.post(PROMO_URL, data=json.dumps(payload_send), headers=headers_promo, timeout=30)
    except Exception as e:
        logger.error(f"خطأ في إرسال الهدية: {e}")
        await update.message.reply_text("حدث خطأ أثناء إرسال الهدية.")
        return ConversationHandler.END

    if response3.status_code == 200:
        await update.message.reply_text(
            f"✅ تم إرسال الهدية بنجاح!\n"
            f"📱 من: {phone}\n"
            f"🎁 إلى: {target}\n"
            f"💵 المبلغ: {amount}{amount_type}\n"
            f"⏳ الصلاحية: {validity}{validity_unit}"
        )
    else:
        await update.message.reply_text(f"❌ فشل في إرسال الهدية. رمز الحالة: {response3.status_code}\n{response3.text}")

    # إنهاء المحادثة
    return ConversationHandler.END

# -------------------- إلغاء المحادثة --------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يلغي المحادثة ويعيد البوت للحالة الطبيعية."""
    await update.message.reply_text("تم إلغاء العملية. استخدم /start للبدء من جديد.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# -------------------- الخطأ في حالة عدم تطابق المدخلات --------------------
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """في حالة إرسال المستخدم رسالة غير متوقعة أثناء المحادثة."""
    await update.message.reply_text("الرجاء اتباع التعليمات. أرسل /start للبدء من جديد أو /cancel للإلغاء.")
    # نعيد نفس الحالة الحالية (لا نغيرها)
    # لكن لأننا لا نعرف الحالة الحالية بسهولة، الأفضل إرجاع None أو إعادة توجيه.
    # هنا سنعيد الحالة الحالية من context.user_data['state'] غير موجودة، لذا نستخدم -1 ثم نترك ConversationHandler يعيدنا للحالة المناسبة.
    return -1

# -------------------- الوظيفة الرئيسية --------------------
def main() -> None:
    """تشغيل البوت."""
    # ضع التوكن الخاص بك هنا
    TOKEN = "8791476397:AAHnp5P-gsbcG7FXqIPhcYNEjxqeMBHCZaY"

    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()

    # إعداد محادثة (conversation handler)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            TARGET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.COMMAND, fallback),  # لو أمر غير معروف
            MessageHandler(filters.ALL, fallback)       # أي رسالة أخرى
        ],
    )

    application.add_handler(conv_handler)

    # بدء البوت
    application.run_polling()

if __name__ == "__main__":
    main()
