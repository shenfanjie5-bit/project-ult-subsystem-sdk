# subsystem-sdk 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.1
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `subsystem-sdk` 子项目从“几个校验器和提交脚本”的零散理解收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目中唯一负责子系统公共 base class、Ex-0~Ex-3 本地校验、统一 submit client、heartbeat client、注册机制和测试 fixtures 的公共框架模块。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 补充子系统对 SDK 的只读依赖约束和稳定 API 版本策略 | Codex |

---

## 1. 一句话定义

`subsystem-sdk` 是主项目中**唯一负责把“子系统如何按 Ex-0~Ex-3 合同说话、如何向 Layer B 提交候选对象、如何上报心跳、如何在 Lite/Full 两种提交后端之间平滑切换”封装成统一开发框架**的公共模块，它以“Ex-0 只能是 Metadata / 心跳”“producer payload 只包含生产者拥有字段”“transport 切换不要求子系统改业务代码”为不可协商约束。

它不是 Layer B 运行时本体，也不是 contracts 的第二套 schema。  
它不拥有 PG 队列表、Kafka topic、去重/冲突检测规则，也不实现新闻/公告/研报等具体子系统业务。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么写一个 Python client”，而是：

1. **子系统出口统一问题**：如果每个子系统各自理解 Ex-0~Ex-3、各自封装提交方式，合同语义会很快漂移，`subsystem-*` 就无法并行自动化开发。
2. **Lite / Full 切换成本问题**：Lite 模式经 PG 队列提交，Full 模式切 Kafka-compatible broker；如果 transport 细节泄露到子系统代码，P11 一启动所有子系统都要重写。
3. **公共骨架复用问题**：参考子系统、fixtures、contract examples、注册与心跳机制如果不集中沉淀，就无法形成真正可复制的子系统模板。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| Ex-0 | 子系统 Metadata / 心跳 payload | 不是原始 fact 引用 |
| Ex-1 | Candidate Facts payload | 子系统 -> Layer B |
| Ex-2 | Candidate Signals payload | 子系统 -> Layer B |
| Ex-3 | Candidate Graph Deltas payload | 子系统 -> Layer B |
| Producer-owned Fields | 由子系统自己负责填写的字段 | 不含 Layer B 摄取元数据 |
| Ingest Metadata | Layer B 在摄取时补写的元数据 | 如 `submitted_at`、`ingest_seq`、`layer_b_receipt_id` |
| Submit Client | 统一候选提交接口 | 屏蔽 Lite / Full transport 差异 |
| Heartbeat Client | Ex-0 心跳发送接口 | 负责健康状态上报 |
| Submit Receipt | 一次提交返回的标准执据 | transport 无关 |
| Backend Adapter | submit client 背后的具体传输实现 | Lite -> PG，Full -> Kafka-compatible |
| Subsystem Base Class | 子系统公共运行壳 | 管理 config、submit、heartbeat、fixtures |
| Contract Example | 一组合法/非法 Ex payload 样例 | 用于测试和自动化生成 |
| Registration Spec | 子系统注册元数据 | 描述 subsystem_id、version、capabilities |

**规则**：
- `Ex-0 = Metadata / 心跳` 语义固定，不得改写
- `submitted_at` / `ingest_seq` / `layer_b_receipt_id` 不属于 producer payload
- `subsystem-sdk` 不定义第二套 Ex schema，只消费 `contracts`
- `submit(payload) -> Receipt` 必须对 Lite / Full 保持同一接口
- 纯结构化数据源走 `DataSourceAdapter + dbt`，不走 `subsystem-sdk`

---

## 4. 目标与非目标

### 4.1 项目目标

