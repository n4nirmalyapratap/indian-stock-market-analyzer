---
name: Python package install location (.pythonlibs)
description: How to install Python packages in this repl — installLanguagePackages/uv fails on the immutable nix store.
---

# Installing Python packages in this repl

`installLanguagePackages({language:"python",...})` (uv) and `pip install` (no flags)
both fail with "Permission denied / immutable /nix/store" because they target the
read-only nix store python.

**Install instead into the writable project libs dir** (where all backend deps like
`psycopg`, `uvicorn` already live):

```
python3.11 -m pip install --target .pythonlibs/lib/python3.11/site-packages "<pkg>"
```

`.pythonlibs/...` is already on `sys.path` via the sitecustomize PYTHONPATH, so the
package is importable immediately (verify with `python3.11 -c "import <mod>"`).

**Why:** the nix store is immutable; only `.pythonlibs` is writable for user packages.
**How to apply:** any time a backend package is in `requirements.txt` but missing at
runtime (ModuleNotFoundError), reinstall it with the `--target .pythonlibs/...` form,
not the package-management skill.
