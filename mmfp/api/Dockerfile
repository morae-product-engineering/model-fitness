FROM python:3.12-slim

WORKDIR /app

# Copy project definition first so dependency layer is cached independently
# of source changes.
COPY pyproject.toml ./

# Install the project and its dependencies (fastapi + uvicorn) via editable
# install so the package structure matches the dev environment exactly.
COPY mmfp/ ./mmfp/

RUN pip install --no-cache-dir -e .

# MLI-178: `mmfp.api.scoreboard` reads the candidate slate from
# `${MMFP_PRODUCTS_DIR:-products}/<slug>/candidates.yaml` at request time
# (MLI-174 contract). Without these files in the image the endpoint
# returns "Unknown product 'mli'" — independent of whether the SQLite
# seed has landed. Copied after pip install so product config changes
# don't bust the dependency layer cache.
COPY products/ ./products/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "mmfp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
