import os
from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# 1. Quick sanity check: make sure我们有 OpenAI 的 Key
# 在本地需要手动 export，部署到 App Runner 时会通过 Secrets Manager 注入
if "OPENAI_API_KEY" not in os.environ:
    print("⚠️  WARNING: OPENAI_API_KEY environment variable not set. Chat functionality will fail.")
else:
    print("✅ OPENAI_API_KEY is set")

# --- Lazy loading: 只在第一次调用 /chat 时才真正加载向量库和模型 ---
rag_chain = None

def get_rag_chain():
    global rag_chain
    if rag_chain is None:
        print("Loading RAG model and vector store...")

        # 1) 加载本地 FAISS 索引（ingest.py 预处理生成），并建立检索器
        embeddings = OpenAIEmbeddings()
        vectorstore = FAISS.load_local(
            "faiss_index", 
            embeddings, 
            allow_dangerous_deserialization=True 
        )
        retriever = vectorstore.as_retriever()
        
        # 2) 定义提示词模板：把检索的上下文和用户问题拼成一条完整的 Prompt
        template = """Use the following pieces of context to answer the question.
If you don't know the answer, just say that you don't know, don't try to make up an answer.

Context: {context}

Question: {question}

Helpful Answer: """
        
        prompt = ChatPromptTemplate.from_template(template)
        
        # 3) 选择要调用的 LLM（OpenAI gpt-3.5-turbo，temperature=0 让回答更稳定）
        llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)
        
        # 4) LCEL 管道：retriever -> prompt -> LLM -> 输出解析
        def format_docs(docs):
            return "\n\n".join([d.page_content for d in docs])
        
        rag_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        print("✅ RAG Application is ready.")
    return rag_chain

app = FastAPI()

class Query(BaseModel):
    question: str

@app.get("/")
def read_root():
    # 健康检查接口：部署后通过 curl / Cloudflare 验证服务是否在线
    return {"message": "BEE EDU RAG Application is live!", "version": "v1"}

@app.post("/chat")
def chat(query: Query):
    try:
        # Lazy load RAG chain on first use
        chain = get_rag_chain()
        answer = chain.invoke(query.question)
        return {"answer": f"Helpful Answer: V2 {answer}"}
    except Exception as e:
        # Return error message
        return {"error": str(e)}, 500
