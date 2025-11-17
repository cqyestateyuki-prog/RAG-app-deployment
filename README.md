# RAG App — LangChain + FastAPI + AWS App Runner CI/CD

本仓库包含一个 LangChain RAG 问答 API（FastAPI + FAISS 本地向量库）以及一条完整的 GitHub Actions → ECR → App Runner 自动化发布流水线，无需长期 AWS Access Key（通过 GitHub OIDC 假设角色）。

## 1. 本地开发
1. 准备数据源，放在 `data.txt`，或自行替换。
2. 设置 `OPENAI_API_KEY`，运行 `python ingest.py` 生成 `faiss_index/`。
3. `uvicorn app:app --reload` 即可在本地验证 `/` 与 `/chat`。

## 2. 使用 Terraform 创建云端资源
Terraform 模板位于 `main.tf`，会创建：GitHub OIDC Provider、ECR、Secrets Manager、App Runner 所需角色等。

```bash
export TF_VAR_github_org_or_user="cqyestateyuki-prog"
export TF_VAR_github_repo_name="RAG-app-deployment"
export TF_VAR_openai_api_key="<OPENAI_API_KEY>"

# 如果希望 Terraform 同时创建 App Runner，可将变量置为 true
export TF_VAR_manage_apprunner_via_terraform=false

terraform init
terraform apply -auto-approve
```

> `terraform apply` 结束后，记录输出：`github_actions_role_arn`、`ecr_repository_name`、`apprunner_service_arn`（若 `manage_apprunner_via_terraform=true`）、`apprunner_url`。

## 3. GitHub Secrets（Settings → Secrets and variables → Actions）

| Name | Value 来源 |
| ---- | ---------- |
| `AWS_REGION` | 例如 `us-east-1`（保持与 Terraform provider 相同） |
| `ECR_REPOSITORY` | Terraform 输出 `ecr_repository_name` |
| `APP_RUNNER_ARN` | Terraform 输出 `apprunner_service_arn`（若 Terraform 未创建服务，可先手动创建后更新此值） |
| `AWS_IAM_ROLE_TO_ASSUME` | Terraform 输出 `github_actions_role_arn` |

## 4. GitHub Actions 工作流（`.github/workflows/deploy.yml`）

流水线在 `push` 到 `main` 时触发，关键步骤：

1. `aws-actions/configure-aws-credentials@v4`：通过 OIDC 无密钥登录 AWS 并假设 `AWS_IAM_ROLE_TO_ASSUME`。
2. `aws-actions/amazon-ecr-login@v2`：登录 ECR。
3. Docker 构建并推送镜像，Tag 使用 `${{ github.sha }}`，确保 `linux/amd64` 以兼容 App Runner。
4. 使用 `aws apprunner describe-service` 动态获取 `access-role-arn / instance-role-arn / ServiceName`，避免硬编码。
5. `awslabs/amazon-app-runner-deploy@main`：将最新镜像部署到现有服务，等待服务稳定。

## 5. Cloudflare 自定义域

1. 在 Cloudflare 控制台添加一个新的站点 / 选择已有域名。
2. 创建 `CNAME` 记录，例如 `rag.yourdomain.com`，指向 App Runner 默认域名（`xxx.awsapprunner.com`）。
3. 启用 Cloudflare 代理（可选）并申请自动 SSL。
4. 等待 DNS 生效后，访问 `https://rag.yourdomain.com` 验证健康检查。

## 6. 提交作业所需信息

- GitHub 仓库（Public）链接，包含：
  - `app.py`（FastAPI + LangChain RAG）
  - `Dockerfile`
  - `.github/workflows/deploy.yml`
- Cloudflare 外网访问 URL（例：`https://rag.yourdomain.com`）

## 7. 额外建议

- 若需 Terraform 全量管理 App Runner，请在 `terraform.tfvars` 中设置 `manage_apprunner_via_terraform=true` 并重新 `apply`。
- GitHub Runner 缺省已安装 `jq` 与 AWS CLI v2；若自建 Runner，请确保同等环境。
- App Runner 运行时会自动通过实例角色读取 Secrets Manager 中的 `OPENAI_API_KEY`，无需在镜像内硬编码。
