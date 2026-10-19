# 知序 · Self Atlas

中文 MBTI 风格自我探索网站，适配手机、平板和电脑。原创问卷用于自我了解，尚未经过标准化心理测量验证，不是官方 MBTI 量表、心理诊断或招聘筛选工具。

- **精简 99 题**：E/I、S/N、T/F、J/P，四维分别 25/25/25/24 题。
- **详细 300 题**：共用 99 题＋21 题人格深化＋职业、社交、恋爱各 60 题。每个专项 6 个主题，每主题 10 题。
- 同版本精简答案可复用，只补答 201 题；选择后自动保存并进入下一题，支持回看修改、暂停、刷新恢复、已加载问卷离线作答。
- 报告包含连续偏好位置、均衡说明、优势盲点、具体情境、作答证据、分领域建议及 7 / 30 天行动。四维不混入专项答案。
- 7 天跨设备续答链接 / 二维码，临时加密保存，修订冲突提示、撤销、完成删除和到期清理。
- 本机最近 10 份报告、类型参考库、打印 / PDF、PNG 摘要。
- 答题开始前填写学号和姓名；提交后身份、逐题答案及完整报告加密保存在服务端。
- 管理后台支持查看全部提交记录、搜索、查看完整报告与答案、逐份导出 JSON；同时支持题库维护、版本发布、报告预览、匿名汇总和修改密码。

## 项目结构

```text
frontend/       Vue 3 + TypeScript + Vite
backend/app/    FastAPI + SQLAlchemy，原创题库和确定性计分
backend/tests/  计分、权限、版本和续答测试
deploy/         离线镜像构建、Nginx、systemd、备份恢复
compose.yaml    PostgreSQL 17 + API + Nginx
docs/          设计、计分、运维和验收记录
```

## 本地开发

需要 Python 3.12、Node.js 22.12+（本次使用 24）。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
# 使用独立随机值；不要将实际密钥写入版本库。
export SECRET_KEY='replace-with-your-random-value-at-least-32-characters'
export ADMIN_PASSWORD='replace-with-a-random-password-at-least-9-characters'
export PUBLIC_ORIGIN='http://127.0.0.1:5173'
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8091 --no-access-log
```

另一终端：

```sh
cd frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`。默认开发数据库是 `.local/atlas.db`；设置 `DATABASE_URL` 可切换 PostgreSQL。初始管理员为 `admin`，密码由首次启动的环境变量创建，之后以数据库为准。

```sh
.venv/bin/python -m pytest -q backend/tests
cd frontend
npm run build
```

## 部署

使用独立目录 `/opt/mbti-site`。官网通过同一端口下的 `/mbti/` 访问；专用主机的独立部署见 [运维说明](docs/运维说明.md)。源码不包含服务器密码、后台密码、数据库密钥、实际 `.env`、数据库或用户草稿。

官网入口：[开放工具](http://172.29.20.85/tools)，MBTI [测试页面](http://172.29.20.85/mbti/)，后台 `/mbti/admin`。该服务器复用现有 Kubernetes，独立部署配置及备份见 [服务器 85 部署](docs/服务器85部署.md)。

原服务器 `http://172.29.20.105:8086` 保留运行。以上地址属于私有网络，需要客户端能访问该网络。面向公网时需配置可达入口、域名和 HTTPS，并同步修改 `PUBLIC_ORIGIN` 和 `COOKIE_SECURE`。

## 数据与计分

未提交的答案保存在当前浏览器 IndexedDB。提交报告时身份、原始答案和完整报告使用应用密钥加密后保存在服务器数据库，供管理员查看和逐份导出；记录保留至运营方清理。主动续答产生的加密临时草稿 7 天失效，清理任务每 5 分钟运行，备份排除此类临时数据。匿名使用汇总不包含身份或逐题答案。

七级答案乘正反向后归一化。45–55% 为解释上的接近均衡，恰好 50% 用 X；这些百分比不是准确率或能力分。专项“不适用”不计零，每主题至少 7 / 10 有效回答才提供描述性位置。详见 [计分说明](docs/计分说明.md) 和 [验收记录](docs/验收记录.md)。

尚未进行受试者研究、信效度检验或实体设备实测；当前验证使用自动化浏览器与服务器集成测试。题库上线后仍应根据小规模试用反馈审阅和修订。
