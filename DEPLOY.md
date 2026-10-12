# 钱来钱往记账 · 部署手册

前端是 hash 路由（`/#/family` 这种带 `#` 的地址）、接口走相对路径 `/api/v1`，两者同源。
**这带来两个便利**：不存在跨域问题（CORS 只在分域名时才需要配），服务端也不需要 history fallback，任意静态托管都能跑。

---

## 一、三种跑法，按需选

| 路线 | 谁能访问 | 用时 | 适合 |
|---|---|---|---|
| A 内网单端口 | 同一内网的设备 | 5 分钟 | 自己先跑通手感 |
| B 内网 + 隧道 | 任何能上网的人 | 10 分钟 | 让家人先真用两周 |
| C 云服务器 compose | 固定域名，长期 | 40 分钟 | 正式使用 |

---

## 二、路线 A：内网单端口（零 Docker）

Django 同时发接口与前端产物，一个端口搞定。

```bash
# 1. 构建前端
cd frontend && npm install && npm run build && cd ..

# 2. 配置后端（backend/.env）
#    DEBUG=False
#    ALLOWED_HOSTS=*
#    SERVE_WEB=True          ← 打开单端口托管
#    WEB_DIST=../frontend/dist

# 3. 起服务（0.0.0.0 才能被手机访问；本机跑 runserver 只监听 127.0.0.1）
cd backend
python manage.py migrate
python manage.py runserver 0.0.0.0:8001 --noreload
```

手机浏览器打开 `http://<你的内网IP>:8001`。

**不通的两个常见原因**：公司 WiFi 开了客户端隔离（设备之间不通）；或者你用的是 `npm run dev`（vite 默认只监听 `127.0.0.1`，要加 `--host 0.0.0.0`）。

---

## 三、路线 B：内网 + cloudflared 隧道

在路线 A 跑通的基础上加一条命令，得到一个公网 HTTPS 地址，微信发给家人即可打开。

```bash
# 下载地址：https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:8001
```

输出形如 `https://xxxx.trycloudflare.com`，全程 HTTPS、不用域名证书备案。
**缺点**：进程一停地址就失效，重启会换地址；速度取决于线路。试用期够用，长期用走路线 C。

> 隧道指向 8001（Django 单端口）即可 —— 同源，不会有跨域问题。

---

## 四、路线 C：云服务器（正式）

### 依赖装在哪（先看这个，免得找错地方）

| 东西 | 装在哪 | 谁触发 |
|---|---|---|
| 服务器操作系统 | **只需要 Docker**，不用装 Python / Node / MySQL / Redis | `install.sh`（没 Docker 时用官方脚本装） |
| 后端 Python 依赖 | `python:3.12-slim` 镜像里，`pip install -r backend/requirements.txt` | `docker compose build`（Dockerfile） |
| 前端依赖 | **从不上服务器** —— `node_modules` 不进仓库，`frontend/dist` 随仓库提交 | 本机 `npm run build` |
| MySQL / Redis / nginx | 各自官方镜像，参数写在 `docker-compose.yml` | `install.sh` → `compose up -d` |
| 运行配置（SECRET_KEY、库密码、域名） | `deploy/.env`，不进仓库，权限 600 | `install.sh` 自动生成；已存在则不覆盖 |
| 建表 / 收静态 / 注册定时任务 | 容器内 | `entrypoint.sh`：migrate → collectstatic → setup_schedules |

公司内网或国内节点要留意两个下载源：PyPI（`.env` 里放开 `PIP_INDEX_URL`）和 Docker Hub（`/etc/docker/daemon.json` 的 `registry-mirrors`）。拉不动时 `install.sh` 会把这两条排查项直接打在错误里。

### 0. 首次上线（GitLab 路线，推荐）

公司服务器走跳板机，代码统一走 GitLab；**服务器上不装 Node**，前端 `dist` 随仓库提交。

**一次性准备**

1. 公司 GitLab 建**私有**仓库（家里账本别设成 internal/public），本机推送：

```bash
cd E:\Source\family-ledger
git init
git remote add origin git@gitlab.company.com:<group>/family-ledger.git
git add . && git commit -m 'init'
git push -u origin main
```

2. GitLab → Settings → Repository → **Deploy Keys**：把服务器上 `ssh-keygen -t ed25519` 生成的公钥加进去（**别勾写权限**）。这样服务器 `git pull` 不用带个人账号密码。

3. 服务器（跳板机进去后）：

```bash
git clone git@gitlab.company.com:<group>/family-ledger.git /opt/family-ledger
bash /opt/family-ledger/deploy/install.sh                    # 自动探测公网 IP
# bash /opt/family-ledger/deploy/install.sh your.domain.com  # 有域名就传进来
```

`install.sh` 依次做完：装 Docker（没有的话）→ 生成 `deploy/.env`（`SECRET_KEY` 与数据库密码随机生成，公网 IP 自动写进 `ALLOWED_HOSTS`）→ 构建启动五个容器 → 健康检查 → 挂每日 3 点备份。**已存在的 `.env` 不会被覆盖**（密码一换，web 就连不上已初始化的库）。

### 1. 日常发版

```powershell
# 本机：改完代码后，前端必须重新构建并一起提交
cd E:\Source\family-ledger\frontend
npm run build
cd ..
git add . && git commit -m '说明改了啥' && git push
```

```bash
# 服务器
bash /opt/family-ledger/deploy/update.sh
```

`update.sh` = `git pull` + 重建后端镜像 + 自动建表 + 健康检查。前端 `dist` 由 nginx 直接挂载，pull 完刷新页面即生效。

> **别忘**：`frontend/dist` 故意没被 `.gitignore` 忽略 —— 服务器不装 Node 就靠它。只改后端时也要 `git add .`，否则会推上去一个旧前端。

