## 目录职责
`astock_data/clients` 放各数据源客户端，只做网络抓取、解析和轻量规范化。

## 关键文件
- `eastmoney.py`，东财唯一 chokepoint，所有 `eastmoney.com` URL 只能放这里。
- `tencent.py`，腾讯实时行情客户端。
- `sina.py`，新浪行情、财报、新闻客户端。
- `tdx.py`，mootdx 包装客户端。
- `__init__.py`，客户端导出集合。

## 允许修改
- 客户端解析、超时、错误映射、会话注入、请求节流相关实现。
- 仅在对应 vendor 文件内扩展该 vendor 的 URL 与解析逻辑。

## 禁止修改
- 不要把 `eastmoney.com` URL 写到别的文件。
- 不要恢复百度 PAE 资金流接口。
- 不要把客户端升级成业务层、缓存层或模型层。

## 验证命令
- `python -m pytest tests/test_eastmoney_client.py -q`
- `python -m pytest tests/test_tencent_client.py -q`
- `python -m pytest tests/test_sina_client.py -q`
- `python -m pytest tests/test_tdx_client.py -q`

## 与公共接口的关系
客户端只给服务层和公开门面提供原始数据，不能直接面对 CLI 或 MCP，也不能跳过 resolver。
