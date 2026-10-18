# 浏览器回归

在专用测试数据库启动本地服务，使用独立浏览器上下文运行；该脚本会实际完成测试并产生匿名统计与临时续答，不应拿线上生产数据作为日常测试环境。

```sh
python3.12 -m venv .e2e-venv
.e2e-venv/bin/pip install -r tests/requirements.txt
.e2e-venv/bin/playwright install chromium
# 变量填本地测试管理员密码，脚本不回显。
export ATLAS_ADMIN_TEST_PASSWORD='your-development-admin-password'
.e2e-venv/bin/python tests/auto_advance.py
.e2e-venv/bin/python tests/e2e.py
```

默认访问 `http://127.0.0.1:5173`。`ATLAS_TEST_URL` 可指定专用验收环境，`ATLAS_BROWSER_EXECUTABLE` 可指定现有 Chromium；测试产物位于忽略提交的 `artifacts/e2e`。

覆盖 99 题逐题完成、刷新、暂停、复用 99＋201、七天链接恢复、并发冲突与撤销、离线作答、专项不适用、报告章节、PNG、PDF、历史和后台预览。布局断言覆盖 320 / 360 / 390 / 600 / 768 / 820 / 1024 / 1440px。真正的 Safari、Android / iOS 和实体设备体验仍需人工试用。

自动前进专项回归检查连续双击不跳题、已保存答案回看修改、暂停 / 题号取消待切换、存储失败保留当前题与重试。完整流程通过每题选项直接推进，不再点击“下一题”。

子路径部署可设置 `ATLAS_TEST_URL=http://172.29.20.85/mbti/`；脚本同时支持根路径与子路径，并检查续答链接使用相同入口前缀。
