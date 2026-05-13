# Stage 1: Build frontend
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# v0.6.0 R-PA-7.1/7.2 显式守护（守护者 M-2 立约）—
#   prompts 启动期 seed 守护对象 + catalog template fallback 第 3 级守护对象
#   显式 COPY 即使未来改 COPY 策略（多阶段构建 / .dockerignore 加新规则）也不会漏
COPY knot/prompts/ /app/knot/prompts/
COPY knot/services/agents/_template_catalog.py /app/knot/services/agents/_template_catalog.py
COPY --from=frontend-builder /knot/static ./knot/static
RUN mkdir -p knot/data
EXPOSE 8000
CMD ["uvicorn", "knot.main:app", "--host", "0.0.0.0", "--port", "8000"]
