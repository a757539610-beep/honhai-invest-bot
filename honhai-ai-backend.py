import logging
import os
from datetime import datetime

import openai
import pinecone
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

# 載入環境變數
load_dotenv()

app = Flask(__name__)
CORS(app)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 設定 API 金鑰
openai.api_key = os.getenv("OPENAI_API_KEY", "your-openai-api-key")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "your-pinecone-api-key")
PINECONE_ENV = os.getenv("PINECONE_ENV", "us-west1-gcp")

# 初始化 Pinecone
try:
    pinecone.init(api_key=PINECONE_API_KEY, environment=PINECONE_ENV)
    index = pinecone.Index("honghai-investment")
    logger.info("Pinecone 初始化成功")
except Exception as exc:  # pylint: disable=broad-except
    logger.error("Pinecone 初始化失敗: %s", exc)
    index = None


class HonhaiAIAssistant:
    def __init__(self):
        self.name = "鴻海投資助手"
        self.version = "1.0.0"

    def get_embedding(self, text):
        """取得文本向量"""
        try:
            response = openai.Embedding.create(
                input=text,
                model="text-embedding-ada-002",
            )
            return response["data"][0]["embedding"]
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("向量化失敗: %s", exc)
            return None

    def query_similar_data(self, query_text, top_k=10):
        """查詢相關資料"""
        if not index:
            return []
        try:
            query_vec = self.get_embedding(query_text)
            if not query_vec:
                return []
            results = index.query(
                query_vec,
                top_k=top_k,
                include_metadata=True,
            )
            return results.get("matches", [])
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("查詢相關資料失敗: %s", exc)
            return []

    def generate_answer(self, query_text, top_k=10):
        """生成回答"""
        matches = self.query_similar_data(query_text, top_k=top_k)
        context_list = []
        for match in matches:
            meta = match.get("metadata", {})
            if "text" in meta:
                context_list.append(meta["text"])
        context_block = "\n".join(context_list[:top_k])

        prompt = f"""你是鴻海投資助手，專門回答鴻海科技集團相關的投資問題。

相關資料：
{context_block}

問題：{query_text}

請根據以上資料回答問題，如果資料不足請說明，並提供你對鴻海投資的基本建議。回答要專業、客觀，避免給出具體買賣建議。

回答："""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("生成回答失敗: %s", exc)
            return "抱歉，目前無法處理您的查詢。請稍後再試。"


default_assistant = HonhaiAIAssistant()


@app.route("/")
def home():
    return jsonify(
        {
            "message": "鴻海 AI 投資助手 API",
            "version": default_assistant.version,
            "status": "running",
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.route("/api/query", methods=["POST"])
def query():
    try:
        data = request.get_json()
        if not data or "question" not in data:
            return jsonify({"error": "請提供問題"}), 400
        question = data["question"].strip()
        if not question:
            return jsonify({"error": "問題不能為空"}), 400
        logger.info("收到查詢: %s", question)

        # 從向量資料庫檢索上下文
        answer = default_assistant.generate_answer(question, top_k=10)

        return jsonify(
            {
                "question": question,
                "answer": answer,
                "timestamp": datetime.now().isoformat(),
                "status": "success",
            }
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("查詢處理失敗: %s", exc)
        return jsonify({"error": "系統錯誤，請稍後再試"}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "pinecone_connected": index is not None,
        }
    )


@app.route("/api/info", methods=["GET"])
def info():
    return jsonify(
        {
            "name": default_assistant.name,
            "version": default_assistant.version,
            "description": "提供鴻海科技集團投資相關資訊查詢",
            "endpoints": [
                "/api/query - POST 查詢問題",
                "/api/health - GET 健康檢查",
                "/api/info - GET 系統資訊",
                "/api/examples - GET 範例問題",
            ],
        }
    )


@app.route("/api/examples", methods=["GET"])
def examples():
    demo = [
        {
            "question": "鴻海近期在AI領域的重要動向？",
            "answer": "根據公開資料，鴻海積極投入AI伺服器製造與銷售，並與 NVIDIA 合作打造超級電腦。",
        },
        {
            "question": "鴻海2024年財報有哪些亮點？",
            "answer": "2024年報顯示營收增長強勁，主因為 AI 業務部門需求提升。",
        },
    ]
    return jsonify({"examples": demo})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
