FROM python:3.12-slim

WORKDIR /app

# Copy project definition first so dependency layer is cached independently
# of source changes.
COPY pyproject.toml ./

# Install the project and its dependencies (fastapi + uvicorn) via editable
# install so the package structure matches the dev environment exactly.
COPY mmfp/ ./mmfp/

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "mmfp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
