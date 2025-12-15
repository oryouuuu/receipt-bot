import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, ImageMessage, TextSendMessage
import google.generativeai as genai
from PIL import Image
import io

app = Flask(__name__)

# ==========================================
# 環境変数から鍵を読み込む（セキュリティ対策）
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})

# プロンプト
SYSTEM_PROMPT = """
あなたは完璧な経理AIです。画像を隅々まで読み、以下のルールでJSONを出力してください。

【厳守ルール】
1. **品目の完全網羅**: レシートに印字されている商品は、**1つ残らず全て** `items` 配列に書き出してください。「その他」や省略は許されません。
2. **合計金額**: 「合計」「小計」「対象計」などの文字を慎重に探し、**支払金額の総額**を抽出してください。ポイント残高やお釣りとお間違わないように。
3. **勘定科目の強制変換**: ビジネス経費として処理するため、以下のように変換してください。
   - スーパー/コンビニの食品 → "会議費" (単価が高い場合) または "消耗品費" (安い場合)
   - 日用品/文具 → "消耗品費"
   - 交通機関 → "旅費交通費"
   - 書籍 → "新聞図書費"
   - 不明/個人の買い物 → "事業主貸"
   ※「食料品費」という科目は使用禁止です。
4. **日付**: 年号（R7など）の場合は西暦（2025）に変換してください。

【出力JSONフォーマット】
{
  "date": "YYYY-MM-DD",
  "amount": 0,
  "vendor": "店名",
  "items": ["品目1", "品目2", "品目3", ...], 
  "category": "勘定科目",
  "invoice": "Txxxxxxxxxxxxx"
}
"""
@app.route("/callback", methods=['POST'])
def callback():
    # LINEからの署名確認（なりすまし防止）
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # 1. LINEサーバーから画像を取得
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    image_bytes = io.BytesIO(message_content.content)
    img = Image.open(image_bytes)

    # 2. Geminiで解析
    try:
        response = model.generate_content([SYSTEM_PROMPT, img])
        data = json.loads(response.text)
        
        # 3. 整形して返信（読みやすいテキスト形式に変換）
        reply_text = f"【解析完了】\n日付: {data.get('date')}\n金額: ¥{data.get('amount'):,}\n店名: {data.get('vendor')}\n科目: {data.get('category')}\n品目: {', '.join(data.get('items', []))}"
        
        # 将来的にはここでExcelやスプレッドシートに飛ばす処理を入れる
        
    except Exception as e:
        reply_text = f"エラーが発生しました: {e}"

    # 4. LINEに返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)