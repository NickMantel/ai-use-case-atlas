FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

# EXTRAS="databricks-sdk" or "google-cloud-bigquery google-auth" etc.
ARG EXTRAS=""
COPY requirements.txt .
RUN pip install -r requirements.txt && if [ -n "$EXTRAS" ]; then pip install $EXTRAS; fi

COPY app ./app
COPY frameworks ./frameworks
COPY data/demo_catalog.yaml ./data/demo_catalog.yaml
COPY run.py .

RUN useradd --create-home atlas && chown -R atlas /srv
USER atlas
EXPOSE 8000
CMD ["python", "run.py"]
