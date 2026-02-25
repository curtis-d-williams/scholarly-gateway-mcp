# PyPI Publishing Instructions

Distribution name: **scholarly-gateway-mcp**
Import package: `scholarly_gateway`
Console script: `scholarly-gateway`

## Prerequisites

```bash
pip install build twine
# or: pip install -e ".[dev]"  (includes build + twine)
```

## Build

```bash
# From the repo root
python -m build
# Produces:
#   dist/scholarly_gateway_mcp-<version>-py3-none-any.whl
#   dist/scholarly_gateway_mcp-<version>.tar.gz
```

## Validate before upload

```bash
twine check dist/*
```

## Publish to TestPyPI (staging)

```bash
twine upload --repository testpypi dist/*
# Requires env var: TWINE_USERNAME=__token__
# Requires env var: TWINE_PASSWORD=<TestPyPI API token>
```

Verify after upload:
```bash
pip install --index-url https://test.pypi.org/simple/ scholarly-gateway-mcp
scholarly-gateway --help
```

## Publish to PyPI (production)

```bash
twine upload dist/*
# Requires env var: TWINE_USERNAME=__token__
# Requires env var: TWINE_PASSWORD=<PyPI API token>
```

Users can then install with:
```bash
pip install scholarly-gateway-mcp
```

## Required tokens / credentials

| Variable | Value |
|---|---|
| `TWINE_USERNAME` | `__token__` (literal string) |
| `TWINE_PASSWORD` | API token from https://pypi.org/manage/account/token/ |

For CI/CD, store the token as a repository secret (e.g., `PYPI_API_TOKEN`) and set `TWINE_PASSWORD=${{ secrets.PYPI_API_TOKEN }}`.

## Version bump procedure

1. Edit `pyproject.toml` — increment `version` following semver (e.g., `0.1.1` → `0.1.2`).
2. Commit: `git commit -m "chore: bump version to X.Y.Z"`.
3. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. Rebuild and upload: `python -m build && twine upload dist/*`.
