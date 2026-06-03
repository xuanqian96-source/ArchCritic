# ArchCritic 前端 V1 独立复刻

本目录是依据 Figma“前端 V1”制作的新版 React 前端。它连接现有 FastAPI 后端，但不会修改原来的 `frontend` 目录。

使用 React、TypeScript 和 Tailwind CSS。设计画布固定为 `1536×820`，浏览器窗口变化时会整体等比缩放。

## 本地预览

```bash
cd /mnt/e/claude/论文/ArchCritic/frontend-v1-replica
npm run dev
```

打开 `http://localhost:4173`。如果端口已占用，Vite 会在终端显示实际使用的下一个端口。

后端需同时运行：

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 构建部署文件

```bash
npm run build
```

构建完成后，将 `dist` 目录作为普通静态网页部署即可。

## 基础检查

```bash
npm run typecheck
npm test
```

生产构建完成后，可直接将 `dist` 目录部署为静态网站，并让浏览器可以访问后端 `8000` 端口。
