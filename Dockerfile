FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY access/ access/
COPY engine/ engine/
COPY validator/ validator/
COPY orchestrator/ orchestrator/
COPY scripts/ scripts/
RUN chmod +x scripts/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["scripts/entrypoint.sh"]
