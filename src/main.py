import json
import logging
import os

from langchain.chains import ConversationChain, RetrievalQA
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_models import BedrockChat
from langchain_community.retrievers import AmazonKnowledgeBasesRetriever
from langchain_openai import ChatOpenAI
from slack_bolt import App, Ack, Say
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

LOG_LEVEL = os.environ.get("LOG_LEVEL")

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_BOT_MEMBER_ID = os.environ.get("SLACK_BOT_MEMBER_ID")

CHATGPT_SETTINGS = os.environ.get("CHATGPT_SETTINGS")
BEDROCK_SETTINGS = os.environ.get("BEDROCK_SETTINGS")

logging.getLogger(__name__).setLevel(LOG_LEVEL)

app = App(
    logger=logging.getLogger(__name__),
    signing_secret=SLACK_SIGNING_SECRET,
    token=SLACK_BOT_TOKEN,
    process_before_response=True
)


def send_ack(ack: Ack):
    ack()


def get_thread_ts(channel_id: str, event_ts: str) -> str:
    res = app.client.conversations_replies(
        channel=channel_id,
        ts=event_ts,
        limit=1,
    )
    messages = res["messages"]
    if "ok" in res and "thread_ts" in messages[0]:
        return messages[0]["thread_ts"]
    else:
        return event_ts


def get_thread_messages(channel_id, thread_ts: str, limit: int) -> list[dict]:
    res = app.client.conversations_replies(
        channel=channel_id,
        ts=thread_ts,
        limit=limit,
    )
    return res["messages"]


def handle_app_mentions(event, say: Say, logger: logging.Logger):
    logger.debug("event: %s", json.dumps(event, ensure_ascii=False))
    channel_id = event["channel"]
    event_ts = event["event_ts"]

    # get messages
    thread_messages = get_thread_messages(channel_id, get_thread_ts(channel_id, event_ts), 30)
    logger.debug(json.dumps(thread_messages, ensure_ascii=False))

    # ask
    memory = ConversationBufferMemory(return_messages=True)
    inputs = outputs = ""
    for m in thread_messages:
        text = m["text"].replace(f"<@{SLACK_BOT_MEMBER_ID}>", "").strip()
        if m["user"] == SLACK_BOT_MEMBER_ID:
            outputs += text
        else:
            if len(outputs) > 0:
                memory.save_context({"input": inputs}, {"output": outputs})
                inputs = outputs = ""
            inputs += text
    retriever = None
    if CHATGPT_SETTINGS:
        logging.debug(f"Using ChatGPT: {CHATGPT_SETTINGS}")
        settings = json.loads(CHATGPT_SETTINGS)
        llm = ChatOpenAI(
            api_key=settings["apiKey"],
            model=settings["model"],
        )
    elif BEDROCK_SETTINGS:
        logging.debug(f"Using Bedrock: {BEDROCK_SETTINGS}")
        settings = json.loads(BEDROCK_SETTINGS)
        llm = BedrockChat(model_id=settings["model"])
        if "kb" in settings:
            retriever = AmazonKnowledgeBasesRetriever(
                knowledge_base_id=settings["kb"],
                retrieval_config={
                    "vectorSearchConfiguration": {
                        "numberOfResults": 4
                    }
                }
            )
    else:
        raise ValueError("No model settings")
    if retriever:
        chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            verbose=True,
            memory=memory,
        )
        res = chain.invoke({"query": inputs})
        result = res["result"]
    else:
        conversation = ConversationChain(
            llm=llm,
            verbose=True,
            memory=memory,
        )
        result = conversation.predict(input=inputs)

    # reply
    say(channel=channel_id, thread_ts=event_ts, text=result)


app.event("app_mention")(
    ack=send_ack,
    lazy=[handle_app_mentions],
)


def lambda_handler(event, context):
    slack_handler = SlackRequestHandler(app=app)
    if "x-slack-retry-num" in event["headers"]:
        print("Retry request ignored")
        return {"statusCode": 200, "body": "Retry request ignored"}
    return slack_handler.handle(event, context)
