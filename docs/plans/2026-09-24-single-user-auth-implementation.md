# 单用户密码认证 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为象棋记谱 Web 添加可选的单用户密码登录（环境变量启用，Session Cookie 保持登录），保护全部 `/api/*`。

**Architecture:** 后端用 Flask 内置签名 session + `before_request` 全局钩子，`AUTH_PASSWORD` 未设置时认证整体禁用；新建 `/api/auth/{login,logout,me}` 蓝图。前端新增 auth store、登录页、路由守卫，axios/fetch 收到 401 统一派发 `app-unauthorized` 事件跳登录页（自定义事件避免 `api→router→store→api` 循环依赖）。

**Tech Stack:** Flask 3 session、hmac.compare_digest；Vue 3 + Pinia + vue-router；pytest + vitest。零新增依赖。

**设计决策：** 详见 `docs/plans/2026-09-24-single-user-auth-design.md`。

**已知工作区状态：** 存在未提交的移动端改动，所有 `git add` 均按文件精确 stage，禁止 `git add -A` / `git add .`。

---

### Task 0: 落盘设计文档与本计划

**Files:**
- Create: `docs/plans/2026-09-24-single-user-auth-design.md`
- Create: `docs/plans/2026-09-24-single-user-auth-implementation.md`

**Step 1:** 将设计写入设计文档；本计划全文写入实现计划文档。

**Step 2: Commit**

```bash
git add docs/plans/2026-09-24-single-user-auth-design.md docs/plans/2026-09-24-single-user-auth-implementation.md
git commit -m "docs: 单用户密码认证设计与实现计划"
```

---

### Task 1: 后端配置（SECRET_KEY / AUTH_PASSWORD）

**Files:**
- Modify: `backend/config.py`

**Step 1: 写配置**

```python
import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "chess.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD") or None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 7 * 24 * 3600


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    SECRET_KEY = "test-secret"
    AUTH_PASSWORD = None  # 显式关闭，隔离宿主环境变量
```

**Step 2: 验证**

Run: `cd backend && .venv/bin/python -c "from config import Config, TestConfig; assert TestConfig.AUTH_PASSWORD is None; print('ok')"`
Expected: `ok`

**Step 3: Commit** — `git add backend/config.py && git commit -m "feat(backend): 认证相关配置项（SECRET_KEY/AUTH_PASSWORD/会话）"`

---

### Task 2: auth 蓝图（login / logout / me）

**Files:**
- Create: `backend/routes/auth.py`
- Modify: `backend/app.py`（注册蓝图）
- Test: `backend/tests/test_auth_api.py`

**Step 1: 写失败测试**

```python
import pytest

from app import create_app
from config import TestConfig
from models import db


class AuthTestConfig(TestConfig):
    AUTH_PASSWORD = "s3cret"
    SECRET_KEY = "auth-test-secret"


@pytest.fixture
def auth_app():
    app = create_app(AuthTestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


def test_login_success_and_me(auth_client):
    resp = auth_client.post("/api/auth/login", json={"password": "s3cret"})
    assert resp.status_code == 200
    me = auth_client.get("/api/auth/me").get_json()
    assert me == {"auth_required": True, "authenticated": True}


def test_login_wrong_password(auth_client):
    resp = auth_client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 401
    me = auth_client.get("/api/auth/me").get_json()
    assert me["authenticated"] is False


def test_me_when_auth_disabled(client):
    me = client.get("/api/auth/me").get_json()
    assert me == {"auth_required": False, "authenticated": False}


def test_logout_clears_session(auth_client):
    auth_client.post("/api/auth/login", json={"password": "s3cret"})
    assert auth_client.post("/api/auth/logout").status_code == 200
    me = auth_client.get("/api/auth/me").get_json()
    assert me["authenticated"] is False
```

**Step 2: 运行确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_api.py -v`
Expected: FAIL（无 `/api/auth` 路由）

**Step 3: 实现 `backend/routes/auth.py`**

```python
import hmac

from flask import Blueprint, current_app, jsonify, request, session

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    password = current_app.config.get("AUTH_PASSWORD")
    if not password:
        return jsonify({"error": "认证未启用"}), 400
    data = request.get_json(silent=True) or {}
    candidate = data.get("password", "")
    if not isinstance(candidate, str) or not hmac.compare_digest(candidate, password):
        return jsonify({"error": "密码错误"}), 401
    session.permanent = True
    session["authenticated"] = True
    return jsonify({"ok": True})


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.get("/me")
def me():
    password = current_app.config.get("AUTH_PASSWORD")
    return jsonify(
        {
            "auth_required": bool(password),
            "authenticated": bool(password) and bool(session.get("authenticated")),
        }
    )
