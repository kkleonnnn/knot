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
COPY --from=frontend-builder /app/bi_agent/static ./bi_agent/static
RUN mkdir -p bi_agent/data
EXPOSE 8000
CMD ["uvicorn", "bi_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
