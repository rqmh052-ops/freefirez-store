import logging
import json
import requests
import re
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

# الهيدر الخاص بالتسجيل (مأخوذ من السكربت السفلي)
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

# الهيدر الخاص بطلبات API (مأخوذ من السكربت السفلي)
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

# -------------------- دالة ترجمة المصطلحات فقط --------------------
def translate_terms(text):
    if not text: return ""
    text = str(text).upper().strip()
    
    # خريطة الترجمة للمصطلحات المتوقعة من السيرفر
    translations = {
        "UNITS": "وحدة",
        "UNIT": "وحدة",
        "MB": "ميجابايت",
        "GB": "جيجابايت",
        "MILES": "ميل",
        "HOURS": "ساعات",
        "HOUR": "ساعة",
        "DAYS": "أيام",
        "DAY": "يوم",
        "MINUTES": "دقائق",
        "MIN": "دقيقة"
    }
    return translations.get(text, text) # إذا لم يجد المصطلح يتركه كما هو

# -------------------- بداية المحادثة --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    # استخدام Markdown لجعل الاسم يظهر كمنشن (أزرق)
    mention = f"[{user.first_name}](tg://user?id={user.id})"
    
    await update.message.reply_text(
        f"مرحباً بك {mention}!\n"
        "أهلاً بك في بوت إرسال هدايا فودافون.\n"
        "الرجاء إرسال رقم فودافون الخاص بك:",
        parse_mode='Markdown'
    )
    return PHONE

# -------------------- استقبال الرقم --------------------
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    
    # حماية: التحقق من صحة رقم الهاتف المصري
    if not re.match(r"^01[0-2,5]\d{8}$", phone):
        await update.message.reply_text("⚠️ خطأ: يرجى إدخال رقم فودافون صحيح مكون من 11 رقم يبدأ بـ 01")
        return PHONE
        
    context.user_data['phone'] = phone
    await update.message.reply_text("✅ تم استلام الرقم.\nالآن الرجاء إرسال **كلمة المرور**:", parse_mode='Markdown')
    return PASSWORD

# -------------------- استقبال كلمة المرور --------------------
async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text.strip()
    
    # حماية: منع النصوص القصيرة جداً أو الطويلة جداً
    if len(password) < 4 or len(password) > 50:
        await update.message.reply_text("⚠️ كلمة المرور غير صالحة، يرجى المحاولة مجدداً:")
        return PASSWORD
        
    context.user_data['password'] = password
    await update.message.reply_text("🎯 تم استلام كلمة المرور.\nالآن أرسل **الرقم الذي تريد إرسال الهدية إليه**:", parse_mode='Markdown')
    return TARGET_PHONE

# -------------------- التنفيذ النهائي --------------------
async def get_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = update.message.text.strip()
    
    # التحقق من رقم المستلم
    if not re.match(r"^01[0-2,5]\d{8}$", target):
        await update.message.reply_text("⚠️ يرجى إدخال رقم مستلم صحيح:")
        return TARGET_PHONE

    phone = context.user_data['phone']
    password = context.user_data['password']

    status_msg = await update.message.reply_text("🔍 جاري تسجيل الدخول والحصول على البيانات... ⏳")

    # ---------- الخطوة 1: الحصول على access_token ----------
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
            await status_msg.edit_text("❌ فشل تسجيل الدخول. تأكد من الرقم وكلمة المرور.")
            return ConversationHandler.END

        token = r1.json()['access_token']

        # ---------- الخطوة 2: جلب تفاصيل الهدية ----------
        headers_promo = HEADERS_API.copy()
        headers_promo['Authorization'] = f"Bearer {token}"
        headers_promo['msisdn'] = phone
        headers_promo['x-dtpc'] = "8$7781247_562h50vPHEBDRMPUAFUMABJNUMWMBLCNOCMGLGU-0e0"  # ثابت كما في السكربت

        params = {
            '@type': "Promo",
            '$.context.type': "nearbyRamadan26"
        }

        r2 = requests.get(PROMO_URL, params=params, headers=headers_promo, timeout=30)
        if r2.status_code != 200:
            await status_msg.edit_text("❌ فشل في الحصول على بيانات الهدية.")
            return ConversationHandler.END

        data = r2.json()
        if not isinstance(data, list) or len(data) < 2:
            await status_msg.edit_text("🎁 للأسف، لا توجد هدايا متاحة على هذا الرقم حالياً.")
            return ConversationHandler.END

        promo = data[1]
        p_id = promo.get("id")
        c_id = promo.get("channel", {}).get("id")

        # استخراج القيم وترجمة الوحدات فقط
        amount = "0"
        unit = ""
        validity = ""
        v_unit = ""

        for char in promo.get("characteristics", []):
            name = char.get("name")
            val = char.get("value")
            
            if name == "amount":
                amount = val  # ترك القيمة كما هي
                unit = translate_terms(char.get("@type", ""))
            elif name == "OfferValidity":
                validity = val
            elif name == "OfferValidityUnit":
                v_unit = translate_terms(val)

        # ---------- الخطوة 3: إرسال الهدية ----------
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
        else:
            await status_msg.edit_text(f"❌ حدث خطأ أثناء الإرسال. قد تكون الهدية استُخدمت بالفعل. رمز الخطأ: {r3.status_code}")

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text("🛑 حدث خطأ تقني غير متوقع.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("تم إلغاء العملية. أرسل /start للبدء مجدداً.")
    return ConversationHandler.END

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("الرجاء اتباع التعليمات. أرسل /start للبدء من جديد أو /cancel للإلغاء.")
    return -1

def main() -> None:
    # ضع التوكن الخاص بك هنا
    TOKEN = "8791476397:AAHnp5P-gsbcG7FXqIPhcYNEjxqeMBHCZaY"
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
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

    application.add_handler(conv_handler)
    print("البوت يعمل الآن...")
    application.run_polling()

if __name__ == "__main__":
    main()