1. **提供子系统公共 base class**：给 `subsystem-*` 提供一致的启动、配置、提交流程壳。
2. **提供 Ex-0~Ex-3 本地校验器**：在子系统侧尽早发现 schema 错误和明显字段缺失。
3. **提供统一 submit client**：用一个接口覆盖 Lite 的 PG 提交和 Full 的 Kafka-compatible 提交。
4. **提供 heartbeat client**：统一发送 Ex-0 心跳与健康状态。
5. **提供注册机制**：统一管理 `subsystem_id`、version、capabilities、支持的 Ex 类型等元数据。
6. **提供 fixtures 与 contract examples**：为参考子系统、集成测试和自动化脚手架提供标准样例。
7. **提供预检辅助**：对实体锚点等做可选 preflight 检查，帮助子系统更早暴露问题，但不替代 Layer B 权威校验。

### 4.2 非目标

- **不拥有 Ex-0~Ex-3 schema**：正式 payload schema 归 `contracts`，因为 schema 不能在 SDK 中复制第二份。
- **不拥有 Layer B 摄取基础设施**：PG 队列表、`cycle_candidate_selection`、`cycle_metadata`、Kafka topic 等归 `data-platform` / `stream-layer`。
- **不实现具体子系统业务逻辑**：新闻、公告、研报、社交等领域逻辑归各自 `subsystem-*`。
- **不做去重/冲突检测的权威判定**：权威校验归 Layer B，SDK 只做 fail-fast 本地校验。
- **不定义心跳状态表存储**：心跳策略和字段在本模块定义，但状态表与接收落地归 `data-platform`。
- **不服务纯结构化数据源**：Tushare/Wind 这类 adapter 路线不经过子系统框架。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
contracts + data-platform + entity-registry + stream-layer(full mode)
  -> subsystem-sdk
      ├── subsystem base class
      ├── Ex validators
      ├── submit client
      ├── heartbeat client
      ├── registration
      ├── fixtures / contract examples
      └── testing helpers
  -> subsystem-*
      ├── subsystem-announcement
      ├── subsystem-news
      └── future subsystem-*
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| `contracts` | Ex-0~Ex-3 schema、错误码、版本信息 | SDK 不能自定义第二套 payload 结构 |
| `data-platform` | Lite 模式候选提交入口、heartbeat 接收入口、Layer B receipt 语义 | PG 队列与状态表不归本模块 |
| `entity-registry` | canonical_entity_id 可解析性 preflight 能力 | 可选辅助，不替代权威校验 |
| `stream-layer` | Full 模式 submit backend 适配点 | P11 启动后切 Kafka-compatible |
| `assembly` | 环境配置、backend 选择、secret 注入 | 部署与注入不归本模块定义 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| `subsystem-*` | base class、submit / heartbeat client、validator、fixtures | Python import（只读消费 SDK 公开接口） |
| `data-platform` / Layer B | 合法 Ex payload、heartbeat payload、统一 receipt 语义 | API / queue / backend adapter |
| `assembly` | 参考子系统模板、配置约定 | 配置 + scaffolding |
| `stream-layer` | Full 模式 backend 接口契约 | Python protocol |

### 5.4 核心边界

- **`subsystem-sdk` 只拥有客户端语义，不拥有 Layer B 存储与权威校验**
- **Ex schema 只来自 `contracts`，SDK 不复制 schema 定义**
- **`submitted_at` / `ingest_seq` / `layer_b_receipt_id` 是 ingest metadata，不进入 producer payload**
- **`submit(payload) -> Receipt` 是稳定接口，Lite / Full 切换不能要求子系统改业务代码**
- **心跳策略和字段定义归 `subsystem-sdk`，心跳落地表归 `data-platform`**
- **各 `subsystem-*` 对 SDK 的依赖是只读的，不允许反向调用内部检查接口或修改 SDK 全局状态**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Contract-first

SDK 的第一职责不是“帮你发消息”，而是确保子系统在真正提交前就按正式合同说话。  
如果合同解释权散落在每个子系统里，后面的 Layer B 和主系统就会持续被迫兼容坏历史。

#### 原则 2：Producer Owns Only Producer Fields

子系统只对自己能负责的字段负责。  
一切由 Layer B 或后端生成的摄取元数据，都不应反向污染 producer payload。

