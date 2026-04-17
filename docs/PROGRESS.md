# 项目进度概览 — subsystem-sdk

> 任务详情见 `docs/TASK_BREAKDOWN.md`
> 项目文档：`docs/subsystem-sdk.project-doc.md`
> 最后更新：2026-04-17

---

## 里程碑总览

| Milestone | 标题 | 路线图阶段 | Issue 数 | 状态 | 退出条件 |
|-----------|------|------------|----------|------|----------|
| milestone-0 | 合同与 transport 边界冻结 | 阶段 0 | 3 | not started | `submitted_at` / `ingest_seq` / `layer_b_receipt_id` 不出现在 SDK producer payload 设计中；`SubmitReceipt` / `ValidationResult` 接口冻结 |
| milestone-1 | P4a SDK 主干 | 阶段 1 | 4 | not started | base class + Ex validators + Lite submit + heartbeat 跑通；参考子系统可提交 Ex-0/1/2/3 |
| milestone-2 | P4a Fixtures 与参考子系统 | 阶段 2 | 2 | not started | 自动化代理可基于 SDK 生成并跑通一个参考子系统 |
| milestone-3 | P4b Entity Preflight 与校验报告增强 | 阶段 3 | 2 | not started | 明显错误的 entity refs 能在本地预先发现，receipt warnings 富化 |
| milestone-4 | P11 Full backend 切换 | 阶段 4 | 2 | not started | 不改业务代码、仅切配置即可在 Lite ↔ Full 间切换 transport |

合计：**13 个 issue / 5 个 milestone**

---

## Issue 索引

### milestone-0 — 合同与 transport 边界冻结
| ID | 标题 | Labels | 依赖 | 状态 |
|----|------|--------|------|------|
| ISSUE-001 | Python 包脚手架与 contracts 依赖边界基线 | P0, infrastructure, milestone-0 | 无 | todo |
| ISSUE-002 | Ex-0 语义常量与 Producer-owned Fields 冻结 | P0, infrastructure, milestone-0 | #ISSUE-001 | todo |
| ISSUE-003 | SubmitReceipt 与 ValidationResult 数据模型初版 | P0, infrastructure, milestone-0 | #ISSUE-001, #ISSUE-002 | todo |

### milestone-1 — P4a SDK 主干
| ID | 标题 | Labels | 依赖 | 状态 |
|----|------|--------|------|------|
| ISSUE-004 | Ex 校验器与 contracts 加载主调度 | P0, feature, milestone-1 | #ISSUE-002, #ISSUE-003 | todo |
| ISSUE-005 | 统一 Submit Client 与 Lite PG Backend Adapter | P0, feature, integration, milestone-1 | #ISSUE-003, #ISSUE-004 | todo |
| ISSUE-006 | Heartbeat Client 与 Ex-0 心跳 Payload 构造 | P0, feature, milestone-1 | #ISSUE-004, #ISSUE-005 | todo |
| ISSUE-007 | Subsystem Base Class 与注册装载 | P0, feature, integration, milestone-1 | #ISSUE-005, #ISSUE-006 | todo |

### milestone-2 — P4a Fixtures 与参考子系统
| ID | 标题 | Labels | 依赖 | 状态 |
|----|------|--------|------|------|
| ISSUE-008 | Contract Example Bundle 与 Fixture 加载器 | P1, feature, testing, milestone-2 | #ISSUE-004 | todo |
| ISSUE-009 | Reference Subsystem Skeleton 与 Testing Helpers | P1, feature, integration, milestone-2 | #ISSUE-007, #ISSUE-008 | todo |

### milestone-3 — P4b Entity Preflight 与校验报告增强
| ID | 标题 | Labels | 依赖 | 状态 |
|----|------|--------|------|------|
| ISSUE-010 | Entity Preflight Helper 与可降级查询通道 | P1, feature, milestone-3 | #ISSUE-004 | todo |
| ISSUE-011 | Validation Report 与 Receipt Warnings 富化 | P1, feature, integration, milestone-3 | #ISSUE-009, #ISSUE-010 | todo |

### milestone-4 — P11 Full backend 切换
| ID | 标题 | Labels | 依赖 | 状态 |
|----|------|--------|------|------|
| ISSUE-012 | Full Backend Adapter（Kafka-compatible） | P1, feature, milestone-4 | #ISSUE-005 | todo |
| ISSUE-013 | Lite/Full 切换配置与兼容性测试套件 | P1, integration, testing, milestone-4 | #ISSUE-005, #ISSUE-007, #ISSUE-012 | todo |

---

## 关键不可协商约束追踪（PR 审查必查）

| 约束 | 守护机制 | 落地 issue |
|------|----------|------------|
| Ex-0 语义固定为 Metadata / 心跳 | `EX0_SEMANTIC` 常量 + `assert_ex0_semantic` | ISSUE-002 |
| `submitted_at` / `ingest_seq` / `layer_b_receipt_id` 不进 producer payload | `INGEST_METADATA_FIELDS` + `assert_no_ingest_metadata` | ISSUE-002 |
| Ex schema 只从 `contracts` import | `_contracts.py` 唯一入口 + AST lint | ISSUE-001, ISSUE-004 |
| `submit(payload) -> Receipt` Lite/Full 一致 | `SubmitBackendInterface` + 兼容矩阵 | ISSUE-005, ISSUE-013 |
| Receipt 不暴露 PG/Kafka 私有字段 | `assert_no_private_leak` + `RESERVED_PRIVATE_KEYS` | ISSUE-003, ISSUE-012 |
| SDK 不替代 Layer B 权威校验 | preflight 仅 warning，不发明 ID | ISSUE-010, ISSUE-011 |

---

## 当前阶段

**当前阶段**：milestone-0（合同与 transport 边界冻结）
**下一动作**：开始 ISSUE-001（包脚手架）
**Blocker 升级条件**（见 §25.3）：需要复制 contracts schema、需要 SDK 做权威校验、`submit()` / `send_heartbeat()` 出现 breaking change 但无 major bump 计划、无法提供 reference subsystem / fixture
