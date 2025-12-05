FROM python:3.12

EXPOSE 8080
ENV PORT 8080

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies using uv
# Copy pyproject.toml, uv.lock, and README.md (required by pyproject.toml)
COPY pyproject.toml uv.lock README.md ./
RUN uv pip install --system --no-cache .

# Copy the app to the container
COPY ./app ./app

# Run the app
CMD uvicorn app.main:app --host 0.0.0.0 --port 8080

