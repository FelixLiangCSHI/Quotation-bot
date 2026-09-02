# 企业级部署 Gap Summary(Phase 0–4 → Production)

日期:2026-09-02(更新:第一节"现在能改"清单已全部实施完成,见各表状态列)
范围:基于 Phase 00–04(MVP 阶段)代码评审结果,梳理当前本地 / GitHub 环境与企业级服务器部署之间的差距。
分类原则:

- **现在能改**:仅依赖本地代码和 GitHub 仓库即可完成、可用现有测试验证的改动。
- **现在改不了**:必须等接入企业云端 / 内网资源(企业 AI 网关、鉴权体系、内部 API、监控平台、真实数据源)才能落地的改动,当前只能保留 mock / 配置占位。

---

## 一、现在能改(本地 / GitHub 环境即可完成)

### A. 业务正确性(优先级最高)

| # | Gap | 位置 | 改法 |
|---|-----|------|------|
| A1 | **决策树产品规则旁路**:仅通过决策树注册的产品 ID 被视为已知产品,但其规则未加载进 `rules_by_product_id`,region 校验被静默跳过 | `app/rule_engine.py`(`_load_decision_tree_product_ids` 相关) | 将 `rules/decision_tree_normalized_rules.json` 并入规则引擎索引,或不将无规则覆盖的 ID 标记为 valid;补回归测试 |
| A2 | 金额与折扣使用 `float` + `round()`,存在分位误差与阈值边界风险 | `app/quotation.py` | 改用 `Decimal` + 显式货币舍入 |

### B. 输入边界与 API 健壮性

| # | Gap | 位置 | 改法 |
|---|-----|------|------|
| B1 | `/recommend` 的 `message` 无长度上限(`/validation/check` 已有 4000 上限),超大输入可造成 CPU / LLM token DoS | `app/api.py` | Pydantic `Field(..., max_length=...)`,与 validation 端点保持一致 |
| B2 | `product_ids` 列表无数量 / 长度 / 格式限制,未知 ID 原样回显 | `app/api.py` | 限制条数 + ID 正则校验 |
| B3 | `LLM_API_BASE` 不校验 scheme/host,配错即把 API key(Authorization 头)发往任意端点(含明文 HTTP) | `app/llm.py` | 强制 HTTPS 校验、非法配置 fail-closed(白名单值可留占位,见 G4) |
| B4 | LLM 润色文本无后验校验,直接替换确定性回答,prompt injection 可篡改面向客户的措辞 | `app/api.py` / `app/llm.py` | 校验润色文本保留产品 ID / 价格 / 验证结论,否则回退模板文本;可用现有 mock LLM 测试验证 |

### C. 可运维性(代码层)

| # | Gap | 位置 | 改法 |
|---|-----|------|------|
| C1 | `/health` 不校验数据资产;snapshot 懒加载,坏数据也能通过健康检查 | `app/api.py`、`app/data_loader.py` | 启动时 eager load,增加 readiness 端点校验 snapshot 与 merged_rules 完整性 |
| C2 | 除 `app/llm.py` 外全项目无结构化日志 | `app/*.py` | 引入标准 `logging` 配置(JSON 格式化可先落地,输出目标见 E4) |
| C3 | `/data/sources` 每次调用重读 `merged_rules.json` | `app/api.py` | 加 mtime 感知缓存 |
| C4 | 响应暴露内部溯源元数据(workbook sheet/cell、原始规则文本) | `app/api.py`、`app/recommender.py` | 增加开关剥离 provenance,默认对外隐藏 |
| C5 | 缺少容器化 / 部署工件 | 仓库根目录 | 编写 Dockerfile、uvicorn 多 worker 启动配置、CI workflow(GitHub Actions 跑测试) |

### D. 前端与脚本

| # | Gap | 位置 | 改法 |
|---|-----|------|------|
| D1 | 前端硬编码 `http://127.0.0.1:8000`,服务器部署即失效 | `frontend/app.js` | 改为同源相对路径,或部署时注入的配置变量 |
| D2 | `sessionStorage` 无上限写入,长会话超配额;`response.json()` 先于 `response.ok` 判断 | `frontend/app.js` | 截断历史 + 捕获 quota 异常;先判断状态码再解析 |
| D3 | PPT 脚本将内部架构 Mermaid 图发送至外部 `mermaid.ink` 且无超时,内部信息外泄 | `scripts/create_roadmap_ppt_from_markdown.py` | 本地渲染或显式 opt-in + 超时 |

### E. 测试补强

| # | Gap | 改法 |
|---|-----|------|
| E1 | 缺少"LLM 篡改关键事实应被拒绝"的测试 | 用现有 mock LLM 添加 prompt-injection / 事实保持测试 |
| E2 | 缺少输入边界(超长 message、超大 product_ids 列表)的 API 测试 | 配合 B1/B2 一起补 |


### 实施状态(2026-09-02)

第一节所有条目已实施完成:

- ✅ A1 决策树区域规则旁路已修复(`rule_engine.py` 现在索引并校验 `region_allow`/`region_block` 决策树规则,附回归测试)
- ✅ A2 金额计算改用 `Decimal` 半进位舍入(`_round_money`、`calculate_discount_rate`)
- ✅ B1/B2 `/recommend` message 上限 4000,`product_ids` 上限 100 条 / 每条 40 字符
- ✅ B3 `LLM_API_BASE` 强制 HTTPS,非法配置 fail-closed 禁用推理层
- ✅ B4 LLM 润色文本后验(产品 ID / 价格 / 验证结论缺失即回退确定性文本)
- ✅ C1/C2 启动 eager load + `/health` 就绪校验 + 结构化日志
- ✅ C3 `merged_rules.json` mtime 感知缓存
- ✅ C4 `QUOTATION_INCLUDE_SOURCES=0` 可剥离 source 溯源元数据(Beta 默认保留)
- ✅ C5 Dockerfile + .dockerignore(非 root 用户、healthcheck)
- ✅ D1 前端 API base 可配置(`window.QUOTATION_API_BASE` → 同源 → localhost 回退),FastAPI 挂载 `/ui` 静态前端
- ✅ D2 sessionStorage 截断(100 条消息 / 50 条历史)+ 配额异常处理;fetch 先判断状态再解析
- ✅ D3 mermaid.ink 外发需 `ALLOW_EXTERNAL_MERMAID_RENDER=1` 显式 opt-in,加 30s 超时
- ✅ E1/E2 新增 prompt-injection 拒绝测试、输入边界测试、决策树区域校验测试

---

## 二、现在改不了(需接入企业云端后落地)

这些项在本地只能用 mock、环境变量占位或文档记录,真正启用依赖企业资源。

### F. 认证与网络安全(依赖企业鉴权体系)

| # | Gap | 当前状态(mock/占位) | 需要的企业资源 |
|---|-----|---------------------|----------------|
| F1 | **API 无任何认证/授权**——`/recommend`、`/validation/check`、`/data/sources`、`/llm/status` 完全开放 | 无鉴权,仅 CORS 限制 localhost | 企业 SSO / Entra ID / API 网关(JWT 校验);拿到 IdP 配置后接 `Depends` 鉴权中间件。*本地可预留的部分:先写一个可插拔的 auth dependency 接口 + 假 token 测试* |
| F2 | 无限流 | 无 | 通常由企业 API 网关 / 反向代理层提供;本地无真实网关无法验证 |
| F3 | HTTPS / TLS 终结 | 本地 HTTP | 企业负载均衡 / 证书体系 |
| F4 | CORS 白名单为 localhost 端口 | `app/api.py` 硬编码 localhost | 需要企业前端正式域名确定后改为配置化(可先做成环境变量,但真实值需云端确定) |

### G. LLM 真实接入(依赖企业 AI 平台,Phase 0/2 遗留)

| # | Gap | 当前状态 | 需要的企业资源 |
|---|-----|---------|----------------|
| G1 | Azure OpenAI / DeepSeek-v4-pro 真实端点、key、deployment 名 | `.env.example` 占位;`LLM_API_BASE`/`LLM_API_KEY` 未设置时 reasoning 层禁用,回退确定性回答 | IT / AI 平台批复(`docs/phase0_azure_openai_access_request.md` 流程) |
| G2 | Entra ID / Managed Identity 免 key 认证 | 仅 API key 路径实现 | 企业订阅内的托管身份;`DefaultAzureCredential` 需在云端环境验证 |
| G3 | 真实 LLM 输出质量 / prompt 调优、token 成本评估 | 只能用 mock 响应测试解析逻辑 | 真实端点与配额 |
| G4 | LLM 域名白名单(B3 的白名单值) | 只能校验 HTTPS 格式 | 企业网关正式域名 |

### H. 数据与规则(依赖内部真实数据源,Phase 4 遗留)

| # | Gap | 当前状态 | 需要的企业资源 |
|---|-----|---------|----------------|
| H1 | `quotation_snapshot.json` 为静态快照,无刷新机制 | 手工提交至仓库 | 内部定价 / 产品主数据 API 或数据库连接;届时实现定时同步或读实时 API |
| H2 | 规则 SME 评审闭环 | `rules/*.csv` 模板 + 手工 merge 脚本 | 企业协作平台(SharePoint/内部审批流)对接 |
| H3 | 持久化会话记忆 / 数据库 | 会话状态仅存浏览器 `sessionStorage` | 企业数据库 / Redis 审批与实例 |
| H4 | 真实数据的数据使用合规确认 | `docs/phase0_data_usage_approval.md` 流程文档 | 法务 / 数据 owner 批复 |

### I. 运维与监控(依赖企业基础设施)

| # | Gap | 当前状态 | 需要的企业资源 |
|---|-----|---------|----------------|
| I1 | 集中日志 / APM / 告警 | 本地 stdout | 企业监控平台(如 Azure Monitor / ELK);C2 完成后仅需接输出端 |
| I2 | 密钥管理 | `.env` 文件 | 企业 Key Vault / Secret Manager |
| I3 | 正式运行环境(VM/K8s/内网域名) | 本地 uvicorn | 服务器资源审批(`docs/phase0_run_location_decision.md`) |
| I4 | 企业级前端集成(Teams / 内部门户) | 静态 `frontend/` 演示页 | 企业前端平台与发布通道 |

---

## 三、建议执行顺序

1. **立即(本地可完成)**:A1 规则旁路修复 → B1/B2 输入边界 → B4 LLM 输出后验 → C1 健康检查 → E 测试补强。
2. **部署准备(本地可完成)**:C2 日志、C5 Dockerfile + CI、D1 前端 API base 配置化、F1 的可插拔 auth 接口预留。
3. **接入企业云端后**:F1–F4 鉴权/网关/TLS → G1–G4 真实 LLM → I1–I3 监控与密钥 → H1–H4 真实数据源与持久化。

> 结论:Phase 0–4 的 MVP 架构(规则引擎为唯一验证权威、LLM 仅润色、单一数据源)无需重构。"现在能改"的清单全部是代码级工程收敛,可在当前仓库直接完成并用现有 169 个测试基线验证;"现在改不了"的清单本质上都是**外部资源依赖**,建议在代码中统一以环境变量 + fail-closed 默认值预留接口,连上企业云端后仅做配置切换。
