# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY service/ service/

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /app /app
ENV PYTHONUNBUFFERED=1
EXPOSE 8081
CMD ["uv", "run", "service/engine_api/app.py"]