```

`backend/app.py` 蓝图注册处加 `from routes.auth import auth_bp` 与 `app.register_blueprint(auth_bp, url_prefix="/api/auth")`。

**Step 4: 运行确认通过** — 4 passed

**Step 5: Commit** — `git add backend/routes/auth.py backend/app.py backend/tests/test_auth_api.py && git commit -m "feat(api): 登录/登出/会话状态端点"`

---

### Task 3: before_request 全局 API 守卫

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_auth_api.py`

**Step 1: 写失败测试**（追加）

```python
def test_api_requires_login_when_enabled(auth_client):
    assert auth_client.get("/api/games").status_code == 401
    assert auth_client.get("/api/stats").status_code == 401


def test_login_grants_api_access(auth_client):
    auth_client.post("/api/auth/login", json={"password": "s3cret"})
    assert auth_client.get("/api/stats").status_code == 200


def test_health_and_auth_endpoints_whitelisted(auth_client):
    assert auth_client.get("/api/health").status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 200
    assert auth_client.post("/api/auth/logout").status_code == 200


def test_non_api_paths_not_blocked(auth_client):
    assert auth_client.get("/some/spa/path").status_code != 401


def test_auth_disabled_apis_open(client):
    assert client.get("/api/stats").status_code == 200
```

**Step 2: 运行确认失败**

**Step 3: 实现钩子**（`create_app` 内）

```python
    from flask import request, session as flask_session

    public_api_paths = {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/me"}

    @app.before_request
    def _require_auth():
        if not app.config.get("AUTH_PASSWORD"):
            return None
        path = request.path
        if not path.startswith("/api/") or path in public_api_paths:
            return None
        if flask_session.get("authenticated"):
            return None
        return jsonify({"error": "未登录"}), 401
```

文件头 import 补 `request`。

**Step 4: 运行确认通过** — 9 passed

**Step 5: Commit** — `git add backend/app.py backend/tests/test_auth_api.py && git commit -m "feat(api): before_request 全局保护 /api/*（白名单放行）"`

---

### Task 4: 后端全量回归

**Step 1: Run** `cd backend && .venv/bin/python -m pytest -q`
**Expected:** 全绿（原 508 项 + 新增 9 项）。

---

### Task 5: 前端 api 层（auth 方法 + 401 统一处理）

**Files:**
- Modify: `frontend/src/api/index.js`
- Test: `frontend/src/api/__tests__/auth.test.js`

**Step 1: 写失败测试**

```javascript
import { beforeEach, describe, expect, it, vi } from "vitest";
import { analyzeStream } from "../index";

function mockFetchStatus(status) {
  global.fetch = vi.fn(async () => ({
    ok: status === 200,
    status,
    body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
  }));
}

describe("401 统一处理", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("analyzeStream 收到 401 派发 app-unauthorized", async () => {
    mockFetchStatus(401);
    const onUnauthorized = vi.fn();
    window.addEventListener("app-unauthorized", onUnauthorized);
    await analyzeStream({ fen: "x" }, { onError: () => {} });
    expect(onUnauthorized).toHaveBeenCalled();
    window.removeEventListener("app-unauthorized", onUnauthorized);
  });
});
```

**Step 2: 确认失败**

**Step 3: 实现**：顶部加 `notifyUnauthorized()`；axios 拦截器 401（且非 `/auth/`）分支派发事件；两个 fetch 流 401 分支派发；`api` 对象加 `login` / `logout` / `authMe`。

**Step 4: 确认通过**

**Step 5: Commit** — `git add frontend/src/api/index.js frontend/src/api/__tests__/auth.test.js && git commit -m "feat(frontend): auth API 与 401 统一未授权事件"`

---

### Task 6: auth store

**Files:**
- Create: `frontend/src/stores/auth.js`
- Test: `frontend/src/stores/__tests__/auth.test.js`

**Step 1: 写失败测试**

