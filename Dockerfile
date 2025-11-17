# 1. 使用官方 Python 基础镜像
#    尽量选择 slim 版本，镜像体积更小，部署到 App Runner 更快
FROM python:3.11-slim

# 2. 设置工作目录
#    App Runner 在容器里会默认执行 CMD，所以我们把代码放到 /app 目录
WORKDIR /app

# 3. 安装依赖
#    先复制 requirements.txt，这样如果代码变动但依赖不变，Docker 会利用缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 复制所有代码和数据
#    包括 FastAPI 应用、向量索引（faiss_index）以及 Terraform 等文件
COPY . .

# 4.5 构建 FAISS 索引 (如果还不存在)
#    生产环境中我们通常在 CI 或本地先运行 ingest.py，这里保留命令作为参考
# RUN python ingest.py

# 5. 暴露端口
#    App Runner 默认监听 8080，所以我们在容器内也保持一致
EXPOSE 8080

# 6. 启动命令
# 用 uvicorn 运行 FastAPI 应用
#    --host 0.0.0.0 让容器外部可以访问，端口和 EXPOSE 对齐
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]