## 目录职责
`astock_data/formatters` 只做结构化模型到文本的纯转换。

## 关键文件
- `dispatch.py`，模型到渲染器的分发。
- `__init__.py`，`to_markdown` 与 `to_text` 导出。

## 允许修改
- 文本排版、字段展示顺序、空值文案、表格样式。
- 仅围绕 `model_dump` 的纯转换逻辑。

## 禁止修改
- 不要引入网络请求，不要读写缓存，不要变更模型内容。
- 不要把格式化器变成 UI、LLM 或业务层。

## 验证命令
- `python -m pytest tests/test_formatters.py -q`
- `python -m pytest -q`

## 与公共接口的关系
格式化器只消费 19 个公开入口返回的模型，不参与数据获取，也不承担 ticker 解析。
