import os
import re
import time

from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    JoinEvent,
    MemberJoinedEvent,
    SourceGroup,
    ImageSendMessage,
    Mention,
    Mentionee,
)

app = Flask(__name__)

# -----------------------------
# CONFIG
# -----------------------------

CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET")

if CHANNEL_ACCESS_TOKEN is None or CHANNEL_SECRET is None:
    raise ValueError("ต้องตั้งค่า CHANNEL_ACCESS_TOKEN และ CHANNEL_SECRET ใน Environment Variables")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# >>>>>>> แก้ค่าตรงนี้ <<<<<<

# userId ของแอดมิน (หาได้จาก log หรือให้บอทตอบกลับ user_id เวลาแอดมินพิมพ์ !me)
ADMIN_IDS = {
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # ใส่ของคุณแทน
}

# รูปต้อนรับ (ต้องเป็นลิงก์ https ที่เข้าถึงได้จากอินเทอร์เน็ต)
WELCOME_IMAGE_URL = "https://example.com/welcome.jpg"

# ข้อความกฎกลุ่ม
WELCOME_RULES_TEXT = (
    "👋 ยินดีต้อนรับเข้าสู่กลุ่ม VVIP\n"
    "กฎกลุ่มมีดังนี้:\n"
    "1️⃣ ห้ามส่งลิงก์ทุกชนิดโดยไม่ได้รับอนุญาต\n"
    "2️⃣ ห้ามโฆษณา / เว็บพนัน / การพนันทุกประเภท\n"
    "3️⃣ เคารพกันและกัน ใช้คำสุภาพ\n"
    "4️⃣ ฝ่าฝืนอาจถูกเตือนและเตะออกจากกลุ่ม\n"
)

# list คนที่เคยโดน “แบน/เตือนรุนแรง”
banned_users = set()

# กันสแปมข้อความซ้ำ
user_last_message = {}  # {user_id: (text, timestamp)}
REPEAT_WINDOW = 7

LINK_PATTERN = re.compile(r"(https?://|www\.)", re.IGNORECASE)

BAD_KEYWORDS = [
    "บาคาร่า", "bacara", "bacarat", "baccarat",
    "คาสิโน", "casino", "slot", "สล็อต", "ยิงปลา",
    "หวยหุ้น", "หวยยี่กี", "หวยฮานอย", "หวยลาว",
    "แทงบอล", "แทงบอลออนไลน์", "พนันบอล", "พนัน",
]


# -----------------------------
# HELPERS
# -----------------------------

def is_admin(user_id: str) -> bool:
    return user_id in ADMIN_IDS


def is_link(text: str) -> bool:
    return bool(LINK_PATTERN.search(text))


def is_bad_keyword(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in BAD_KEYWORDS)


def is_repeat(user_id: str, text: str) -> bool:
    now = time.time()
    last = user_last_message.get(user_id)
    user_last_message[user_id] = (text, now)

    if not last:
        return False
    last_text, last_time = last
    if text == last_text and (now - last_time) <= REPEAT_WINDOW:
        return True
    return False


def make_admin_mention_text(group_id: str, base_text: str) -> TextSendMessage:
    """สร้างข้อความที่แท็กแอดมินทุกคน"""
    mentionees = []
    text_parts = []
    index = 0

    for admin_id in ADMIN_IDS:
        try:
            profile = line_bot_api.get_group_member_profile(group_id, admin_id)
            name = f"@{profile.display_name} "
            text_parts.append(name)
            mentionees.append(Mentionee(index=index, length=len(name), user_id=admin_id))
            index += len(name)
        except Exception:
            # ถ้าดึง profile ไม่ได้ ก็ข้ามชื่อ
            pass

    text = base_text + "\n" + "".join(text_parts) if text_parts else base_text
    return TextSendMessage(text=text, mention=Mention(mentionees=mentionees))


def mention_all_members(group_id: str, header_text: str) -> TextSendMessage:
    """แท็กทุกคนในกลุ่ม (ได้สูงสุด ~20 คนต่อข้อความ)"""
    member_ids = line_bot_api.get_group_member_ids(group_id)
    mentionees = []
    text_parts = []
    index = len(header_text) + 1

    text = header_text + "\n"

    # จำกัดแค่ 20 คนต่อข้อความเพื่อความปลอดภัย
    for user_id in member_ids[:20]:
        try:
            profile = line_bot_api.get_group_member_profile(group_id, user_id)
            name = f"@{profile.display_name} "
            text += name
            mentionees.append(Mentionee(index=index, length=len(name), user_id=user_id))
            index += len(name)
        except Exception:
            pass

    return TextSendMessage(text=text, mention=Mention(mentionees=mentionees))


