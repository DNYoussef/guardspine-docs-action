FROM python:3.12-slim AS builder
WORKDIR /staging
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/staging/deps -r requirements.txt
COPY . /staging/app

FROM python:3.12-slim
COPY --from=builder /staging/deps /usr/local/lib/python3.12/site-packages/
COPY --from=builder /staging/app /app
WORKDIR /app
ENTRYPOINT ["python", "/app/entrypoint.py"]
