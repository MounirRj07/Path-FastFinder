# Image du backend Path-FastFinder
# Construction : docker build -t path-fastfinder-api --build-arg GRAPH_URL=<url du zip> backend
# Lancement    : docker run -p 8000:8000 --env-file .env path-fastfinder-api

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl unzip \
 && rm -rf /var/lib/apt/lists/*

# Dependances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Le graphe n'est pas dans Git : on le telecharge depuis la release GitHub
ARG GRAPH_URL=https://github.com/Mounir07-yo/Path-FastFinder/releases/download/graph-v1/graph-v1.zip
RUN mkdir -p /data/graph \
 && curl -fsSL "$GRAPH_URL" -o /tmp/graph.zip \
 && unzip -q /tmp/graph.zip -d /data/graph \
 && rm /tmp/graph.zip \
 && test -f /data/graph/meta.json

ENV GRAPH_PATH=/data/graph
EXPOSE 8000

# Un seul processus : les penalites sont gardees en memoire dans ce processus
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