```javascript
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "../auth";
import { api } from "../../api";

vi.mock("../../api", () => ({
  api: { login: vi.fn(), logout: vi.fn(), authMe: vi.fn() },
}));

describe("auth store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());
  });

  it("ensureReady 只拉一次 me", async () => {
    api.authMe.mockResolvedValue({ auth_required: true, authenticated: false });
    const store = useAuthStore();
    await store.ensureReady();
    await store.ensureReady();
    expect(api.authMe).toHaveBeenCalledTimes(1);
    expect(store.authRequired).toBe(true);
  });

  it("login 成功置位，失败保持未登录", async () => {
    api.login.mockResolvedValueOnce({ ok: true });
    const store = useAuthStore();
    await store.login("pw");
    expect(store.authenticated).toBe(true);
    api.login.mockRejectedValueOnce(new Error("密码错误"));
    await expect(store.login("bad")).rejects.toThrow();
    expect(store.authenticated).toBe(false);
  });

  it("logout 复位", async () => {
    api.logout.mockResolvedValue({ ok: true });
    const store = useAuthStore();
    store.authenticated = true;
    await store.logout();
    expect(store.authenticated).toBe(false);
  });
});
```

**Step 2: 确认失败**

**Step 3: 实现 `frontend/src/stores/auth.js`**

```javascript
import { defineStore } from "pinia";
import { api } from "../api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    authRequired: false,
    authenticated: false,
    ready: false,
    loading: false,
  }),
  actions: {
    async fetchMe() {
      const data = await api.authMe();
      this.authRequired = data.auth_required;
      this.authenticated = data.authenticated;
      this.ready = true;
    },
    async ensureReady() {
      if (!this.ready) await this.fetchMe();
    },
    async login(password) {
      this.loading = true;
      try {
        await api.login(password);
        this.authenticated = true;
      } finally {
        this.loading = false;
      }
    },
    async logout() {
      await api.logout();
      this.authenticated = false;
    },
    markUnauthorized() {
      this.authenticated = false;
    },
  },
});
```

**Step 4: 确认通过**

**Step 5: Commit** — `git add frontend/src/stores/auth.js frontend/src/stores/__tests__/auth.test.js && git commit -m "feat(frontend): auth Pinia store"`

---

### Task 7: 登录页 + 路由守卫 + 401 监听

**Files:**
- Create: `frontend/src/views/LoginView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/main.js`

**Step 1: 实现 `LoginView.vue`**（全屏居中，`data-test` 选择器）

**Step 2: 路由守卫**：新增 `/login` 路由；`beforeEach` 先 `ensureReady`，认证启用且未登录 → `/login`。

**Step 3: `main.js`**：`app-unauthorized` → `markUnauthorized` + 跳 `/login`。

**Step 4: 手动验证**（后端 `AUTH_PASSWORD=dev`，前端 dev）。

**Step 5: Commit** — `git add frontend/src/views/LoginView.vue frontend/src/router/index.js frontend/src/main.js && git commit -m "feat(frontend): 登录页、路由守卫与 401 跳转"`

---

### Task 8: App.vue 集成（全屏登录 + 退出按钮）

**Files:**
- Modify: `frontend/src/App.vue`

**Step 1:** 裸渲染条件加 `route.path === "/login"`。
**Step 2:** topnav 加「退出」按钮（`authRequired && authenticated`）。
**Step 3:** 冒烟验证。
**Step 4: Commit** — `git add frontend/src/App.vue && git commit -m "feat(frontend): 导航栏退出登录与登录页全屏渲染"`

---

### Task 9: 配置样例与 README

**Files:**
- Create: `.env.example`
- Modify: `README.md`

**Step 1: `.env.example`** 含 `AUTH_PASSWORD` / `SECRET_KEY` 说明。
**Step 2: README** 启动节、API 一览表加 auth 三行、已知限制「单用户、无登录」改为「可选密码登录」、设计文档列表追加。
**Step 3: Commit** — `git add .env.example README.md && git commit -m "docs: 认证配置说明与 API 文档"`

---

### Task 10: 全量验证

**Step 1:** 后端 `pytest -q` 全绿。
**Step 2:** 前端 `npx vitest run` 全绿。
**Step 3:** `npm run build` 成功。
**Step 4:** 生产模式 curl 联测（未登录 401 / 登录 200 / 带 cookie 200）。
**Step 5:** 确认 `git status` 未混入移动端未提交改动。