#### 原则 3：Same Code Path, Different Backend

Lite 和 Full 的差异应停在 backend adapter 层。  
子系统代码看到的应该始终是同一个 `submit()` / `heartbeat()` 接口。

#### 原则 4：Fail Fast, Fail Locally

明显的合同错误、空字段、错误枚举、明显不可解析实体引用，应该在子系统本地尽早暴露。  
这样既减少 Layer B 噪声，也让自动化代理更容易定位问题。

#### 原则 5：Reference Subsystem Ready

SDK 不只是给人手写代码用，也必须能支撑“自动化批量生成子系统项目”。  
因此 fixtures、contract examples、参考骨架和测试辅助必须作为一等能力存在。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 把 `Ex-0` 改写成别的业务含义 | 心跳机制和合同版本全会漂移 |
| 把 `submitted_at` / `ingest_seq` 写进 Ex payload | 把 Lite 细节污染成长期接口 |
| 子系统直接知道 PG 队列表或 Kafka topic 名称 | 一旦切换 backend 所有子系统都要改 |
| 在 SDK 里复制 Ex schema | 会形成 contracts 之外的第二真相源 |
| 在 base class 里塞新闻/公告/研报业务逻辑 | 公共壳失去可复用性 |
| 用 SDK 替代 Layer B 权威校验 | 会把客户端预检和服务端真正规则混为一谈 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| `subsystem-announcement` | base class、submit / heartbeat、Ex validator | 参考子系统 |
| `subsystem-news` | base class、submit / heartbeat、fixtures | 高压测子系统 |
| 后续 `subsystem-*` | 公共框架与 contract examples | 并行开发与自动化生成 |
| `assembly` | 参考模板、默认配置 | 项目总装与启动 |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| 主编 / 架构 owner | Ex 合同是否被稳定执行 |
| reviewer | 是否有人把 Layer B 细节塞回生产者接口 |
| 自动化代理 | 是否有可复用脚手架、fixtures 和统一 API |

---

## 8. 总体系统结构

### 8.1 Payload Authoring 主线

```text
subsystem S0 logic
  -> build Ex-1 / Ex-2 / Ex-3 payload from contracts models
  -> local validator
  -> optional entity preflight
  -> submit client
  -> receive SubmitReceipt
```

### 8.2 Heartbeat 主线

```text
subsystem runtime status
  -> build Ex-0 heartbeat payload
  -> heartbeat validator
  -> heartbeat client
  -> receive heartbeat receipt
```

### 8.3 Fixture / Reference 主线

