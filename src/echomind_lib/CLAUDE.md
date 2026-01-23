# echomind_lib - Shared Library

This is the **single source of shared code** for all EchoMind services.

## Structure

```
echomind_lib/
├── db/                      # Database access
│   ├── models/              # SQLAlchemy ORM models (one file per entity)
│   │   ├── __init__.py      # Re-exports all models
│   │   ├── base.py          # Shared Base, column types
│   │   ├── user.py
│   │   ├── assistant.py
│   │   └── ...
│   ├── postgres.py          # CRUD operations
│   ├── qdrant.py            # Vector DB operations
│   ├── nats_subscriber.py   # JetStream consumer
│   └── nats_publisher.py    # JetStream publisher
├── helpers/                 # Utility code
│   ├── minio_helper.py      # S3/MinIO operations
│   ├── device_checker.py    # GPU/CPU detection
│   └── readiness_probe.py   # K8s health checks
└── models/                  # AUTO-GENERATED (READ-ONLY)
    ├── public/              # API models from proto
    └── internal/            # NATS message models from proto
```

## Rules

1. **ALL shared code goes here** - Never duplicate across services
2. **`models/` is READ-ONLY** - Generated from proto, never edit
3. **One ORM model per file** in `db/models/`
4. **Use `TYPE_CHECKING`** for forward references to avoid circular imports

## Import Patterns

```python
# Database
from echomind_lib.db.models import User, Assistant, Document
from echomind_lib.db.postgres import DocumentCRUD, ConnectorCRUD
from echomind_lib.db.qdrant import QdrantDB
from echomind_lib.db.nats_subscriber import JetStreamEventSubscriber
from echomind_lib.db.nats_publisher import JetStreamPublisher

# Helpers
from echomind_lib.helpers.readiness_probe import ReadinessProbe
from echomind_lib.helpers.minio_helper import MinIOHelper
from echomind_lib.helpers.device_checker import DeviceChecker

# Generated models (read-only)
from echomind_lib.models import SemanticData
from echomind_lib.models.public import User as UserRead
```

## Adding New Code

- **New helper?** → `helpers/{name}_helper.py`
- **New DB model?** → `db/models/{entity}.py` + export in `__init__.py`
- **New CRUD?** → Add to `db/postgres.py`
- **New API model?** → Edit proto, run `make gen-proto` (never hand-write)