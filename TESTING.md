# 自动化测试指南 (Automated Testing Guide)

本项目包含后端计算逻辑的单元测试和 API 的集成测试。

## 1. 环境准备 (Prerequisites)

确保你已经激活了 Python 虚拟环境:

```powershell
# Windows
..\.venv\Scripts\activate
```

安装测试依赖 (如果尚未安装):

```bash
pip install pytest httpx
```

## 2. 运行测试 (Running Tests)

> [!IMPORTANT]
> **务必先进入 `账单` 目录！**
> 
> ```powershell
> cd c:\仓库\Antigravity-Manager\账单
> ```
> 
> 如果你在项目根目录 (`Antigravity-Manager`) 运行测试，可能会遇到 `ImportError`。

### 运行所有测试

在 `c:\仓库\Antigravity-Manager\账单` 目录下运行:

```bash
pytest -v
```

`-v` (verbose) 参数会显示每个测试用例的详细执行结果。

### 运行特定测试文件

如果你只想运行计算逻辑的单元测试:

```bash
pytest tests/unit/test_calculation.py -v
```

如果你只想运行 API 的集成测试:

```bash
pytest tests/integration/test_api_clients.py -v
```

## 3. 解读测试结果 (Interpreting Results)

- **PASSED (绿色)**: 测试通过。逻辑符合预期。
- **FAILED (红色)**: 测试失败。
    -如果在 **Unit Test** 失败，说明 `calculate_service_fee.py` 中的解析逻辑与预期不符。
    - 如果在 **Integration Test** 失败，说明 API 接口或数据库操作有问题。

## 4. 常见问题

- **ModuleNotFoundError**: 确保你在 `c:\仓库\Antigravity-Manager\账单` 根目录下运行 `pytest`，这样 Python 才能正确找到 `api` 和根目录下的模块。
## 4. 什么时候需要运行测试？ (When to Run Tests)

自动化测试是保障代码质量的安全网，建议在以下场景运行：

1.  **修改核心逻辑后**：比如修改了 `calculate_service_fee.py` 中的正则表达式或计算公式，运行测试可以确保没有破坏现有的计费规则。
2.  **新增客户或规则时**：当你添加了新的特殊客户计费逻辑，应该先添加对应的测试用例，确保新逻辑正确且不影响其他客户。
3.  **重构代码时**：比如优化数据库查询或重构目录结构（如本次），运行测试能快速发现 `ImportError` 或数据库连接问题。
4.  **部署上线前**：在将代码推送到服务器之前，务必运行一次全量测试 (`pytest -v`)，确保发布版本的稳定性。