```text
contracts schemas
  -> contract examples
  -> fixture bundles
  -> reference subsystem template
  -> test / scaffolding consumers
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| SubsystemRegistrationSpec | 子系统注册配置与能力声明 | 本地配置文件 / package metadata |
| SubmitBackendConfig | backend 选择与连接配置 | YAML / TOML / env 映射 |
| ContractExampleBundle | 一组合同样例载荷 | fixtures 目录 |
| ReferenceSubsystemTemplate | 参考子系统模板文件集合 | 模板 / 代码生成输入 |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| BaseSubsystemContext | 子系统运行上下文 | 进程级 |
| ValidationResult | 本地校验结果 | 单次校验期间 |
| SubmitReceipt | 一次提交的统一执据 | 单次提交期间 |
| HeartbeatStatus | 当前健康状态快照 | 单次心跳期间 |
| BackendAdapter | Lite / Full 传输实现 | 进程级 |
| EntityPreflightResult | 可选实体预检结果 | 单次提交期间 |

### 9.3 核心对象详细设计

#### SubsystemRegistrationSpec

**角色**：声明一个子系统是谁、支持什么、如何被统一框架识别。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| subsystem_id | String | 如 `subsystem-news` |
| version | String | 子系统版本 |
| domain | String | 领域，如 `news` / `announcement` |
| supported_ex_types | Array[String] | `Ex-0` / `Ex-1` / `Ex-2` / `Ex-3` 子集 |
| owner | String | owner 或维护人 |
| heartbeat_policy_ref | String | 心跳策略引用 |
| capabilities | JSON | 可选能力声明 |

#### SubmitReceipt

**角色**：屏蔽 Lite / Full backend 差异的统一提交回执。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| accepted | Boolean | 是否被 backend 接受 |
| receipt_id | String | SDK 统一 receipt 标识 |
| backend_kind | String | `lite_pg` / `full_kafka` / `mock` |
| transport_ref | String \| Null | backend 侧执据，如 queue id / message ref |
| validator_version | String | 使用的本地校验版本 |
| warnings | Array[String] | 非阻断警告 |
| errors | Array[String] | 阻断错误 |

#### ValidationResult

**角色**：描述一次本地 Ex payload 校验的结果。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| is_valid | Boolean | 是否通过 |
| ex_type | String | `Ex-0` / `Ex-1` / `Ex-2` / `Ex-3` |
| schema_version | String | 来自 `contracts` 的版本 |
| field_errors | Array[String] | 字段级错误 |
| warnings | Array[String] | 兼容性或弱约束警告 |
| preflight | JSON \| Null | 可选实体预检结果 |

#### BaseSubsystemContext

**角色**：子系统运行时访问 config、submit、heartbeat、fixtures 的统一入口。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| registration | SubsystemRegistrationSpec | 注册元数据 |
| backend_adapter | BackendAdapter | 当前 transport 实现 |
| validator_registry | JSON | Ex validator 注册表 |
| heartbeat_client | Object | 心跳接口 |
| submit_client | Object | 提交接口 |
| fixture_bundle_ref | String \| Null | 默认 fixtures 引用 |

#### ContractExampleBundle

**角色**：给测试、脚手架和自动化代理提供一组标准样例。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| bundle_name | String | 样例集名称 |
| ex_type | String | 对应 Ex 类型 |
| valid_examples | Array[JSON] | 合法样例 |
| invalid_examples | Array[JSON] | 非法样例 |
| notes | String | 说明 |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- 正式 payload schema -> `contracts`
- SDK 本地配置 / 注册信息 / backend 配置 -> 文件型配置
- fixtures / contract examples / 参考模板 -> 仓库文件
- submit receipt / validation result -> 运行时对象，不做 authoritative persistence

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| 注册与 backend 配置 | YAML / TOML / env | 简单、可版本化 |
| fixtures / examples | JSON / YAML | 易读、适合自动化生成 |
| 参考模板 | Python package template files | 便于脚手架复用 |
| 运行时 receipt | 内存对象 / 测试日志 | authoritative receipt 在 backend 侧 |

### 10.3 关系模型

- `SubsystemRegistrationSpec.supported_ex_types -> contracts.ExPayloadSchema`
- `ValidationResult.ex_type -> contracts Ex schema version`
- `SubmitReceipt.transport_ref` 指向 Lite 队列或 Full backend 侧执据，但其 authoritative 记录不归 SDK
- `EntityPreflightResult` 只能引用 `entity-registry` 查询结果，不能派生出新 canonical ID

---

## 11. 核心计算/算法设计

### 11.1 本地合同校验算法

**输入**：Ex payload。

**输出**：`ValidationResult`。

**处理流程**：

```text
receive payload
  -> identify ex_type
  -> load contracts model for ex_type
  -> validate required fields / enums / shape
  -> optionally run producer-side semantic checks
  -> return ValidationResult
```

**规则**：

- `Ex-0` 只允许 Metadata / 心跳语义
- 校验只基于 `contracts`，不自造 schema
- 本地通过不代表 Layer B 一定接受，只代表 producer 侧没有明显违约

### 11.2 实体预检算法

**输入**：Ex-1 / Ex-2 / Ex-3 payload 中的 entity refs。

**输出**：`EntityPreflightResult`。

**处理流程**：

```text
extract entity refs
  -> if no entity refs return skip
  -> query entity-registry lookup helper
  -> mark obvious unresolved refs
  -> attach warnings or block based on policy
