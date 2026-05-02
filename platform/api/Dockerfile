FROM python:3.12-slim

WORKDIR /app

# Copy project definition first so dependency layer is cached independently
# of source changes.
COPY pyproject.toml ./

# Install the project and its dependencies (fastapi + uvicorn) via editable
# install so the package structure matches the dev environment exactly.
COPY platform/ ./platform/

RUN pip install --no-cache-dir -e .

EXPOSE 8000

# python -m preserves /app (WORKDIR) in sys.path, which is required because
# the top-level package is named "platform" — identical to a stdlib module.
# Running via the console_script would set sys.path[0] to the script dir,
# hiding our package behind the stdlib lookup. -m keeps WORKDIR first.
CMD ["python", "-m", "uvicorn", "platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
