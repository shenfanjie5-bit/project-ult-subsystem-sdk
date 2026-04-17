# 项目任务拆解

## 阶段 0：合同与 transport 边界冻结

**目标**：在写任何 client 代码之前，先把 Ex-0 语义、producer-owned fields 列表、SubmitReceipt 接口与项目骨架冻结成可被静态校验的事实，杜绝下游 milestone 漂移。
**前置依赖**：无

### ISSUE-001: Python 包脚手架与 contracts 依赖边界基线
**labels**: P0, infrastructure, milestone-0

#### 背景与目标
当前仓库只有 `pyproject.toml` 占位与一个 `docs/` 目录，没有任何 Python 包结构，也没有 `contracts` 的 import 通道。本 issue 落地 `subsystem_sdk.*` 顶层包结构、pytest 配置、`contracts` 依赖占位与一份**只允许 Ex schema 来自 contracts** 的静态约束测试，使后续 §14 的 `base / validate / submit / heartbeat / backends / fixtures / testing` 7 个子包都能按统一布局落点。这是 §4.2 与 §6.2 中 “SDK 不复制 schema” 这一不可协商约束的物理基础：包结构和 import lint 必须在 client 代码之前就位，否则下个 milestone 的开发者第一反应就是把 schema 抄进 SDK。

#### 所属模块
**主写入路径（允许实现）**：
- `pyproject.toml`
- `subsystem_sdk/__init__.py`
- `subsystem_sdk/base/__init__.py`
- `subsystem_sdk/validate/__init__.py`
- `subsystem_sdk/submit/__init__.py`
- `subsystem_sdk/heartbeat/__init__.py`
- `subsystem_sdk/backends/__init__.py`
- `subsystem_sdk/fixtures/__init__.py`
- `subsystem_sdk/testing/__init__.py`
- `subsystem_sdk/_contracts.py`
- `tests/__init__.py`
- `tests/test_package_layout.py`
- `tests/test_contracts_boundary.py`
- `tests/conftest.py`

**邻近只读 / 集成路径**：
- `docs/subsystem-sdk.project-doc.md`（参考 §14、§16 的命名）
- `CLAUDE.md`、`AGENTS.md`（项目级指令，不修改）

**禁止越界路径**：
- 不要新建 `subsystem_sdk/contracts/`（那是 `contracts` 模块的领地）
- 不要在任何 `__init__.py` 中实现业务逻辑（仅暴露符号）
- 不要修改 `docs/subsystem-sdk.project-doc.md`

#### 实现范围
- 项目元数据
  - `pyproject.toml`: 把 `[tool.setuptools] packages = []` 改成 `find` 配置，新增 `[tool.setuptools.packages.find] include = ["subsystem_sdk*"]`；保留 `requires-python = ">=3.11"`；在 `[project] dependencies` 加 `pydantic>=2.6`；新增 `[project.optional-dependencies] test = ["pytest>=8"]`；保留 `[tool.pytest.ini_options]`。
- 包骨架（每个 `__init__.py` 仅放模块 docstring + `__all__: list[str] = []`）
  - `subsystem_sdk/__init__.py`: 顶层 docstring 引用 §1，定义 `__version__ = "0.1.0"`，导出 `__all__ = ["__version__"]`。
  - `subsystem_sdk/base/__init__.py`、`validate/__init__.py`、`submit/__init__.py`、`heartbeat/__init__.py`、`backends/__init__.py`、`fixtures/__init__.py`、`testing/__init__.py`: 每个顶部一行 docstring 注明该子包对应 §14 的哪一行。
- contracts 依赖通道
  - `subsystem_sdk/_contracts.py`: 唯一允许 `import contracts`（或当前阶段 `try/except ImportError` 的占位）的模块；导出 `def get_ex_schema(ex_type: str) -> type` 占位实现，签名为 `def get_ex_schema(ex_type: str) -> type | None`，当前实现 `raise NotImplementedError("populated in milestone-1")`；常量 `SUPPORTED_EX_TYPES: tuple[str, ...] = ("Ex-0", "Ex-1", "Ex-2", "Ex-3")`。
- 测试基线
  - `tests/conftest.py`: 暴露 `PROJECT_ROOT: Path` fixture 指向仓库根目录。
  - `tests/test_package_layout.py`: 7 个用例，分别 `import subsystem_sdk.<subpackage>` 不抛错、确认 `subsystem_sdk.__version__ == "0.1.0"`。
  - `tests/test_contracts_boundary.py`: 用 AST 扫描 `subsystem_sdk/**/*.py`，断言除 `subsystem_sdk/_contracts.py` 外没有任何文件出现 `import contracts` / `from contracts`。函数签名 `def _scan_imports(path: Path) -> set[str]`。

#### 不在本次范围
- 不实现任何 validator、submit client、receipt 类（属 ISSUE-002 / ISSUE-003）
- 不连接真实 `contracts` 包（当前 `contracts` 仓还未冻结，`_contracts.py` 仅占位）
- 不写任何具体 backend adapter（属 milestone-1）
- 不要在本 issue 内改 `README.md` 之外的文档；新增使用文档另开 issue
- 如果发现 `contracts` 仓的真实 import path 和占位不符，必须按 §25.3 升级 blocker，禁止在本 SDK 内复制 schema 抢跑