### 2. 手工路线（不跑脚本时照这个做）

```bash
git clone git@gitlab.company.com:<group>/family-ledger.git /opt/family-ledger && cd /opt/family-ledger
cd deploy && cp env.production.example .env
vi .env          # SECRET_KEY / DB_PASSWORD / DB_ROOT_PASSWORD / ALLOWED_HOSTS 必改
openssl rand -base64 64     # 生成 SECRET_KEY

cd /opt/family-ledger/deploy
docker compose up -d --build
docker compose ps           # 五个服务都应 Up
curl -i http://127.0.0.1/api/v1/core/health/   # 健康检查
```

浏览器打开 `http://<服务器IP>` 即可。服务器上不用 `npm install` —— `frontend/dist` 已随仓库拉下来。

> 备用：服务器连不上 GitLab 时，用本机 `deploy\pack.ps1` 打包，再 `scp -o ProxyJump=跳板机 包 root@目标机:/opt/` 传过去解压。

### 3. HTTPS

- **境外节点（香港/新加坡）免备案**：用 certbot 或云厂商免费证书，把 `nginx.conf` 里注释掉的 443 server 段启用，证书放 `deploy/certs/`。
- **国内节点**：需先备案域名（1~2 周），再把 `server_name` 换成你的域名后申请证书。
- 有了 HTTPS 后，把 `.env` 的 `CSRF_TRUSTED_ORIGINS` 改成 `https://你的域名`。

### 4. 备份

```bash
chmod +x deploy/backup.sh
# 每天凌晨 3 点
echo "0 3 * * * /opt/family-ledger/deploy/backup.sh >> /var/log/fl-backup.log 2>&1" | crontab -
```

默认存 `/var/backups/family-ledger`，保留 30 天。恢复命令写在脚本头部注释里。

### 5. 发版

```bash
cd /opt/family-ledger
git pull
cd frontend && npm run build && cd ..
cd deploy && docker compose up -d --build      # web/queue 重建，nginx 挂载的 dist 直接生效
```

### 6. 运维速查

```bash
docker compose logs -f web        # 看日志
docker compose exec web python manage.py migrate        # 手动迁表
docker compose exec web python manage.py snapshot_accounts   # 手动补一次资产快照
docker compose exec web python manage.py setup_schedules     # 注册定时任务（幂等，启动时已自动跑）
docker compose logs -f queue                                 # 看异步任务（账单解析、每日快照）
docker compose exec web python manage.py createsuperuser      # 建 admin 账号
```

---

## 五、上线前必做清单（逐项核对）

- [ ] `.env` 里 `DEBUG=False` —— 否则 500 错误页会把 SQL 和配置摊开
- [ ] `SECRET_KEY` 已换成 `openssl rand -base64 64` 的随机值 —— 泄露等于任何人可伪造 JWT 读你家账本
- [ ] `ALLOWED_HOSTS` 填真实域名/IP，不要留 `*`
- [ ] 上面几项没配好时**服务会拒绝启动**并打印原因（`SECRET_KEY`/`ALLOWED_HOSTS`/SQLite 三条闸门）——不是坏了，按提示改完再起
- [ ] **删除演示账号** `13800138000` / `13800138001`（密码 `test123456`），或至少改成强密码
  ```bash
  docker compose exec web python manage.py shell -c "
  from apps.users.models import User
  User.objects.filter(username__in=['13800138000','13800138001']).delete()"
  ```
  > 注意：删之前先注册好你和家人的真实手机号账号，并把主账号转到真账号上
- [ ] **清掉测试借款**：去「借钱来往」页把 `¥50,000` 那条测试借出删掉（它会扣减关联账户余额）
- [ ] 限制 `/django-admin`（在 `nginx.conf` 里给 `location /admin/` 加 `allow 你的IP; deny all;`，不用就注释掉 Django admin 路由）
- [ ] `AISettings.api_key` 目前明文存库；不接 AI 就别填，填了注意别把库泄露
- [ ] 备份定时任务已挂，并且**恢复过一次**（没验证过的备份不算备份）
- [ ] `deploy/.env` 只存在于服务器上：`git status` 里看不到它（仓库根已有 `.gitignore` 兜底，但如果之前误提交过，密钥要当作已泄露重新生成）

---

## 六、已知限制（不是 bug，是当前能力边界）

1. **没有系统推送**：H5 在 iOS 上拿不到推送通道，「我的 → 推送设置」如实标注为「未接入」。现在能拿到的提醒是记账后的即时提示（超过「事后知会 / 事前申请」阈值时）。要真推送，路径是补微信小程序走订阅消息。
2. **微信内置浏览器的两个坑**：导入账单的文件选择、导出 CSV 的下载在微信内常被拦 —— **用系统浏览器做导入/导出**。
3. **刷新才同步**：没有 WebSocket，对方改完你重进页面就是新的，但不会主动刷新当前页。
4. **登录有效期**：access token 2 小时，但前端会在 401 时用 refresh token 静默续期（失败才跳登录），所以**30 天内不操作也不会被踢**；换设备、清浏览器数据、或连续 30 天没打开才会要求重新登录。

---

## 七、项目自带的单端口能力

`SERVE_WEB=1` 时 Django 直接吐 `dist`：

- `GET /` → `index.html`（未构建时返回 503 + 中文提示，不抛 500）
- `GET /manifest.webmanifest` → 正确的 `application/manifest+json`（否则 Chrome 不认 PWA）
- `GET /assets/*`、`/icons/*` → 静态文件，含 `..` 的路径一律 400

生产仍建议 `SERVE_WEB=0` 让 nginx 发静态（缓存策略与 gzip 更完整）。
