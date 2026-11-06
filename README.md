# 设备故障诊断智能体 V1.0.0

后端 FastAPI（`/api/v1`）+ 前端 React/Vite + 本地 BGE-M3 检索 + 可选 DeepSeek，用于工业设备多分类故障诊断、批量评测与报告生成。

## 最终状态

| 项目 | 内容 |
|---|---|
| 最终判定 | [FINAL-ACCEPTANCE-V5.md](docs/FINAL-ACCEPTANCE-V5.md)：通过 |
| AC 计数 | 90/90（P0 78/78、P1 12/12） |
| 测试基线 | `storage/pytest-accept-v5.xml`：194 collected / 0 failed / 0 skipped |

## 启动与首次运行

1. **环境要求**：Python 3.12+；Node.js 版本未在仓库锁定（`frontend/package.json` 未声明 engines，依赖 Vite 8 / React 19）；`models/bge-m3` 为本地嵌入模型，不联网下载，目录缺失时自动回退 hash 检索。

2. **依赖安装**

   后端：

   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   前端：

   ```powershell
   cd frontend
   npm install
   ```

3. **配置**：将 `backend/.env.example` 复制到仓库根目录并命名为 `.env`；`EDG_LLM_MODE=fake` 可完整离线跑通；DeepSeek 模式需填入 `EDG_DEEPSEEK_API_KEY`，不得提交真实密钥。

4. **初始化数据**：首次启动自动执行数据库迁移、写入种子知识库 `kb_v1`。

5. **启动**

   一键启动（后端 8000 + 前端 5173）：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start.ps1
   ```

   脚本在未安装 `frontend/node_modules` 时跳过前端并提示先执行 `npm install`；前端 `/api` 代理指向后端。仅启动后端可加 `-SkipFrontend`。

   手动启动：

   ```powershell
   # 后端
   cd backend
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   ```powershell
   # 前端
   cd frontend
   npm run dev -- --port 5173
   ```

6. **验证**

   | 检查项 | 操作 | 期望结果 |
   |---|---|---|
   | 前端工作台 | 打开前端地址（http://127.0.0.1:5173） | 首次访问直接注册新账号，登录后进入工作台 |
   | 后端健康检查 | 打开健康检查接口（http://127.0.0.1:8000/api/v1/health） | 返回 200 |
   | BGE 缺失（可选） | 打开同一健康检查接口 | `status=degraded`，并返回 `embedding_reason` |

## 配置说明

`.env` 常用键：

| 键名 | 说明 |
|---|---|
| `EDG_LLM_MODE` | `fake`：不调用 DeepSeek，使用本地模拟 LLM，适合离线开发；`deepseek`：走真实 API，用于评测与生产诊断 |
| `EDG_DEEPSEEK_API_KEY` | DeepSeek 密钥，`deepseek` 模式必填，不得提交真实密钥 |
| `EDG_DEEPSEEK_BASE_URL` | DeepSeek API 地址 |
| `EDG_DEEPSEEK_MODEL` | 模型名 |
| `EDG_EMBEDDING_MODE` | 嵌入检索模式 |
| `EDG_SESSION_TTL_HOURS` | 会话有效期（小时） |
| `EDG_INTERRUPT_TTL_MINUTES` | 中断令牌有效期（分钟） |

## 目录结构

| 目录 | 内容 |
|---|---|
| `backend/` | FastAPI 服务、测试、pytest 配置 |
| `frontend/` | React/Vite 前端应用 |
| `data/` | 数据集，`ai4i2020.csv` 为评测原始数据 |
| `models/` | 本地模型目录，`bge-m3` 嵌入模型存放处 |
| `docs/` | 需求、架构、验收、交付文档 |
| `storage/` | SQLite 数据库、检查点、证据文件、junit XML |
| `screenshots/` | 浏览器链路截图证据 |
| `config/` | 敏感词等运行时配置 |

## 指标与披露义务

| 指标 | 结果 | 口径 |
|---|---|---|
| KPI-01 五分类 | 96.36%（106/110） | 主验收口径，依 C-011 |
| 六分类 | 88.33%（106/120） | 必须同时披露 |
| KPI-04 | 239/240 = 99.58% | 严格 DeepSeek 为 238/240 = 99.17% |
| KPI-05 | 0/20 | — |

C-011 仅覆盖 KPI-01 六分类门槛，C-012 仅覆盖 AC-CC-01，均不外扩。

## 常见问题

| 现象 | 处理 |
|---|---|
| 端口被占用 | `start.ps1` 直接提示，加 `-Port 8010 -FrontendPort 5174` 更换 |
| 首次启动报 `LLM_NOT_CONFIGURED` | DeepSeek 模式未填 Key 时诊断接口返回 503，填入密钥或切 `fake` 模式 |
| BGE 模型缺失 → 回退 hash 检索 | `/health` 返回 `status=degraded` 与 `embedding_reason` |
| 前端被踢回登录页 | 会话过期返回 401 `AUTH_SESSION_EXPIRED`，属正常行为 |
| 数据库被占用 | `storage/app.db` 为单实例 SQLite，避免多进程同时写入 |

## 复验命令

运行测试：

```powershell
cd backend
python -m pytest -q
```

期望 194 passed / 0 failed / 0 skipped。解析 junit 统计：

```powershell
python -c "
import xml.etree.ElementTree as E
root = E.parse('../storage/pytest-accept-v5.xml').getroot()
print(list(root)[0].attrib)
"
```

## 文档索引

| 文档 | 说明 |
|---|---|
| [FINAL-ACCEPTANCE-V5.md](docs/FINAL-ACCEPTANCE-V5.md) | 最终判定，唯一权威 |
| [DELIVERY-NOTES.md](docs/DELIVERY-NOTES.md) | 交付说明、KPI 口径、已知限制 OBS-01~12 |
| [AC-EVIDENCE-PACK.md](docs/AC-EVIDENCE-PACK.md) | 证据登记 |
| [E2E-UI-测试记录.md](docs/E2E-UI-测试记录.md) | 浏览器链路 |
| [PRD-设备故障诊断智能体-V1.0.0.md](docs/PRD-设备故障诊断智能体-V1.0.0.md) | 产品需求 |
| [ARCH-系统架构与API契约.md](docs/ARCH-系统架构与API契约.md) | 系统架构与 API 契约 |
| [UIUX-设备故障诊断智能体.md](docs/UIUX-设备故障诊断智能体.md) | UI/UX 设计 |
| [DB-数据库设计文档.md](docs/DB-数据库设计文档.md) | 数据库设计 |
| [EVAL-评测报告.md](docs/EVAL-评测报告.md) | 评测报告 |

## 已知限制

- 六分类 88.33% 未达 90%，按 C-011 披露不阻塞交付。
- AC-CC-01 的 Edge 单版本与 WebKit 替代 Safari，依 C-012 接受（仅此 AC）。
- KPI-05 评审人为内部代号，无外部实名存证，对外审计需补。
- 1 条 rule-engine 回落状态为 `succeeded`，未单独标 `degraded`。

## 使用范围

内部项目，未指定开源许可。