#### 关键交付物
- `pyproject.toml`：包含 `pydantic>=2.6` 依赖与 setuptools find 配置
- `subsystem_sdk/_contracts.py`：唯一 contracts 入口，常量 `SUPPORTED_EX_TYPES`、占位函数 `get_ex_schema`
- 7 个子包目录与各自 `__init__.py`，每个文件 ≤ 10 行
- `tests/test_contracts_boundary.py`：AST-level lint，函数签名 `def test_no_direct_contracts_import_outside_gateway() -> None`
- `tests/test_package_layout.py`：7 + 1 个 import / version 用例
- README.md 顶部追加一段 “Implementation has begun — see docs/TASK_BREAKDOWN.md” 提示，仅一行

#### 验收标准
**Core scaffold:**
- [ ] `pip install -e .` 在 Python 3.11 下成功
- [ ] `python -c "import subsystem_sdk; print(subsystem_sdk.__version__)"` 输出 `0.1.0`
- [ ] 7 个子包均可被 `import` 且不触发副作用
**Contracts boundary:**
- [ ] `subsystem_sdk/_contracts.py` 是唯一含 `contracts` 字面量 import 的文件
- [ ] `SUPPORTED_EX_TYPES` 严格等于 `("Ex-0", "Ex-1", "Ex-2", "Ex-3")`
- [ ] `get_ex_schema("Ex-1")` 当前抛 `NotImplementedError`
**Tests:**
- [ ] `tests/test_package_layout.py` 至少 8 个用例，全部通过
- [ ] `tests/test_contracts_boundary.py` 至少 1 个用例，AST 扫描覆盖全部 `subsystem_sdk/**/*.py`
- [ ] `pytest` 整体退出码 0，无 warning（`-W error`）

#### 验证命令
```bash
# Install
pip install -e ".[test]"
# Layout + boundary tests
pytest tests/test_package_layout.py tests/test_contracts_boundary.py -v
# Full regression
pytest -q
# Smoke import
python -c "import subsystem_sdk, subsystem_sdk.base, subsystem_sdk.validate, subsystem_sdk.submit, subsystem_sdk.heartbeat, subsystem_sdk.backends, subsystem_sdk.fixtures, subsystem_sdk.testing; print('ok')"
```

#### 依赖
无前置依赖

---

### ISSUE-002: Ex-0 语义常量与 Producer-owned Fields 冻结
**labels**: P0, infrastructure, milestone-0

#### 背景与目标
§3、§5.4、§6.2、§22 反复强调：`Ex-0` 必须永远等价于 “Metadata / 心跳”，且 `submitted_at`、`ingest_seq`、`layer_b_receipt_id` 三个 ingest metadata 字段**绝不**进入 producer payload。这两条是 SDK 全部下游设计的承重墙。本 issue 把这两条规则物化成：(a) 一组冻结常量与枚举，(b) 一个 `assert_producer_only(payload)` 守护函数，(c) 一组针对 §22 风险表前两行的回归测试。在 milestone-1 开始写真正的 validator 前先落这块，可以让任何后续误把 ingest metadata 写入 payload 的代码立刻在 CI 红掉。

#### 所属模块
**主写入路径**：
- `subsystem_sdk/validate/semantics.py`
- `subsystem_sdk/validate/__init__.py`（仅追加 `__all__` 导出）
- `tests/validate/__init__.py`
- `tests/validate/test_ex0_semantics.py`
- `tests/validate/test_producer_only.py`

**邻近只读路径**：
- `subsystem_sdk/_contracts.py`（读取 `SUPPORTED_EX_TYPES`）

**禁止越界路径**：
- 不要在 `validate/` 下放 schema 校验逻辑（属 ISSUE-006）
- 不要新增任何 backend / submit 文件
- 不要在 `semantics.py` 里 import `pydantic`（保持纯 Python，避免循环依赖）

#### 实现范围
- 常量层
  - `subsystem_sdk/validate/semantics.py` 顶部定义：
    - `EX0_SEMANTIC: Final[str] = "metadata_or_heartbeat"`
    - `EX0_BANNED_SEMANTICS: Final[frozenset[str]] = frozenset({"fact", "signal", "graph_delta", "business_event"})`
    - `INGEST_METADATA_FIELDS: Final[frozenset[str]] = frozenset({"submitted_at", "ingest_seq", "layer_b_receipt_id"})`
    - `PRODUCER_OWNED_REQUIRED: Final[dict[str, frozenset[str]]]` —— 按 §9.3 表格枚举每种 Ex 的必备 producer-owned 字段名集合（先放最小集合：Ex-0 = `{"subsystem_id", "version", "heartbeat_at", "status"}`；Ex-1/2/3 = `{"subsystem_id", "produced_at"}`）
