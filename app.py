from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage
import os

app = Flask(__name__)

# ดึงค่า TOKEN และ SECRET จาก Environment ของ Render
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.lower()

    # คำที่ถือว่าเป็นลิงก์/สแปม
    ban_words = ["http", "https", "www.", "bit.ly", "เชิญเข้ากลุ่ม", "เข้าเล่น"]
    if any(word in text for word in ban_words):
        line_bot_api.reply_message(
            event.reply_token,
            TextMessage(text="🚫 ห้ามส่งลิงก์หรือสแปมในกลุ่มนี้")
        )

if __name__ == "__main__":
    # ใช้พอร์ต 10000 (Render จะ override เองเวลา deploy จริง)
    app.run(host="0.0.0.0", port=10000)
