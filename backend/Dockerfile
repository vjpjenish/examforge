FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
EXPOSE 8000
# Shell form so $PORT expands: hosts like Render assign the port at runtime.
# Falls back to 8000, which is what docker-compose.yml maps.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