- 守护函数
  - `def assert_ex0_semantic(declared_semantic: str) -> None`：若不等于 `EX0_SEMANTIC` 抛 `Ex0SemanticError`
  - `def assert_no_ingest_metadata(payload: Mapping[str, Any]) -> None`：扫描顶层与一层嵌套 dict，发现 `INGEST_METADATA_FIELDS` 中任何 key 时抛 `IngestMetadataLeakError`，错误消息包含字段名
  - `def assert_producer_only(ex_type: str, payload: Mapping[str, Any]) -> None`：先校验 `ex_type in SUPPORTED_EX_TYPES`，再调用 `assert_no_ingest_metadata`，再校验 `PRODUCER_OWNED_REQUIRED[ex_type]` 全部存在
- 异常
  - `class SemanticsError(ValueError)`、`class Ex0SemanticError(SemanticsError)`、`class IngestMetadataLeakError(SemanticsError)`、`class MissingProducerFieldError(SemanticsError)`
- 导出
  - `subsystem_sdk/validate/__init__.py` 把上述常量/函数/异常加入 `__all__`
- 测试
  - `tests/validate/test_ex0_semantics.py`：覆盖正确语义通过、`EX0_BANNED_SEMANTICS` 中每个值都抛 `Ex0SemanticError`
  - `tests/validate/test_producer_only.py`：分别用 3 个泄漏字段 × 顶层/嵌套两位置 = 6 个用例验证 `IngestMetadataLeakError`；用缺字段 payload 验证 `MissingProducerFieldError`；用 happy path payload 验证 `assert_producer_only` 通过

#### 不在本次范围
- 不实现 schema-level 字段类型校验（留给 ISSUE-006 配合 contracts pydantic model）
- 不实现 entity preflight（属 milestone-3）
- 不要把守护函数挂到 `submit()` 上（`submit_client` 在 ISSUE-005 才落地）
- 不引入 `pydantic` validator 装饰器风格，本 issue 只用纯函数 + 异常
- 如果项目 doc §3 之后追加新的 ingest metadata 字段，必须在 contracts 侧先冻结，再回到本 issue 升级 `INGEST_METADATA_FIELDS`，不得在其他模块隐式扩列

#### 关键交付物
- `subsystem_sdk/validate/semantics.py`：4 个常量 + 4 个异常类 + 3 个守护函数
- 函数签名清单：
  - `assert_ex0_semantic(declared_semantic: str) -> None`
  - `assert_no_ingest_metadata(payload: Mapping[str, Any]) -> None`
  - `assert_producer_only(ex_type: str, payload: Mapping[str, Any]) -> None`
- 异常类层级：`SemanticsError ← {Ex0SemanticError, IngestMetadataLeakError, MissingProducerFieldError}`
- 公开 API：`from subsystem_sdk.validate import assert_producer_only, INGEST_METADATA_FIELDS, EX0_SEMANTIC` 必须可用
- 至少 12 个 pytest 用例覆盖 §22 风险表前两行

#### 验收标准
**Core constants:**
- [ ] `INGEST_METADATA_FIELDS == frozenset({"submitted_at", "ingest_seq", "layer_b_receipt_id"})`
- [ ] `EX0_SEMANTIC == "metadata_or_heartbeat"`
- [ ] `PRODUCER_OWNED_REQUIRED` 含 4 个 key（Ex-0..Ex-3）
**Guards:**
- [ ] 任何 ingest metadata 字段出现在 payload 顶层或一层嵌套都触发 `IngestMetadataLeakError`
- [ ] `assert_ex0_semantic` 对 `EX0_BANNED_SEMANTICS` 的所有值都抛错
- [ ] `assert_producer_only` 对未知 `ex_type` 抛 `SemanticsError`
**Exceptions:**
- [ ] 4 个异常类全部继承自 `ValueError`
**Tests:**
- [ ] `tests/validate/test_ex0_semantics.py` ≥ 5 用例
- [ ] `tests/validate/test_producer_only.py` ≥ 7 用例
- [ ] 全套 pytest 通过，无新 warning

#### 验证命令
```bash
# Targeted
pytest tests/validate/ -v
# Boundary regression (ensure ISSUE-001 still green)
pytest tests/test_contracts_boundary.py tests/test_package_layout.py -v
# Full
pytest -q
# Public API smoke
python -c "from subsystem_sdk.validate import assert_producer_only, INGEST_METADATA_FIELDS, EX0_SEMANTIC; assert_producer_only('Ex-0', {'subsystem_id':'x','version':'1','heartbeat_at':'t','status':'ok'}); print('ok')"
```

#### 依赖
依赖 #ISSUE-001（包脚手架与 `_contracts.py` 提供 `SUPPORTED_EX_TYPES`）

---

### ISSUE-003: SubmitReceipt 与 ValidationResult 数据模型初版
**labels**: P0, infrastructure, milestone-0

#### 背景与目标
§9.3、§13.1、§13.2 与 §16.3 把 `SubmitReceipt` 与 `ValidationResult` 列为 “transport 无关、对子系统长期稳定” 的两个核心运行时对象。后续 milestone-1 的 submit client 与 validator 都要返回这两类对象，且 §11.3 要求 backend response 必须先经过 `normalize_receipt()` 才能交给上层；§22 风险表第二行明确要求 receipt 不得泄漏 PG/Kafka 私有字段。本 issue 在 transport 与 validator 都还没有的阶段先把这两类 Pydantic 模型、`backend_kind` 枚举与归一化函数冻结，作为后续所有 backend adapter 必须遵守的输出契约。