```

**边界**：

- 这是 preflight helper，不是实体解析 owner
- 不能因为 preflight 失败就自动发明 canonical_entity_id
- Layer B / downstream 仍可做更严格的权威校验

### 11.3 提交 backend 选择算法

**输入**：`SubmitBackendConfig`、payload。

**输出**：`SubmitReceipt`。

**处理流程**：

```text
read backend mode
  -> if lite use PgSubmitBackend
  -> if full use KafkaCompatibleSubmitBackend
  -> call backend.submit(payload)
  -> normalize backend response to SubmitReceipt
```

**规则**：

- 子系统业务代码不关心 backend 类型
- Lite / Full 切换只能通过配置或依赖注入完成
- Receipt 字段必须稳定，不能暴露 PG / Kafka 私有细节给上层业务

### 11.4 心跳算法

**输入**：当前子系统健康状态。

**输出**：Ex-0 heartbeat payload 与 `SubmitReceipt`。

**处理流程**：

```text
collect runtime status
  -> build Ex-0 payload
  -> validate against contracts
  -> submit through heartbeat client
  -> return receipt
```

**规则**：

- Ex-0 字段、频率、超时策略由 SDK 统一定义
- 心跳接收与状态表落地不归 SDK
- 心跳失败不应伪装为业务 payload 提交成功

### 11.5 Fixture 生成算法

**输入**：目标 Ex 类型、schema 版本、示例模板。

**输出**：`ContractExampleBundle`。

**处理流程**：

```text
load contracts schema
  -> create valid example set
  -> create invalid example set
  -> annotate notes and edge cases
  -> publish fixture bundle
```

### 11.6 参考子系统脚手架算法

**输入**：`SubsystemRegistrationSpec`、默认 backend 配置、fixture refs。

**输出**：参考子系统项目骨架。

**处理流程**：

```text
create subsystem package skeleton
  -> wire BaseSubsystemContext
  -> include submit / heartbeat calls
  -> copy fixture examples
  -> expose sample handlers for Ex-1 / Ex-2 / Ex-3
```

---

## 12. 触发/驱动引擎设计

### 12.1 触发源类型

| 类型 | 来源 | 示例 |
|------|------|------|
| 启动触发 | 子系统进程启动 | 加载 registration 与 backend config |
| 提交触发 | 子系统 S0 完成一次候选产出 | 发送 Ex-1 / Ex-2 / Ex-3 |
| 心跳触发 | 定时器 / scheduler | 发送 Ex-0 |
| 测试触发 | CI / 本地开发 | 跑 fixtures / contract examples |
| 模式切换触发 | 配置变更 | Lite -> Full backend 切换 |

### 12.2 关键触发流程

```text
subsystem_emit(payload)
  -> validate_payload()
  -> optional_preflight()
  -> submit(payload)
  -> receive receipt
