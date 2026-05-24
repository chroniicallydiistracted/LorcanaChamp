# LorcanaChamp Rules Kernel v2 Scaffold

This archive contains a standalone v2 kernel scaffold for LorcanaChamp.

## Install / apply

From the LorcanaChamp repo root, copy or extract these paths into the repo:

```text
lorcana_engine_v2/
tests/v2/
docs/architecture/
```

## Run

```bash
python3 -m pytest tests/v2 -q
```

## Design rule

The package is intentionally independent from legacy `lorcana_bot` runtime code.
The current v1 engine may be used as human reference only. Lorcanito remains the
source of truth for v2 architecture and behavior.
