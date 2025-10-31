# Qdrant Infrastructure Bootstrap

This directory contains the infrastructure assets required to stand up Qdrant locally and on [Railway](https://railway.app) so the embedding pipeline (Mission B1.5) has a consistent vector store target.

## Local Development

1. Ensure Docker Desktop is running.
2. Start the stack:
   ```bash
   docker compose up qdrant -d
   ```
   or boot the entire application:
   ```bash
   docker compose up --build
   ```
3. Qdrant will be reachable at `http://localhost:6333`. The container is configured for on-disk payload storage and tuned for write-optimized imports by default.

## Railway Deployment

Railway supports declarative setup through the `railway.template.json` file in this directory. The template provisions a Qdrant service with the storage options required for our cost/performance profile.

### Usage

1. Install the Railway CLI (`npm i -g @railway/cli`) and authenticate (`railway login`).
2. Target the TraceLab project:
   ```bash
   railway use <project-id>
   ```
3. Provision Qdrant using the template:
   ```bash
   railway up --service-template infra/qdrant/railway.template.json
   ```
4. Capture the generated `QDRANT_URL` and `QDRANT_API_KEY` from Railway and place them in your `.env` or deployment secrets so the application and CLI tooling can connect.

The template mirrors the local configuration—payloads on disk, scalar quantization enabled post-ingest, and conservative logging to keep Railway costs predictable.
