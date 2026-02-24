## Content Suite Backend (FastAPI)

Backend para la **App: Content Suite**. Implementa los flujos de Brand DNA, generación creativa con RAG, gobernanza de estados y auditoría multimodal. Expone API REST usada por el frontend.

### Stack rápido

- Requiere Python 3.12 o 3.13 (Render: define `runtime.txt`).
- FastAPI, SQLAlchemy 2, Pydantic Settings.
- Postgres + pgvector (RAG). Auth JWT con `python-jose`.
- IA: Groq (texto), Google GenAI (texto/visión/embeddings).
- Observabilidad: Langfuse (trazas y generations).

### Correr local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# completa claves (GROQ_API_KEY, GOOGLE_API_KEY, LANGFUSE_*) y SECRET_KEY
uvicorn app.main:app --reload --port 8000
```

- DB: usa `DATABASE_URL` (por defecto `postgresql+psycopg://postgres:postgres@localhost:5432/contentsuite`).
- Si `SEED_DEFAULT_USERS=true` se crean usuarios demo (creator/approver_a/approver_b con passwords en seed).

### Roles y workflow

- Roles (`app/db/models.py`): `creator`, `approver_a`, `approver_b`.
- Workflow (`app/services/workflow.py`): `pending_a` → `pending_b` → `approved` / `rejected`.
- Journey events: `asset_created`, `review_a_approved/rejected`, `audit_check/fail`.

### Módulos principales

- **Módulo I: Brand DNA Architect**
  - Router: `app/api/brand_manuals.py`
  - Service: `app/services/brand_manuals_service.py` (genera manual y chunks RAG con embeddings, registra en Langfuse).
  - Modelos: `BrandManual`, `BrandManualChunk`.
- **Módulo II: Creative Engine**
  - Router: `app/api/creative_assets.py` (`POST /creative-assets`).
  - Service: `app/services/creative_assets_service.py` (consulta RAG por manual, arma prompts y genera texto con Groq; registra journey `asset_created`).
  - Tipos de asset: `product_description`, `video_script`, `image_prompt`.
- **Módulo III: Governance & Multimodal Audit**
  - Router: `app/api/governance.py` (`review-a`, `audit-image`, `review-b`).
  - Service: `app/services/governance_service.py`: transición de estados, validación de roles, logging de journey. Auditoría multimodal usa Google Vision LLM con contexto del manual (RAG) y guarda `MultimodalAudit`.
- **Módulo IV: Observabilidad**
  - `app/services/observability_service.py` encapsula Langfuse traces/generations. Todos los servicios anotan input/output, contexto RAG y decisiones.

### API (resumen)

- **Auth** (`app/api/auth.py`):
  - `POST /api/v1/auth/login` → Token JWT.
  - `GET /api/v1/auth/me` → usuario actual.
- **Brand manuals** (`/api/v1/brand-manuals`):
  - `POST` (role: creator) crea manual + chunks RAG.
  - `GET` lista manuales.
- **Creative assets** (`/api/v1/creative-assets`):
  - `POST` (creator) genera asset con RAG.
  - `GET` lista por rol/estado; `GET /history` histórico + últimos auditorías; `GET /{id}/journey` trazabilidad.
- **Governance** (`/api/v1/governance`):
  - `POST /creative-assets/{id}/review-a` (approver_a) → `pending_b` o `rejected` (requiere motivo).
  - `POST /creative-assets/{id}/audit-image` (approver_b) → corre auditoría multimodal, guarda veredicto.
  - `POST /creative-assets/{id}/review-b` (approver_b) → `approved` o `rejected`.

### Datos y esquemas

- Modelos DB: ver `app/db/models.py` (roles, manuales, assets, audits, journey events).
- Schemas Pydantic: `app/schemas/*.py` (requests/responses para auth, manuals, assets, governance).

### Configuración

- Variables en `.env` (ver `.env.example`):
  - `DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `CORS_ORIGINS`.
  - IA: `GROQ_API_KEY`, `GROQ_MODEL`; `GOOGLE_API_KEY`, `GOOGLE_TEXT_MODEL`, `GOOGLE_VISION_MODEL`, `GOOGLE_EMBEDDING_MODEL`.
  - Observabilidad: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`.
  - `SEED_DEFAULT_USERS` para poblar cuentas demo. Requiere JSON en `DEMO_USERS_JSON` según `.env.example`

### Observabilidad y trazabilidad

- Cada generación/auditoría se envuelve en `observability.trace` y `observability.generation` con anotaciones de contexto RAG, prompts y resultados (Langfuse).
- Journey de assets persiste eventos en DB (`AssetJourneyEvent`) para la UI de línea de tiempo.
