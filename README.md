# 日常 · 工作台

一个人用的中文工作台：待办事项、工作笔记、常用链接。
电脑与手机连接**同一个在线服务**，即可共用数据；页面每 30 秒读取更新，
切回页面时也会更新。编辑冲突会提示，不会直接覆盖另一台设备的新内容。

已提供密码登录、搜索、编辑与删除、待办完成、截止日期及 JSON 数据导出。
页面适配手机。不依赖外部字体、CDN 或第三方账号。

## 在开发环境运行

需要 Python 3.12 或更新版本。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python app.py
```

程序默认仅监听本机端口 8000。初次运行创建 `.data/`：

- `password.txt`：随机初始登录密码，仅保存在本地，文件权限 600。
- `session.key`：会话签名密钥。
- `workbench.sqlite3`：数据及密码的哈希值。

这三个文件均不会提交到 Git。请在自己的终端查看初始密码文件，勿分享或上传。
也可以直接设置一个自己的密码：

```sh
.venv/bin/python app.py set-password
```

按提示输入两次至少 12 位的密码，输入时不会显示。设置后移除初始密码文件并使旧登录失效。
忘记密码时可以再次运行此命令；已有待办和笔记不会删除。

## 云环境中的已验证命令

仓库位于 `/workspace/info87`，依赖位于 `/workspace/.venvs/info87`。
在已有隔离环境直接使用此仓库，不需要创建额外 Git worktree。

```sh
cd /workspace/info87
/workspace/.venvs/info87/bin/python -m pip install -r requirements.lock
WORKBENCH_PYTHON=/workspace/.venvs/info87/bin/python sh scripts/check.sh
/workspace/.venvs/info87/bin/python app.py
```

`GET /healthz` 会检查数据库连接。它只验证基本就绪；完整功能还应测试登录和增删改。
云环境内的本机监听地址不是公开网站，不能直接给办公室电脑或手机访问。

## 在办公室、家里和手机上使用

需要把程序部署到一个持续在线、有持久化磁盘的服务，并提供 HTTPS 网址。
GitHub 仓库用于保存代码；GitHub Pages 不能运行这个 Python 服务或保存其数据库。
当前项目没有自动购买主机，也没有创建公开网站。

部署时：

1. 使用 `requirements.lock` 安装依赖。
2. 把 `WORKBENCH_DATA_DIR` 设置为独立的持久化目录，不能用会在重新部署时清空的临时磁盘。
3. 在主机的安全环境变量设置中设置 `WORKBENCH_PASSWORD`（至少 12 位），不要写进代码。
   设定此变量后，它会作为登录密码；修改变量并重启服务也会使旧登录失效。
   使用终端 `set-password` 管理密码时则不要设置此变量，以免重启时恢复为变量中的密码。
4. 通过 HTTPS 反向代理提供访问，设置 `WORKBENCH_SECURE_COOKIE=1`。
5. 若只允许可信反向代理访问后端，设置 `WORKBENCH_TRUST_PROXY=1`，信任它提供的一层
   `X-Forwarded-Proto`。不要让未经代理的公网请求直接到达后端端口。
6. 托管平台需要时运行 `python app.py --host 0.0.0.0`，端口读取平台 `PORT` 变量（默认 8000）。
7. 定期备份数据库，并保管好密码。可以通过页面“导出我的数据”下载明文 JSON 存档；
   JSON 导出暂不支持在界面中导入。

上线后，在各设备浏览器打开同一个 HTTPS 网址并用同一密码登录。
此版本需要联网使用，不提供离线编辑或多人协作。多台服务实例不能各用不同的 SQLite 文件；
请部署为一台服务实例并挂载同一持久化目录。

## 备份与恢复

服务运行时可以生成一致的数据库备份，输出路径必须是一个不存在的新文件：

```sh
.venv/bin/python app.py backup --output /安全的备份目录/workbench-2026-10-25.sqlite3
```

数据库备份包含密码哈希与所有内容，应妥善保管。完整恢复时先停止服务，
用备份替换数据目录中的 `workbench.sqlite3`（权限 600），再启动并检查内容。
保留 `session.key` 可继续验证已有登录；遗失该文件后会生成新密钥，重新登录即可。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js  # 可选：JavaScript 语法检查
```

可选真实浏览器检查需要 Playwright 与 Chromium。先启动一个**专用测试服务**，
它的数据目录必须含首次启动生成的 `password.txt`；不要对真实个人数据运行此检查。
测试会写入并清理以“浏览器验证：”开头的记录及“手机添加的事项”。

```sh
CHROMIUM_EXECUTABLE=/usr/bin/chromium python3 tests/browser_smoke.py
```

可通过 `WORKBENCH_TEST_URL` 指定测试服务地址、`WORKBENCH_DATA_DIR` 指定测试数据目录。
浏览器检查涵盖电脑、390px 手机、两台设备共享数据、纯文本安全显示、搜索和退出登录。