#### 所属模块
**主写入路径**：
- `subsystem_sdk/submit/receipt.py`
- `subsystem_sdk/submit/__init__.py`（追加导出）
- `subsystem_sdk/validate/result.py`
- `subsystem_sdk/validate/__init__.py`（追加导出）
- `tests/submit/__init__.py`
- `tests/submit/test_receipt.py`
- `tests/validate/test_result.py`

**邻近只读路径**：
- `subsystem_sdk/validate/semantics.py`（仅读取常量）
- `subsystem_sdk/_contracts.py`（仅读取 `SUPPORTED_EX_TYPES`）

**禁止越界路径**：
- 不要在 `submit/` 下放任何真实 backend 调用（属 ISSUE-005）
- 不要在本 issue 引入 `httpx` / `psycopg` / `confluent-kafka` 等 transport 依赖
- 不要在 receipt 中暴露 `pg_queue_id` / `kafka_topic` / `kafka_offset` 等私有键

#### 实现范围
- 枚举与字面量
  - `subsystem_sdk/submit/receipt.py` 顶部：
    - `BackendKind = Literal["lite_pg", "full_kafka", "mock"]`
    - `BACKEND_KINDS: Final[tuple[BackendKind, ...]] = ("lite_pg", "full_kafka", "mock")`
- `SubmitReceipt`（pydantic v2 `BaseModel`，`model_config = ConfigDict(frozen=True, extra="forbid")`）
  - 字段（顺序按 §13.1）：
    - `accepted: bool`
    - `receipt_id: str`（非空，`min_length=1`）
    - `backend_kind: BackendKind`
    - `transport_ref: str | None = None`
    - `validator_version: str`
    - `warnings: tuple[str, ...] = ()`
    - `errors: tuple[str, ...] = ()`
  - 校验器：`@field_validator("errors")` 当 `accepted=True` 时 `errors` 必须为空，否则抛 `ValueError`
- `normalize_receipt`
  - `def normalize_receipt(*, accepted: bool, backend_kind: BackendKind, transport_ref: str | None, validator_version: str, warnings: Sequence[str] = (), errors: Sequence[str] = (), receipt_id: str | None = None) -> SubmitReceipt`：
    - 当 `receipt_id is None` 时用 `uuid.uuid4().hex` 生成
    - 把 `warnings` / `errors` 转为 `tuple`
    - 返回不可变 `SubmitReceipt`
  - `RESERVED_PRIVATE_KEYS: Final[frozenset[str]]` 包含 `{"pg_queue_id", "kafka_topic", "kafka_offset", "kafka_partition"}`，并提供 `def assert_no_private_leak(extra: Mapping[str, Any]) -> None` 用于 backend 适配层在 ISSUE-005 调用
- `ValidationResult`（pydantic v2 `BaseModel`，`frozen=True`）
  - 字段（按 §9.3 / §13.2）：
    - `is_valid: bool`
    - `ex_type: Literal["Ex-0","Ex-1","Ex-2","Ex-3"]`
    - `schema_version: str`
    - `field_errors: tuple[str, ...] = ()`
    - `warnings: tuple[str, ...] = ()`
    - `preflight: dict[str, Any] | None = None`
  - 校验：`is_valid=True` 时 `field_errors` 必须为空
  - 工厂：`@classmethod def ok(cls, ex_type, schema_version, *, warnings=()) -> "ValidationResult"`、`@classmethod def fail(cls, ex_type, schema_version, *, field_errors, warnings=()) -> "ValidationResult"`
- 公开导出
  - `from subsystem_sdk.submit import SubmitReceipt, normalize_receipt, BackendKind`
  - `from subsystem_sdk.validate import ValidationResult`
- 测试
  - `tests/submit/test_receipt.py`：
    - 构造合法 receipt 通过
    - `accepted=True` 且 `errors` 非空抛错
    - `backend_kind` 不在白名单抛错
    - `normalize_receipt` 自动生成 `receipt_id`
    - `assert_no_private_leak` 命中 `RESERVED_PRIVATE_KEYS` 抛错
    - `SubmitReceipt` 实例 `frozen=True`：尝试改字段抛 `ValidationError` / `TypeError`
  - `tests/validate/test_result.py`：
    - `ValidationResult.ok` 与 `fail` 工厂正确
    - `is_valid=True` 配 `field_errors=("x",)` 抛错
    - `ex_type` 不在 4 个值范围内抛错

#### 不在本次范围
- 不实现 `submit()` 调用、不接 backend（属 ISSUE-005）
- 不实现 `validate_payload()` 主调度（属 ISSUE-006）
- 不实现 heartbeat receipt 特化类型（heartbeat 复用同一个 `SubmitReceipt`，按 §13.1 / §11.4）
- 不引入 entity preflight 字段细节（`preflight` 暂为 `dict[str, Any] | None`，结构在 milestone-3 再细化）
- 如果发现 §13.1 与 §9.3 字段集对不上，必须停下来澄清 doc，不要在 SDK 私自加字段

