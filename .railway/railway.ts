import { defineRailway, preserve, project, service } from "railway/iac";

// Own only this repository's services. Worker, databases and volumes belong elsewhere.
export const partial = "tracelab";

export default defineRailway((ctx) => {
  if (ctx.projectId !== "4e3adf39-f05e-48f8-8c7c-f2f27621b484" ||
      ctx.environmentId !== "4fb80245-6762-4438-ab94-6993c3568a92") {
    throw new Error("This configuration targets TraceLab production only.");
  }
  const api = service("TraceLab", {
    domains: [{ domain: "api.tracelab.aquex.ai", port: 8080 }],
    "source": {
        "type": "github",
        "branch": "main",
        "checkSuites": false,
        "repo": "kneelinghorse/TraceLab"
    },
    "build": {
        "buildEnvironment": "V3",
        "builder": "DOCKERFILE",
        "dockerfilePath": "/Dockerfile"
    },
    "deploy": {
        "ipv6EgressEnabled": false,
        "multiRegionConfig": {
            "us-east4-eqdc4a": {
                "numReplicas": 1
            }
        },
        "runtime": "V2",
        "startCommand": "bash -lc \"alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT\"",
        "useLegacyStacker": false
    },
    "networking": {
        "privateNetworkEndpoint": "tracelab",
        "serviceDomains": {
            "tracelab-production.up.railway.app": {}
        }
    },
    env: {
      "AUTH_PASSWORD": preserve(),
      "AUTH_PASSWORD_HASH ": preserve(),
      "AUTH_USERNAME": preserve(),
      "CORS_ALLOWED_ORIGINS_PROD": preserve(),
      "DATABASE_URL": preserve(),
      "DEBUG": preserve(),
      "DEEPSEARCH_MODE": preserve(),
      "DEEPSEARCH_TRACELAB_SERVICE_SECRET": preserve(),
      "DEEPSEARCH_WORKER_HEALTH_URL": preserve(),
      "ENVIRONMENT": preserve(),
      "FRONTEND_URL": preserve(),
      "ONBOARDING_INGEST_ROOT": preserve(),
      "OPENAI_API_KEY": preserve(),
      "OPENAI_CHAT_MODEL": preserve(),
      "OPENAI_CHAT_TEMPERATURE": preserve(),
      "OPENAI_EMBEDDING_DIMENSION": preserve(),
      "OPENAI_EMBEDDING_MODEL": preserve(),
      "OPENAI_ESCALATION_MODEL": preserve(),
      "QDRANT_API_KEY": preserve(),
      "QDRANT_COLLECTION_NAME": preserve(),
      "QDRANT_URL": preserve(),
      "QDRANT__LOG_LEVEL": preserve(),
      "QDRANT__SERVICE__API_KEY": preserve(),
      "QDRANT__STORAGE__PATH": preserve(),
      "RAG_DEFAULT_MAX_TOKENS": preserve(),
      "RBAC_ENABLED": preserve(),
      "RESEND_API_KEY": preserve(),
      "RESEND_FROM_ADDRESS": preserve(),
      "RESEND_INBOUND_API_KEY": preserve(),
      "RESEND_WEBHOOK_SECRET": preserve(),
      "SECRET_KEY": preserve(),
      "SUPPORT_FORWARD_TO": preserve(),
      "TRACELAB_DEEPSEARCH_SERVICE_SECRET": preserve(),
    },
  });
  const web = service("frontend", {
    root: "/frontend",
    domains: [{ domain: "namozine.com", port: 8080 }, { domain: "tracelab.aquex.ai", port: 8080 }],
    "source": {
        "type": "github",
        "branch": "main",
        "checkSuites": false,
        "repo": "kneelinghorse/TraceLab"
    },
    "build": {
        "buildCommand": "npm install && npm run build",
        "buildEnvironment": "V3",
        "builder": "NIXPACKS"
    },
    "deploy": {
        "healthcheckPath": "/admin/users",
        "healthcheckTimeout": 30,
        "ipv6EgressEnabled": false,
        "multiRegionConfig": {
            "us-east4-eqdc4a": {
                "numReplicas": 1
            }
        },
        "runtime": "V2",
        "startCommand": "npm run start -- -H 0.0.0.0 -p $PORT",
        "useLegacyStacker": false
    },
    "networking": {
        "serviceDomains": {
            "frontend-production-43c3.up.railway.app": {
                "port": 8080
            }
        }
    },
    env: {
      "NEXT_PUBLIC_API_BASE_URL": preserve(),
      "NEXT_PUBLIC_API_PATH_PREFIX": preserve(),
      "NEXT_PUBLIC_DEFAULT_PROJECT_ID": preserve(),
      "NEXT_TELEMETRY_DISABLED": preserve(),
      "NODE_ENV": preserve(),
      "PLAYWRIGHT_API_BASE_URL": preserve(),
    },
  });
  return project("TraceLab", { resources: [api, web] });
});
