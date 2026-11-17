# Full existing FastAPI + built React runtime; no credentials or business calls during build.
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY webapp/web/package*.json ./
RUN npm ci
COPY webapp/web/ ./
RUN npm run build
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /frontend/dist ./webapp/web/dist
ENV DATAE_MODE=demo PYTHON_DOTENV_DISABLED=1
EXPOSE 8600
CMD ["python", "-m", "uvicorn", "webapp.api.main:app", "--host", "0.0.0.0", "--port", "8600"]