#### 关键交付物
- `SubmitReceipt`（pydantic frozen model，7 字段）+ `BackendKind` + `BACKEND_KINDS`
- `ValidationResult`（pydantic frozen model，6 字段，含 `ok` / `fail` 工厂）
- `normalize_receipt(...) -> SubmitReceipt` 函数
- `assert_no_private_leak(extra) -> None` 守护函数 + `RESERVED_PRIVATE_KEYS`
- 公开 API：`subsystem_sdk.submit.SubmitReceipt`、`subsystem_sdk.submit.normalize_receipt`、`subsystem_sdk.validate.ValidationResult`
- ≥ 12 个 pytest 用例覆盖正/负/不可变性

#### 验收标准
**Core models:**
- [ ] `SubmitReceipt` 在 `accepted=True, errors=("x",)` 时 `pydantic.ValidationError`
- [ ] `SubmitReceipt` 不接受 `backend_kind="rabbitmq"`（不在白名单）
- [ ] `SubmitReceipt` 实例不可变（`frozen=True`）
- [ ] `ValidationResult.ok(...)` 默认 `field_errors=()`，`is_valid=True`
- [ ] `ValidationResult.fail(...)` 强制 `is_valid=False` 且 `field_errors` 非空
**Receipt normalization:**
- [ ] `normalize_receipt(...)` 不传 `receipt_id` 时返回 32 字符十六进制
- [ ] `assert_no_private_leak({"kafka_topic":"x"})` 抛 `ValueError`
- [ ] `BACKEND_KINDS` 与 `BackendKind` Literal 完全一致
**Public API:**
- [ ] 上述符号可从对应包顶层 import
**Tests:**
- [ ] `tests/submit/test_receipt.py` ≥ 7 用例
- [ ] `tests/validate/test_result.py` ≥ 5 用例
- [ ] `pytest -q` 全绿

#### 验证命令
```bash
# Targeted
pytest tests/submit/test_receipt.py tests/validate/test_result.py -v
# Public API smoke
python -c "from subsystem_sdk.submit import SubmitReceipt, normalize_receipt; r = normalize_receipt(accepted=True, backend_kind='mock', transport_ref=None, validator_version='v0'); assert r.receipt_id and r.accepted; print(r)"
python -c "from subsystem_sdk.validate import ValidationResult; print(ValidationResult.ok(ex_type='Ex-1', schema_version='v0'))"
# Regression
pytest -q
```

#### 依赖
依赖 #ISSUE-001（包脚手架与 pydantic 依赖）, #ISSUE-002（`SUPPORTED_EX_TYPES` 与 semantics 常量供 receipt/result 复用）

---

## 阶段 1：P4a SDK 主干（base / validator / Lite submit / heartbeat）

**目标**：在阶段 0 冻结的接口契约之上，搭出 base class、Ex 校验器、Lite PG submit backend 与 heartbeat client，使一个参考子系统能用 SDK 提交 Ex-0/Ex-1/Ex-2/Ex-3。
**前置依赖**：阶段 0 全部完成（ISSUE-001 ~ ISSUE-003）

### ISSUE-004: Ex 校验器与 contracts 加载主调度
**labels**: P0, feature, milestone-1
**摘要**：在 `subsystem_sdk/validate/` 下落地 `validate_payload(payload, ex_type) -> ValidationResult` 主入口，按 §11.1 流程组合 contracts pydantic 校验、`assert_producer_only`、版本号回填，并在 `_contracts.py` 中实现真正的 `get_ex_schema` 加载。
**所属模块**：`subsystem_sdk/validate/`（主写入：`engine.py`、`registry.py`、`__init__.py`）；`subsystem_sdk/_contracts.py`（实现 schema 加载）；`tests/validate/`
**写入边界**：允许修改 `validate/`、`_contracts.py`、`tests/validate/`；禁止改 `submit/`、`backends/`、`heartbeat/`、`fixtures/`；禁止在 SDK 内复制任何 contracts schema 字段。
**实现顺序**：先在 `_contracts.py` 内做 schema 解析与 schema_version 抽取 → 再写 `engine.validate_payload` 主调度（identify→load→pydantic validate→producer-only check→收集 errors）→ 再写 `registry` 注册自定义弱约束 hook → 最后用 fixture-less 单元测试覆盖 4 个 Ex 类型 × happy/error 各两个用例，目标 1000-1500 行（含测试）。
**依赖**：依赖 #ISSUE-002（semantics 守护）, #ISSUE-003（`ValidationResult` 模型）

---

