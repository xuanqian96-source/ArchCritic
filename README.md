# ArchCritic

基于多Agent协作与RAG知识增强的建筑设计课评图辅助系统。

## 开发环境

- Python 3.10+
- Node.js 20+
- SQLite

## 快速启动

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # 填入 API key
uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev
```
