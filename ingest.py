import os
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# 这个脚本负责把 data.txt 转成向量索引（FAISS）
# 部署前先在本地运行一次，生成的 faiss_index 会被 Docker 镜像打包进去

# 1. 确认我们已经设置 OPENAI_API_KEY
if "OPENAI_API_KEY" not in os.environ:
    raise EnvironmentError("请先设置 OPENAI_API_KEY 环境变量")

# 2. 加载原始文档（可以换成 PDF/CSV 等其他 Loader，这里用纯文本）
loader = TextLoader("./data.txt")
documents = loader.load()

# 3. 将文档切成若干小块，方便后续做语义检索
text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
docs = text_splitter.split_documents(documents)

# 4. 用 OpenAI Embeddings 把每个切片编码成向量，存进 FAISS
embeddings = OpenAIEmbeddings()
db = FAISS.from_documents(docs, embeddings)

# 5. 把索引保存到本地目录（会生成 index.faiss / index.pkl）
db.save_local("faiss_index")
print("✅ FAISS index has been saved to 'faiss_index'")