### ISSUE-005: 统一 Submit Client 与 Lite PG Backend Adapter
**labels**: P0, feature, integration, milestone-1
**摘要**：实现 §11.3 + §16.1 中 `submit(payload) -> SubmitReceipt` 统一接口、`SubmitBackendInterface` Protocol、`PgSubmitBackend`（Lite 模式），并在内部接 `validate_payload` 做 fail-fast，受理 `data-platform` 提供的 PG 队列入口。
**所属模块**：`subsystem_sdk/submit/`（主写入：`client.py`、`protocol.py`、`__init__.py`）；`subsystem_sdk/backends/`（主写入：`lite_pg.py`、`mock.py`、`__init__.py`）；`tests/submit/`、`tests/backends/`
**写入边界**：允许修改 `submit/`、`backends/`、相关测试；禁止改 `validate/`（仅消费 ISSUE-004 接口）、`heartbeat/`、`base/`、`fixtures/`；禁止在 receipt 暴露 `pg_*` 私钥（必须经过 `assert_no_private_leak`）。
**实现顺序**：先定义 `SubmitBackendInterface` Protocol → 再写 `MockSubmitBackend`（仅返回 normalize_receipt）→ 再写 `PgSubmitBackend`（参数化连接 dsn/queue table，用 `psycopg` 占位接口注入，便于 mock）→ 再写 `SubmitClient` 把 validate→preflight-skip→backend.submit→normalize_receipt 串起来 → 最后用 mock backend 做 5+ 集成测试与 1 个端到端 happy path。规模 1000-1500 行。
**依赖**：依赖 #ISSUE-003（`SubmitReceipt` / `normalize_receipt`）, #ISSUE-004（`validate_payload`）

---

### ISSUE-006: Heartbeat Client 与 Ex-0 心跳 Payload 构造
**labels**: P0, feature, milestone-1
**摘要**：按 §11.4、§13.3、§16.1 实现 `send_heartbeat(status_payload) -> SubmitReceipt`、`HeartbeatBackendInterface`、Ex-0 payload 构造器与默认心跳策略（频率/超时常量），复用 ISSUE-005 的 backend 抽象。
**所属模块**：`subsystem_sdk/heartbeat/`（主写入：`client.py`、`payload.py`、`policy.py`、`__init__.py`）；`tests/heartbeat/`
**写入边界**：允许修改 `heartbeat/` 与对应测试；禁止改 `submit/client.py`（如需复用 backend 选择，必须通过依赖注入而非反向 import）；禁止把 `last_output_at` / `pending_count` 之外的业务字段塞进 Ex-0 payload。
**实现顺序**：先定义 `HeartbeatPolicy` dataclass（interval_seconds、timeout_ms 默认值）→ 再写 `build_ex0_payload(subsystem_id, version, status, last_output_at, pending_count) -> dict` → 再写 `HeartbeatClient` 调用 `validate_payload(payload, ex_type="Ex-0")` 后委托 backend.submit → 最后回归测试覆盖 “心跳失败不能伪装为业务提交成功”（§11.4 规则）。规模 1000-1500 行（含测试与 policy 文档字符串）。
**依赖**：依赖 #ISSUE-004（Ex-0 校验）, #ISSUE-005（backend 抽象与 receipt 归一化）

---

### ISSUE-007: Subsystem Base Class 与注册装载
**labels**: P0, feature, integration, milestone-1
**摘要**：按 §9.3 / §11 / §16 实现 `SubsystemRegistrationSpec`、`BaseSubsystemContext`、`register_subsystem(spec)` 与 base class，把 ISSUE-004/005/006 的 client 装配成单一运行壳，提供给后续参考子系统直接 import。
**所属模块**：`subsystem_sdk/base/`（主写入：`registration.py`、`context.py`、`subsystem.py`、`config.py`、`__init__.py`）；`tests/base/`
**写入边界**：允许修改 `base/` 与测试；禁止在 base class 内出现新闻/公告/研报字眼（§22 反模式）；禁止反向修改 `validate/`、`submit/`、`heartbeat/`。
**实现顺序**：先 `SubsystemRegistrationSpec`（pydantic frozen，字段按 §9.3 表）→ 再 YAML/TOML loader（用标准库 `tomllib` + 可选 `pyyaml`，无 yaml 时 fallback 报清晰错误）→ 再 `BaseSubsystemContext` 持有 `submit_client / heartbeat_client / validator_registry / backend_adapter` → 再 `register_subsystem(spec)` 单例注册表 → 最后写一个内存版参考流程的集成测试（注册 → submit Ex-1 mock backend → send_heartbeat），证明 §23 验收 1 可达。规模 1000-1500 行。
**依赖**：依赖 #ISSUE-005（submit client）, #ISSUE-006（heartbeat client）

---

## 阶段 2：P4a Fixtures 与参考子系统

**目标**：把 SDK 从 “能跑” 推进到 “能被自动化代理复用”，落地 contract examples、fixture bundles 与 reference subsystem skeleton。
**前置依赖**：阶段 1 全部完成（ISSUE-004 ~ ISSUE-007）