# -----------------------------
# WEBHOOK
# -----------------------------

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


# -----------------------------
# EVENTS
# -----------------------------

@handler.add(JoinEvent)
def handle_join(event: JoinEvent):
    if isinstance(event.source, SourceGroup):
        text = (
            "สวัสดีครับ ขอบคุณที่เชิญผมเข้ากลุ่ม 🙏\n"
            "ผมจะช่วยเฝ้าลิงก์ / คำต้องห้าม / ข้อความซ้ำให้เองครับ ✅\n"
            "พิมพ์ !help เพื่อดูคำสั่งได้เลย"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text))


@handler.add(MemberJoinedEvent)
def handle_member_joined(event: MemberJoinedEvent):
    """มีคนถูกเชิญ/เข้ากลุ่ม"""
    if not isinstance(event.source, SourceGroup):
        return

    group_id = event.source.group_id

    messages = []

    # ส่งรูปต้อนรับ + ข้อความกฎกลุ่ม
    messages.append(
        ImageSendMessage(
            original_content_url=WELCOME_IMAGE_URL,
            preview_image_url=WELCOME_IMAGE_URL,
        )
    )
    messages.append(TextSendMessage(text=WELCOME_RULES_TEXT))

    # ถ้าอยู่ใน blacklist ให้แจ้งแอดมิน
    for member in event.joined.members:
        if member.user_id in banned_users:
            warn_text = make_admin_mention_text(
                group_id,
                f"⚠️ สมาชิกที่เคยถูกแบน/เตือนรุนแรงกลับเข้ากลุ่มอีกครั้ง: {member.user_id}",
            )
            messages.append(warn_text)

    line_bot_api.reply_message(event.reply_token, messages)


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    user_id = event.source.user_id
    text = event.message.text.strip()
    source = event.source

    is_group = isinstance(source, SourceGroup)
    group_id = source.group_id if is_group else None

    # ---------------- COMMANDS ----------------

    if text.lower() == "!help":
        reply = (
            "📌 คำสั่งบอทกลุ่ม\n"
            "• !help – แสดงคำสั่งทั้งหมด\n"
            "• !status – เช็กสถานะบอท\n"
            "• แอด – แท็กสมาชิกทุกคนในกลุ่ม (สูงสุด ~20 คน)\n"
            "• ล้าง – (แอดมิน) ล้างรายชื่อ blacklist ที่เคยถูกแบน\n"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if text.lower() == "!status":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="บอททำงานปกติครับ ✅"),
        )
        return

    if text == "ล้าง" and is_admin(user_id):
        banned_users.clear()
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text="✅ ล้าง blacklist เรียบร้อยแล้ว")
        )
        return

    if text == "แอด" and is_group:
        msg = mention_all_members(group_id, "📢 เรียกทุกคนมาดูหน่อยครับ")
        line_bot_api.reply_message(event.reply_token, msg)
        return

    # ---------------- ANTI-SPAM ----------------

    if is_group:
        # ถ้าไม่ใช่แอดมิน
        if not is_admin(user_id):

            # 1) ส่งลิงก์ → เตือน + แท็กแอดมิน
            if is_link(text):
                warn_msg = make_admin_mention_text(
                    group_id,
                    "🚫 ตรวจพบการส่งลิงก์ในกลุ่มจากสมาชิกท่านหนึ่ง กรุณาแอดมินพิจารณาเตะออกครับ",
                )
                line_bot_api.reply_message(event.reply_token, warn_msg)
                banned_users.add(user_id)
                return

            # 2) คำต้องห้าม
            if is_bad_keyword(text):
                warn_msg = make_admin_mention_text(
                    group_id,
                    "🚫 ตรวจพบคำต้องห้าม/น่าสงสัยในกลุ่ม กรุณาแอดมินตรวจสอบครับ",
                )
                line_bot_api.reply_message(event.reply_token, warn_msg)
                banned_users.add(user_id)
                return

            # 3) ข้อความซ้ำรัว ๆ
            if is_repeat(user_id, text):
                warn_msg = make_admin_mention_text(
                    group_id,
                    "⚠️ ตรวจพบการพิมพ์ข้อความซ้ำรัว ๆ กรุณาแอดมินตรวจสอบครับ",
                )
                line_bot_api.reply_message(event.reply_token, warn_msg)
                return

    # แชทส่วนตัว – ตอบเบา ๆ พอ
    if not is_group:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="ผมคือบอทป้องกันสแปมในกลุ่มครับ 🙏\nเชิญผมเข้ากลุ่มแล้วพิมพ์ !help เพื่อดูคำสั่งได้เลย"
            ),
        )
    # ถ้าอยู่ในกลุ่มและไม่เข้าข่ายอะไรเลย → เงียบ
    else:
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
