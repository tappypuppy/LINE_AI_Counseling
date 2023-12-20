from flask import Flask, request, abort
import openai
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

load_dotenv()

api_key = os.getenv("API_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

# SQLAlchemy configuration
DATABASE_URL = "sqlite:///messages.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()

# Define the Message model
class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255))
    timestamp = Column(DateTime)
    user_text = Column(String(255))
    reply_text = Column(String(255))

Base.metadata.create_all(bind=engine)

# Create a session to interact with the database
Session = sessionmaker(bind=engine)
session = Session()

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
                ・文字数は100字以内に収め、それを超えないこと
                ・優しい口調で答えること。
                ・「死」を連想させるような単語は使わないでください。
                ・親友や家族のように振る舞うこと。
                ・専門家や知人、家族に相談するように勧めることは禁止
                ・文章を改行するなどして、可読性を高めること
                    """


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    userId = event.source.user_id
    timestamp = datetime.utcfromtimestamp(event.timestamp / 1000.0)  # Convert timestamp to datetime
    prompt = event.message.text

    print(prompt)

    messages_for_gpt = []

    if user_id_exists(userId):
        message_list = get_messages_by_user_id(userId)

        for message_tuple in message_list:
            user_text = message_tuple[0]
            reply_text = message_tuple[1]

            user_text_gpt = {"role": "user", "content": user_text}
            reply_text_gpt = {"role": "system", "content": reply_text}

            messages_for_gpt.append(user_text_gpt)
            messages_for_gpt.append(reply_text_gpt)
        
        print("exist!")
    
    else:
        messages_for_gpt.append({"role": "system", "content": system_prompt})
        print("not exist")

    messages_for_gpt.append({"role": "user", "content": prompt})
    
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
                        model = "gpt-3.5-turbo-16k-0613",
                        messages = messages_for_gpt,
                        temperature=0,
                    )
    
    reply_message = response.choices[0].message.content
    print(reply_message)
    # reply_message = "テスト"

    # 受信したメッセージをデータベースに保存
    save_message(userId, timestamp, prompt, reply_message)


    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_message)]
            )
        )

def user_id_exists(user_id):
    # Check if user_id exists in the messages table
    existing_user = session.query(Message).filter_by(user_id=user_id).first()
    return existing_user is not None

def save_message(user_id, timestamp, user_text, reply_text):
    # Save the message to the database
    message = Message(
        user_id=user_id,
        timestamp=timestamp,
        user_text=user_text,
        reply_text=reply_text
    )
    session.add(message)
    session.commit()

def get_messages_by_user_id(user_id):
    # Calculate 1 day ago from now
    one_day_ago = datetime.utcnow() - timedelta(days=1)

    # SQLAlchemy query to get user_text and reply_text for a specific user_id within the last 1 day, ordered by timestamp
    messages = session.query(Message.user_text, Message.reply_text).filter(
        Message.user_id == user_id,
        Message.timestamp >= one_day_ago
    ).order_by(Message.timestamp).all()

    return messages

if __name__ == "__main__":
    app.run()