### ISSUE-008: Contract Example Bundle 与 Fixture 加载器
**labels**: P1, feature, testing, milestone-2
**摘要**：按 §9.3 / §11.5 / §13.4 实现 `ContractExampleBundle`、`load_fixture_bundle(name)`、4 个 Ex 类型各一组合法 + 非法样例，存放为 JSON/YAML 资源，供后续脚手架与子系统集成测试复用。
**所属模块**：`subsystem_sdk/fixtures/`（主写入：`bundle.py`、`loader.py`、`__init__.py`、`data/ex0/*.json`、`data/ex1/*.json`、`data/ex2/*.json`、`data/ex3/*.json`）；`tests/fixtures/`
**写入边界**：允许修改 `fixtures/` 与测试；禁止把 fixture 当成第二份 schema（每个非法样例必须配一行 `notes` 解释违反哪条 §3 / §5.4 规则）；禁止在 fixture data 中出现真实业务名词（用占位）。
**实现顺序**：先定义 `ContractExampleBundle`（pydantic frozen，字段按 §13.4）→ 再写 `loader` 读取 `subsystem_sdk/fixtures/data/<ex_type>/<name>.json` 并解析成 bundle → 再生成 4 类 Ex 各 ≥ 2 valid + ≥ 3 invalid 的占位样例（覆盖 ingest metadata 泄漏、Ex-0 语义被改写等风险） → 最后用 `validate_payload` 跑 roundtrip 测试，确保 valid 样例全过、invalid 样例全 fail。规模 1000-1500 行（多数在数据文件）。
**依赖**：依赖 #ISSUE-004（validator 用于 roundtrip）

---

### ISSUE-009: Reference Subsystem Skeleton 与 Testing Helpers
**labels**: P1, feature, integration, milestone-2
**摘要**：按 §11.6 / §13.5 / §20 实现 `create_reference_subsystem(spec)` 脚手架生成器、`subsystem_sdk.testing` 中的 `MockBackend`、`run_subsystem_smoke()` 等辅助函数，并把 fixture bundle 直接挂进生成的项目，使自动化代理一条命令就能复制出可跑的参考子系统。
**所属模块**：`subsystem_sdk/testing/`（主写入：`helpers.py`、`mock_backend.py`、`__init__.py`）；`subsystem_sdk/base/scaffold.py`（新增脚手架函数）；`subsystem_sdk/fixtures/templates/`（参考子系统模板文件）；`tests/testing/`、`tests/base/test_scaffold.py`
**写入边界**：允许修改 `testing/`、新增 `base/scaffold.py`、新增 `fixtures/templates/`；禁止在模板里固化任何具体子系统业务逻辑（仅放 `example_handler_ex1` 等占位）；禁止脚手架向仓库根目录之外写入。
**实现顺序**：先抽出 `MockBackend`（继承 ISSUE-005 的 `MockSubmitBackend`，叠加事件捕获）→ 再写 `run_subsystem_smoke(context) -> list[SubmitReceipt]` 跑一遍 Ex-0/1/2/3 → 再写 `create_reference_subsystem(spec, target_dir)` 把 `templates/` 拷贝到目标目录并替换 `subsystem_id` 占位 → 最后端到端测试：在 `tmp_path` 生成一个参考子系统、import 它、跑 `run_subsystem_smoke`，断言 4 张 receipt 全部 `accepted=True`，证明 §23 验收 5 可达。规模 1000-1500 行。
**依赖**：依赖 #ISSUE-007（base class 与 context）, #ISSUE-008（fixture bundles）

---

## 阶段 3：P4b Entity Preflight 与校验报告增强

**目标**：补齐可选的实体预检 helper 与更丰富的 `ValidationResult` / `SubmitReceipt.warnings`，让明显的实体引用错误能在子系统侧提前暴露，但绝不替代 Layer B / entity-registry 的权威解析。
**前置依赖**：阶段 2 全部完成（ISSUE-008、ISSUE-009）

### ISSUE-010: Entity Preflight Helper 与可降级查询通道
**labels**: P1, feature, milestone-3
**摘要**：按 §11.2 / §16.1 实现 `run_entity_preflight(payload) -> EntityPreflightResult`，对 Ex-1/2/3 中的 entity refs 做可选预检，通过 Protocol 注入 `entity-registry` 查询客户端，缺省降级为空实现并打 warning。
**所属模块**：`subsystem_sdk/validate/preflight.py`（新增）；`subsystem_sdk/validate/__init__.py`（追加导出）；`tests/validate/test_preflight.py`
**写入边界**：允许修改 `validate/preflight.py` 与测试；禁止在 preflight 内自动生成 `canonical_entity_id`（§22 反模式）；禁止把 preflight 失败升级为强制 block（默认 warning，由 policy 决定是否 fail）。
**实现顺序**：先定义 `EntityPreflightResult`（字段：`checked: bool`、`unresolved_refs: tuple[str, ...]`、`warnings: tuple[str, ...]`、`policy: Literal["warn","block","skip"]`）→ 再定义 `EntityRegistryLookup` Protocol（`def lookup(refs: Iterable[str]) -> Mapping[str, bool]`）→ 再写 `run_entity_preflight(payload, *, lookup=None, policy="warn")`：无 lookup 时返回 `checked=False, policy="skip"` → 最后回归测试覆盖 §22 风险表第 4 行（preflight 不发明 ID）。规模 1000-1500 行。
**依赖**：依赖 #ISSUE-004（validator 主调度，preflight 结果挂 `ValidationResult.preflight`）

---

