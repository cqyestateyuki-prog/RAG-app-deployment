import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader

# 1. Quick sanity check: make sure我们有 OpenAI 的 Key
# 在本地需要手动 export，部署到 App Runner 时会通过 Secrets Manager 注入
if "OPENAI_API_KEY" not in os.environ:
    print("⚠️  WARNING: OPENAI_API_KEY environment variable not set. Chat functionality will fail.")
else:
    print("✅ OPENAI_API_KEY is set")

# --- Lazy loading: 只在第一次调用 /chat 时才真正加载向量库和模型 ---
rag_chain = None

def ensure_faiss_index():
    """如果 faiss_index 不存在，自动从 data.txt 生成"""
    if not os.path.exists("faiss_index"):
        print("⚠️  FAISS index not found, generating from data.txt...")
        if not os.path.exists("data.txt"):
            raise FileNotFoundError("data.txt not found. Cannot generate index.")
        
        # 加载并处理文档
        loader = TextLoader("./data.txt")
        documents = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
        docs = text_splitter.split_documents(documents)
        
        # 创建向量并存储
        embeddings = OpenAIEmbeddings()
        db = FAISS.from_documents(docs, embeddings)
        db.save_local("faiss_index")
        print("✅ FAISS index generated successfully!")

def get_rag_chain():
    global rag_chain
    if rag_chain is None:
        print("Loading RAG model and vector store...")
        
        # 确保索引存在（如果不存在会自动生成）
        ensure_faiss_index()

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

@app.get("/", response_class=HTMLResponse)
def read_root():
    # 返回一个简单的 HTML 前端页面，让用户可以在浏览器中输入问题
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>RAG 问答应用</title>
        <meta charset="utf-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                text-align: center;
            }
            .input-group {
                margin: 20px 0;
            }
            input[type="text"] {
                width: 100%;
                padding: 12px;
                font-size: 16px;
                border: 2px solid #ddd;
                border-radius: 5px;
                box-sizing: border-box;
            }
            button {
                width: 100%;
                padding: 12px;
                font-size: 16px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                margin-top: 10px;
            }
            button:hover {
                background-color: #45a049;
            }
            button:disabled {
                background-color: #cccccc;
                cursor: not-allowed;
            }
            #answer {
                margin-top: 20px;
                padding: 15px;
                background-color: #f9f9f9;
                border-radius: 5px;
                min-height: 50px;
                white-space: pre-wrap;
            }
            .loading {
                color: #666;
                font-style: italic;
            }
            .error {
                color: #d32f2f;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 RAG 问答应用</h1>
            <p style="text-align: center; color: #666;">基于 LangChain 的检索增强生成问答系统</p>
            
            <div class="input-group">
                <input type="text" id="question" placeholder="请输入您的问题，例如：Who is the instructor? 或 When does the course run?" />
            </div>
            
            <button onclick="askQuestion()" id="submitBtn">提问</button>
            
            <div id="answer"></div>
        </div>
        
        <script>
            function askQuestion() {
                const question = document.getElementById('question').value.trim();
                const answerDiv = document.getElementById('answer');
                const submitBtn = document.getElementById('submitBtn');
                
                if (!question) {
                    answerDiv.innerHTML = '<span class="error">请输入问题</span>';
                    return;
                }
                
                // 禁用按钮，显示加载状态
                submitBtn.disabled = true;
                answerDiv.innerHTML = '<span class="loading">正在思考中...</span>';
                
                // 发送 POST 请求到 /chat 接口
                fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ question: question })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        answerDiv.innerHTML = '<span class="error">错误: ' + data.error + '</span>';
                    } else {
                        answerDiv.innerHTML = '<strong>回答：</strong><br>' + data.answer;
                    }
                    submitBtn.disabled = false;
                })
                .catch(error => {
                    answerDiv.innerHTML = '<span class="error">请求失败: ' + error.message + '</span>';
                    submitBtn.disabled = false;
                });
            }
            
            // 支持按 Enter 键提交
            document.getElementById('question').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    askQuestion();
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content

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
