# Mystery-box build service. Build context = repo root:
#   docker build -f service/Dockerfile -t mysterybox-build-service .
#   docker run -e API_KEY=changeme -p 8000:8000 mysterybox-build-service
FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; the build itself is pure-Python (no Rust optimizer for
# direct-probability mystery-box games).
COPY requirements.txt ./
# The editable git dep line in requirements.txt is for local dev; install the pinned
# runtime deps here and the package itself as editable from the copied source below.
RUN pip install --no-cache-dir \
      fastapi \
      "uvicorn[standard]" \
      numpy==2.2.5 \
      zstandard==0.23.0 \
      python-dotenv==1.2.2 \
      xlsxwriter==3.2.0 \
      boto3==1.35.97 \
      urllib3==2.7.0

COPY . .
RUN pip install --no-cache-dir -e .

# In-container the venv python isn't used; point the builder at the image's python.
ENV PYTHON_BIN=python
ENV ARTIFACT_DIR=/app/service/artifacts
EXPOSE 8000

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
