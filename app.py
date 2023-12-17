from flask import Flask, request, abort
import openai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("API_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")


# あなたは臨床心理士


from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

app = Flask(__name__)

configuration = Configuration(access_token=ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)


@app.route("/")
def test():
    return "OK"


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'




system_prompt = """
                #命令書
                あなたはプロの臨床心理士です。
                あなたは、ユーザーにとって唯一の相談人です。
                自殺予防のカウンセラーとして、相談に乗ってください。
                以下の制約条件をもとに、文章を作成してください。

                #制約条件
                ・文字数は200字以内
                ・優しい口調で答えること。
                ・「死」を連想させるような単語は使わないでください。
                ・親友や家族のように振る舞うこと。
                ・専門家や知人、家族に相談するように勧めることは禁止
                    """

db_temp = {}


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    userId = event.source.user_id
    if userId not in db_temp:
        db_temp[userId] = [{"role": "system", "content": system_prompt}]


    prompt = event.message.text
    prompt_db = {"role": "user", "content": prompt}
    
    db_temp[userId].append(prompt_db)
    # db_temp = [{"role": "system", "content": system_prompt},
    #            {"role": "user", "content": prompt}]
    
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
                        model = "gpt-3.5-turbo-16k-0613",
                        messages = db_temp[userId],
                        temperature=0,
                        max_tokens=400
                    )
    
    reply_message = response.choices[0].message.content
    reply_message_db = {"role": "system", "content": reply_message}

    db_temp[userId].append(reply_message_db)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_message)]
            )
        )

if __name__ == "__main__":
    app.run()