```

### 12.3 启动顺序基线

| 阶段 | 动作 | 说明 |
|------|------|------|
| P0 | `contracts` 冻结 Ex-0~Ex-3 | SDK 必须建立在稳定合同之上 |
| P1 | `data-platform` 先提供 Lite 提交入口与 Layer B receipt 语义 | SDK 需要可用 backend |
| P2 | `entity-registry` 提供可选 entity preflight helper | 子系统更早发现明显实体问题 |
| P4a | `subsystem-sdk` 打通 base class + validator + submit + heartbeat | 先形成公共骨架 |
| P4a+b | 参考子系统基于 SDK 展开 | announcement / news 等开始并行 |
| P11 | `stream-layer` 接管 Full backend submit adapter | transport 不改业务代码 |

---

## 13. 输出产物设计

### 13.1 Submit Receipt

**面向**：`subsystem-*`

**结构**：

```text
{
  accepted: Boolean
  receipt_id: String
  backend_kind: String
  transport_ref: String | null
  warnings: Array[String]
  errors: Array[String]
}
```

### 13.2 Validation Report

**面向**：开发、CI、自动化代理

**结构**：

```text
{
  ex_type: String
  is_valid: Boolean
  schema_version: String
  field_errors: Array[String]
  warnings: Array[String]
  preflight: Object | null
}
```

### 13.3 Heartbeat Payload

**面向**：Layer B / 监控

**结构**：

```text
{
  subsystem_id: String
  version: String
  heartbeat_at: Timestamp
  status: String
  last_output_at: Timestamp | null
  pending_count: Integer
}
```

### 13.4 Contract Example Bundle

**面向**：测试、脚手架、参考子系统

**结构**：

```text
{
  bundle_name: String
  ex_type: String
  valid_examples: Array[Object]
  invalid_examples: Array[Object]
}
```

### 13.5 Reference Subsystem Skeleton

**面向**：子系统开发者、自动化代理

**结构**：

```text
{
  registration_spec: Object
  example_handlers: Object
  fixture_refs: Array[String]
  default_backend_config: Object
}
```

---

## 14. 系统模块拆分

**组织模式**：单个 Python 项目，内部按公共上下文、校验、提交、心跳、fixtures 分 package。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `subsystem_sdk.base` | Python | 库 | base class、运行上下文、注册装载 |
| `subsystem_sdk.validate` | Python | 库 | Ex-0~Ex-3 本地校验 |
| `subsystem_sdk.submit` | Python | 库 | 统一 submit client 与 receipt 归一化 |
| `subsystem_sdk.heartbeat` | Python | 库 | Ex-0 心跳 payload 与发送 |
| `subsystem_sdk.backends` | Python | 库 | Lite / Full backend adapters |
| `subsystem_sdk.fixtures` | Python + JSON/YAML | 库 / 资源 | contract examples 与 fixture bundles |
| `subsystem_sdk.testing` | Python | 库 | 参考子系统测试辅助 |

**关键设计决策**：

- SDK 只 import `contracts`，不复制 Ex schema
- backend adapter 要求 interface 稳定，Lite / Full 切换不能改子系统业务层
- entity preflight 是辅助层，不是实体解析层
- pure structured adapter 路线不依赖 `subsystem-sdk`
- reference subsystem 和 fixtures 要作为正式交付物，而不是事后补样例

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| payload 校验 | Pydantic v2 + `contracts` models | 复用单一 schema 真相 |
| backend adapter | Python protocols / strategy pattern | 屏蔽 Lite / Full 差异 |
| 配置加载 | YAML / TOML / env | 简单、可版本化 |
| fixtures/examples | JSON / YAML | 自动化友好 |
| 开发脚手架 | Python package template | 可复用 |

最低要求：

- 可 import `contracts` 的 Ex-0~Ex-3 模型
- Lite 模式下有可用的提交 backend
- Full 模式预留 Kafka-compatible backend adapter 接口
- 可选 entity preflight helper 可用或可降级为空实现

---

## 16. API 与接口合同

### 16.1 Python 接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `register_subsystem(spec)` | 注册子系统元数据 | `SubsystemRegistrationSpec` |
| `validate_payload(payload)` | 本地校验 Ex payload | Ex payload |
| `submit(payload)` | 提交 Ex payload | Ex payload |
| `send_heartbeat(status_payload)` | 发送 Ex-0 心跳 | Ex-0 payload |
| `run_entity_preflight(payload)` | 对 entity refs 做可选预检 | Ex-1/2/3 payload |
| `load_fixture_bundle(name)` | 读取 fixture bundle | bundle name |
| `create_reference_subsystem(spec)` | 生成参考子系统骨架 | registration spec |

### 16.2 协议接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `SubmitBackendInterface` | 统一 backend 提交接口 | payload |
| `HeartbeatBackendInterface` | 心跳发送接口 | Ex-0 payload |
| `SubsystemBaseInterface` | 公共子系统运行接口 | config / context |
| `ValidationInterface` | 本地合同校验接口 | payload |

### 16.3 版本与兼容策略

- `subsystem-sdk` 只接受 backward compatible 的 Ex schema 演进
- `SubmitReceipt` 结构必须稳定，供子系统和测试长期消费
- Lite / Full backend 切换不能要求改 `submit()` 的调用签名
- `Ex-0` 语义任何时候都必须保持为 Metadata / 心跳
- `submit()` / `send_heartbeat()` 只允许 backward compatible 扩展；如有 breaking change，必须显式升级 major version 并同步更新 reference subsystem skeleton
- Lite / Full transport 切换只能通过 backend adapter 配置完成，不能通过新增第二套 submit API 实现

---

## 18. 测试与验证策略

### 18.1 单元测试

- Ex-0 心跳语义固定测试
- Ex payload 中不含 ingest metadata 的边界测试
- backend adapter 归一化 receipt 测试
- entity preflight 只做辅助不发明新 ID 的测试
- fixture bundle 载入与 schema roundtrip 测试

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| Lite 模式提交 Ex-2 | 验证本地校验 + submit receipt 主干 |
| Lite 模式发送 Ex-0 心跳 | 验证 heartbeat 路径 |
| 配置切换到 Full backend mock | 验证 API 不变 |
| 参考子系统使用 SDK 跑通一条 Ex-1/2/3 | 验证骨架可用 |
| fixtures 驱动 contract tests | 验证自动化生成基础 |

### 18.3 协议 / 契约测试

- `subsystem-sdk` import 的 Ex schema 与 `contracts` 版本一致
- `submit()` 只接受 producer-owned 字段构成的 payload
- `SubmitReceipt` 与 backend private fields 解耦

### 18.4 回归与边界测试

- `Ex-0` 被误写成非心跳语义的回归测试
- `submitted_at` / `ingest_seq` 被错误加入 producer payload 的回归测试
- 子系统代码感知 PG / Kafka 明细的静态检查
- 纯结构化 adapter 误依赖 `subsystem-sdk` 的边界测试

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 单次本地 payload 校验耗时 | `< 50ms` | 常规 payload |
| Lite 模式提交 receipt 返回耗时 | `< 500ms` | 正常本地网络环境 |
| 心跳发送耗时 | `< 300ms` | 常规健康上报 |
| fixture bundle 载入耗时 | `< 100ms` | 单次测试加载 |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| `Ex-0` 语义误用率 | `0` | 不允许漂移 |
| ingest metadata 泄漏进 producer payload 次数 | `0` | 边界必须守住 |
| Lite -> Full 切换需要改业务代码的次数 | `0` | interface 必须稳定 |
| 参考子系统使用 SDK 跑通率 | `100%` | announcement / news 要可用 |

---

## 20. 项目交付物清单

### 20.1 SDK 核心

- subsystem base class
- Ex-0~Ex-3 validator
- submit client
- heartbeat client
- backend adapter 抽象

### 20.2 开发与测试支撑

- fixtures / contract examples
- reference subsystem skeleton
- testing helpers
- registration loader

### 20.3 兼容性能力

- Lite / Full backend 切换配置
- entity preflight helper
- receipt normalization

---

## 21. 实施路线图

### 阶段 0：合同与 transport 边界冻结（1-2 天）

**阶段目标**：先把最容易漂移的接口边界写死。

**交付**：
- Ex-0 语义约束
- producer-owned fields 列表
- `SubmitReceipt` 初版

**退出条件**：`submitted_at` / `ingest_seq` 不再出现在 SDK producer payload 设计里。

### 阶段 1：P4a SDK 主干（3-5 天）

**阶段目标**：打通 base class、validator、Lite submit、heartbeat。

**交付**：
- base class
- Ex validators
- Lite submit backend
- heartbeat client

**退出条件**：参考子系统可以提交 Ex-0 / Ex-1 / Ex-2 / Ex-3。

### 阶段 2：P4a Fixtures 与参考子系统（2-4 天）

**阶段目标**：让 SDK 真正可被自动化复用。

**交付**：
- contract examples
- fixture bundles
- reference subsystem skeleton

**退出条件**：自动化代理能基于 SDK 生成并跑通一个参考子系统。

### 阶段 3：P4b entity preflight 与集成增强（2-4 天）

**阶段目标**：补齐实体预检与更清晰的错误反馈。

**交付**：
- entity preflight helper
- richer validation report
- better receipt warnings

**退出条件**：明显错误的 entity refs 能在本地被提前发现。

### 阶段 4：P11 Full backend 切换（按需）

**阶段目标**：保持 SDK API 不变的前提下切到 Kafka-compatible backend。

**交付**：
- Full backend adapter
- Lite / Full switch config
- compatibility tests

**退出条件**：子系统代码不改，只切配置即可切换 transport。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| Ex 合同在 SDK 内被二次定义 | 合同真相分裂 | 强制只 import `contracts` |
| SDK 暴露 PG / Kafka 细节 | P11 切换成本爆炸 | receipt 归一化 + backend adapter |
| 本地校验与 Layer B 规则长期漂移 | producer 误判通过 | 保留契约测试和 E2E fixtures |
| entity preflight 被误当权威解析器 | 锚点逻辑混乱 | 明确 helper only，不生成 ID |
| 参考子系统缺失 | SDK 变成空壳库 | 把 reference skeleton 纳入正式交付物 |

---

## 23. 验收标准

项目完成的最低标准：

1. `subsystem-sdk` 能提供稳定的 base class、Ex-0~Ex-3 validator、submit client 和 heartbeat client
2. `Ex-0` 在 SDK 语义中固定为 Metadata / 心跳，不存在其他解释
3. producer payload 中不包含 `submitted_at` / `ingest_seq` / `layer_b_receipt_id`
4. `submit(payload) -> Receipt` 在 Lite / Full backend 下调用签名不变
5. SDK 能生成 fixtures / contract examples / reference subsystem skeleton，供参考子系统直接使用
6. SDK 不拥有 Layer B 队列表、Kafka topic、权威去重/冲突检测和具体子系统业务逻辑
7. 文档中定义的 OWN / BAN / EDGE 与主项目 `12 + N` 模块边界一致

---

## 24. 一句话结论

`subsystem-sdk` 子项目不是“给子系统省几行代码”的薄封装，而是主项目里唯一负责把子系统出口做成长期稳定接口的公共 owner。  
它如果边界不稳，后面所有 `subsystem-*` 的并行开发、自动化生成和 Lite -> Full 平滑切换都会一起失控。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `subsystem-sdk` |
| 脚本先读章节 | `§1` `§4` `§5.2` `§5.4` `§9` `§14` `§16` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现一个 client 能力、一个 validator、一个 backend adapter，或一组 reference skeleton / fixture |
| 默认写入范围 | 当前 repo 的 SDK 客户端、validator、fixture、reference skeleton、测试、文档和配置 |
| 内部命名基线 | 以 `§14` 内部模块名和 `§16` 接口名为准，不额外再起第二套 submit API |
| 禁止越界 | 不复制 Ex schema、不做 Layer B 权威判定、不暴露 transport 细节给子系统业务代码 |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落 `submit()` / `send_heartbeat()` / `validate_payload()` 主干
2. 再落 receipt 归一化、本地预检和 reference subsystem skeleton
3. 再落 fixture、contract examples 和自动化生成能力
4. Full backend adapter 只在 Lite 主干稳定后单独推进

补充规则：

- 单个 issue 默认只改一个 SDK 能力，不同时改 submit API 和 backend adapter
- 任何 Lite / Full 切换都必须通过 adapter 配置完成，不通过改业务调用签名实现

### 25.3 Blocker 升级条件

- 需要在 SDK 内复制或改写 `contracts` 中的 Ex schema
- 需要让 SDK 负责 Layer B 权威校验、去重或冲突检测
- `submit()` / `send_heartbeat()` 出现 breaking change 但没有 major version 升级计划
- 无法提供 reference subsystem 或 fixture 作为最小验收样本
