# 单用户密码认证设计

## 背景

象棋记谱 Web 定位为「单用户本地使用」，当前无任何认证：全部 `/api/*` 匿名可访问。若通过 `HOST=0.0.0.0` 暴露到局域网，任何人都能读写棋谱。需要一层轻量认证，单用户即可。

## 目标

- 单用户、单密码登录，无用户表、无注册。
- 通过环境变量启用；未设置时保持现状（免登录），不影响本地开发与现有测试。
- 保护全部 `/api/*`（登录/登出/会话状态/健康检查白名单除外）。
- 登录后浏览器保持会话，无需反复输入。

## 非目标

- 多用户、角色权限、注册、找回密码。
- OAuth / 第三方登录。
- 细粒度端点级权限。

## 方案选型

采用 **Flask 内置签名 session + `before_request` 全局钩子**：

- 零新增依赖（Flask 自带 session 与 `hmac`）。
- 单用户场景不需要 User 模型与 Flask-Login 的 `@login_required` 语义。
- 实现量最小，符合「快速添加」的诉求。

被否决方案：引入 Flask-Login（User 表在单用户下多余，多一个依赖）。

## 详细设计

### 配置（`backend/config.py`）

- `SECRET_KEY`：优先环境变量，缺省 `secrets.token_hex(32)` 随机生成（重启后旧会话失效，单用户可接受；设置环境变量可跨重启保持）。
- `AUTH_PASSWORD`：环境变量，未设置或空 → 认证整体禁用。
- `SESSION_COOKIE_HTTPONLY=True`、`SESSION_COOKIE_SAMESITE="Lax"`。
- `PERMANENT_SESSION_LIFETIME = 7 天`。
- `TestConfig` 显式 `AUTH_PASSWORD=None`、`SECRET_KEY="test-secret"`，隔离宿主环境变量，保证既有测试不受影响。

### 认证端点（`backend/routes/auth.py`，前缀 `/api/auth`）

| 方法 | 路径 | 行为 |
|---|---|---|
| POST | `/login` | body `{password}`；`hmac.compare_digest` 比对；成功 `session.permanent=True` 并置 `authenticated`，返回 `{ok:true}`；密码错返回 401 `{error:"密码错误"}`；认证未启用返回 400 |
| POST | `/logout` | `session.clear()`，返回 `{ok:true}` |
| GET | `/me` | 返回 `{auth_required, authenticated}`，供前端判断是否需要登录页与当前状态 |

### 全局守卫（`backend/app.py` `create_app` 内 `before_request`）

- `AUTH_PASSWORD` 为空 → 直接放行。
- 非 `/api/` 开头的请求 → 放行（静态资源与 SPA 回退）。
- 白名单：`/api/health`、`/api/auth/login`、`/api/auth/logout`、`/api/auth/me`。
- 其余 `/api/*`：`session["authenticated"]` 为真放行，否则 401 `{error:"未登录"}`。

### 前端

- `stores/auth.js`（Pinia）：`authRequired` / `authenticated` / `ready` / `loading`；`ensureReady`（只拉一次 `/me`）、`login`、`logout`、`markUnauthorized`。
- `api/index.js`：新增 `login` / `logout` / `authMe`；axios 响应拦截器与两个 NDJSON fetch 流（`analyzeStream` / `intentStream`）在收到 401 时派发自定义事件 `app-unauthorized`（避免 `api → router → store → api` 循环依赖）。
- `views/LoginView.vue`：单密码输入，提交调 `login`，失败显示「密码错误」。
- `router/index.js`：新增 `/login`；全局守卫先 `ensureReady`，认证启用且未登录 → 跳 `/login`。
- `main.js`：监听 `app-unauthorized` → `markUnauthorized` 并跳 `/login`。
- `App.vue`：`/login` 与移动端一样裸渲染（全屏无导航栏）；桌面 topnav 在认证启用且已登录时显示「退出」。

### 数据流

1. 首次加载任意受保护路由 → 守卫 `ensureReady` → `GET /api/auth/me`。
2. `auth_required=false` → 放行（免登录，现状不变）。
3. `auth_required=true` 且未登录 → 跳 `/login`。
4. 提交密码 → `POST /api/auth/login` → 成功写 session cookie → 跳 `/library`。
5. 任意请求 401（会话过期/密钥变更）→ 派发 `app-unauthorized` → 回登录页。

## 测试

- 后端 `tests/test_auth_api.py`（独立 `AuthTestConfig` fixture）：登录成功/密码错/登出、`me` 两种状态、启用时 API 401、登录后放行、白名单放行、非 API 不拦截、禁用时 API 开放。
- 前端：auth store 单测、`app-unauthorized` 派发单测。
- 回归：既有后端 508 项、前端 208 项全部通过。

## 风险

- `SECRET_KEY` 随机生成的默认值导致重启后需重新登录：可接受，README 说明设置 `SECRET_KEY` 可避免。
- 明文密码存环境变量：单用户本地场景可接受；比对用 `compare_digest` 防时序攻击。
- 无登录失败限流：本地场景暂不引入（YAGNI）。
