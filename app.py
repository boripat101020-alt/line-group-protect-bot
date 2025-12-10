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
    SourceGroup,
)

app = Flask(__name__)

# เอาค่าจาก Environment Variables บน Render
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET")

if CHANNEL_ACCESS_TOKEN is None or CHANNEL_SECRET is None:
    raise ValueError("ต้องตั้งค่า CHANNEL_ACCESS_TOKEN และ CHANNEL_SECRET ใน Environment Variables")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ==============================
# ตั้งค่าป้องกันสแปม
# ==============================

BAD_KEYWORDS = [
    "บาคาร่า", "bacara", "bacarat", "baccarat",
    "คาสิโน", "casino", "slot", "สล็อต", "ยิงปลา",
    "หวยหุ้น", "หวยยี่กี", "หวยฮานอย", "หวยลาว",
    "แทงบอล", "แทงบอลออนไลน์", "พนันบอล", "พนัน",
]

LINK_PATTERN = re.compile(r"(https?://|www\.)", re.IGNORECASE)

user_last_message = {}  # {user_id: (text, timestamp)}
user_warn_count = {}    # {user_id: warn_times}

REPEAT_WINDOW = 7        # วินาทีที่ถือว่าส่งซ้ำรัว ๆ
MAX_WARN = 3             # เตือนกี่ครั้งถึงจะบอกให้แอดมินจัดการ


@app.route("/callback", methods=["POST"])  # <== ตรงกับ URL ใน LINE
def callback():
    signature = request.headers.get("X-Line-Signature", "")

    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(JoinEvent)
def handle_join(event: JoinEvent):
    if isinstance(event.source, SourceGroup):
        text = (
            "สวัสดีครับ ขอบคุณที่เชิญผมเข้ากลุ่ม 🙏\n"
            "ผมจะช่วยป้องกันสแปมลิงก์ / เว็บพนัน / ข้อความซ้ำรัว ๆ ให้เอง ✅\n"
            "พิมพ์ !help เพื่อดูคำสั่งได้ครับ"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text))
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="สวัสดีครับ ผมคือบอทป้องกันสแปม ใช้ในกลุ่มจะมีประโยชน์ที่สุด 😄"),
        )


def is_bad_keyword(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in BAD_KEYWORDS)


def is_link(text: str) -> bool:
    return bool(LINK_PATTERN.search(text))


def is_repeat_spam(user_id: str, text: str) -> bool:
    now = time.time()
    last = user_last_message.get(user_id)

    user_last_message[user_id] = (text, now)

    if not last:
        return False

    last_text, last_time = last
    if text == last_text and (now - last_time) <= REPEAT_WINDOW:
        return True
    return False


def add_warn(user_id: str) -> int:
    count = user_warn_count.get(user_id, 0) + 1
    user_warn_count[user_id] = count
    return count


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    user_id = event.source.user_id
    text = event.message.text.strip()

    is_group = isinstance(event.source, SourceGroup)

    # คำสั่ง
    if text.lower() == "!help":
        reply = (
            "📌 คำสั่งบอท The_boy Security\n"
            "• ป้องกันลิงก์ / เว็บพนัน / ข้อความต้องห้าม\n"
            "• ป้องกันข้อความซ้ำรัว ๆ ภายในไม่กี่วินาที\n"
            "• เตือนผู้ที่ส่งสแปม ถ้าเตือนหลายครั้งจะบอกให้แอดมินจัดการ\n"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if text.lower() == "!status":
        reply = "บอทป้องกันกลุ่มทำงานปกติครับ ✅"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # ส่วนกันสแปม (เฉพาะในกลุ่ม)
    if is_group:
        spam_reasons = []

        if is_link(text):
            spam_reasons.append("ลิงก์")

        if is_bad_keyword(text):
            spam_reasons.append("คำต้องห้าม")

        if is_repeat_spam(user_id, text):
            spam_reasons.append("ข้อความซ้ำรัว ๆ")

        if spam_reasons:
            reason_str = " / ".join(spam_reasons)
            warn_times = add_warn(user_id)

            if warn_times >= MAX_WARN:
                msg = (
                    f"🚫 พบพฤติกรรมสแปม ({reason_str}) หลายครั้งแล้ว\n"
                    f"กรุณาแอดมินตรวจสอบและพิจารณาเตะออกด้วยครับ (เตือนแล้ว {warn_times} ครั้ง)"
                )
            else:
                msg = (
                    f"⚠️ กรุณาอย่าส่ง {reason_str} ในกลุ่มนี้นะครับ\n"
                    f"(เตือนครั้งที่ {warn_times}/{MAX_WARN})"
                )

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
            return

    # ถ้าไม่ใช่สแปม / ไม่ใช่คำสั่ง
    if not is_group:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="สวัสดีครับ ผมคือบอทป้องกันสแปมกลุ่ม\nเชิญผมเข้ากลุ่มแล้วพิมพ์ !help เพื่อดูรายละเอียดได้เลย 😄"
            ),
        )
    else:
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