### ISSUE-011: Validation Report 与 Receipt Warnings 富化
**labels**: P1, feature, integration, milestone-3
**摘要**：把 ISSUE-010 的 preflight 结果接入 `validate_payload` 与 `submit()` 流程，丰富 `ValidationResult.warnings` / `SubmitReceipt.warnings` 内容，新增 `richer_validation_report(result) -> str` 用于人类可读输出，并把这些字段挂进 reference subsystem smoke test。
**所属模块**：`subsystem_sdk/validate/engine.py`（修改）；`subsystem_sdk/submit/client.py`（修改：把 preflight warnings 透传到 receipt）；`subsystem_sdk/validate/report.py`（新增）；`tests/validate/test_report.py`、`tests/submit/test_client_preflight.py`
**写入边界**：允许修改 `validate/engine.py`、`submit/client.py`、新增 `validate/report.py` 与测试；禁止改 `SubmitReceipt` schema（仅写 warnings 字段，已有结构稳定）；禁止把 preflight error 升级为 `errors`（仍然 warnings-only，除非 policy="block"）。
**实现顺序**：先在 engine 中接入可选 preflight → 再在 submit client 中把 `ValidationResult.warnings + preflight.warnings` 合并写入 receipt.warnings → 再写 `richer_validation_report` 输出多行字符串 → 最后扩展 ISSUE-009 的 smoke test，断言带 unresolved ref 的 Ex-1 fixture 触发 receipt warning，但仍 `accepted=True`。规模 1000-1500 行。
**依赖**：依赖 #ISSUE-010（preflight helper）, #ISSUE-009（smoke test 入口）

---

## 阶段 4：P11 Full Backend 切换

**目标**：在 `submit()` / `send_heartbeat()` 调用签名零变更前提下，新增 Kafka-compatible Full backend adapter 与 Lite/Full 切换配置，并通过兼容性测试证明子系统业务代码不需任何修改。
**前置依赖**：阶段 3 全部完成（ISSUE-010、ISSUE-011），且 Lite 主干在生产/集成环境稳定运行

### ISSUE-012: Full Backend Adapter（Kafka-compatible）
**labels**: P1, feature, milestone-4
**摘要**：按 §11.3 / §16 实现 `KafkaCompatibleSubmitBackend`，复用 ISSUE-005 的 `SubmitBackendInterface`，确保 receipt 经过 `assert_no_private_leak` 后只输出 `transport_ref`（不暴露 topic/partition/offset），并提供与 `PgSubmitBackend` 等价的单元/集成测试矩阵。
**所属模块**：`subsystem_sdk/backends/full_kafka.py`（新增）；`subsystem_sdk/backends/__init__.py`（追加导出）；`tests/backends/test_full_kafka.py`
**写入边界**：允许修改 `backends/full_kafka.py` 与测试；禁止改 `submit/client.py`（除非纯加 backend 选择分支）、禁止改 `receipt.py` schema、禁止改 `validate/`；如发现需要 receipt schema 演进，必须按 §25.3 升级 blocker。
**实现顺序**：先定义 producer 客户端依赖注入接口（`ProducerProtocol.send(topic, payload) -> Awaitable[BrokerAck]`）→ 再实现 `KafkaCompatibleSubmitBackend.submit(payload) -> SubmitReceipt`（topic 来自配置而非 payload，ack 转 `transport_ref` 哈希字符串）→ 再写测试覆盖 broker 失败 → `accepted=False, errors=(...)`、ack 成功 → `accepted=True` 且 receipt 不含任何 kafka 私钥。规模 1000-1500 行。
**依赖**：依赖 #ISSUE-005（backend protocol、receipt 归一化）

---

### ISSUE-013: Lite/Full 切换配置与兼容性测试套件
**labels**: P1, integration, testing, milestone-4
**摘要**：按 §16.3 / §21 阶段 4 实现 `SubmitBackendConfig` 加载、`backend_kind: "lite_pg" | "full_kafka"` 切换路径、参数化兼容性测试矩阵（同一 fixture 在两个 backend 下产生结构相同、字段集相同的 receipt），证明 §23 验收 4 / §19.2 “Lite→Full 切换需要改业务代码次数 = 0”。
**所属模块**：`subsystem_sdk/base/config.py`（扩展 backend 配置）；`subsystem_sdk/submit/client.py`（在已有 backend 注入处加配置驱动选择）；`tests/integration/test_backend_switch.py`（新增）；`tests/integration/__init__.py`
**写入边界**：允许修改 `base/config.py`、`submit/client.py`（仅 backend 选择分支）、新增 `tests/integration/`；禁止新增第二套 `submit_full(...)` API（§25.2 明文禁止）；禁止把 backend kind 字符串以外的 transport 细节暴露给上层。
**实现顺序**：先在 `SubmitBackendConfig` 增加 `backend_kind: BackendKind` 与对应 backend 子配置 → 再写 `build_submit_backend(config) -> SubmitBackendInterface` 工厂 → 再扩展 `SubmitClient.__init__` 接 backend 工厂 → 最后写参数化集成测试：同一组 valid / invalid fixture 分别跑 `lite_pg`（用 mock pg）和 `full_kafka`（用 mock producer），断言 `(accepted, errors, warnings, len(receipt_id))` 全部一致，仅 `backend_kind` / `transport_ref` 不同。规模 1000-1500 行。
**依赖**：依赖 #ISSUE-005（Lite backend）, #ISSUE-012（Full backend）, #ISSUE-007（base config 入口）
