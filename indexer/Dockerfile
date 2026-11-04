# The indexer Job's image: the only process that writes Chroma (case study 4.2).
# Build from the REPOSITORY ROOT so the image also carries the fetch script, the
# committed source list and the CI fixtures:   docker build -f indexer/Dockerfile .
FROM python:3.12.16-slim-trixie

# OCR toolchain for the scanned PDFs (3.1 Extract): tesseract for text, poppler for
# rasterising pages. `upgrade` picks up Debian security fixes so the Trivy gate passes.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY indexer/requirements.txt ./requirements.txt
# Nothing installs packages at runtime, so pip and setuptools leave the image: less attack
# surface, and pip's vendored setuptools 70.3.0 copy (CVE-2025-47273) goes with it.
RUN pip install -r requirements.txt && pip uninstall -y pip setuptools

COPY indexer/pipeline ./pipeline
# corpus/fetch.py + sources.yaml + MANIFEST.md: the Job's init container downloads the
# corpus at start-up (third-party PDFs are never baked into a public image).
COPY corpus/fetch.py corpus/sources.yaml corpus/MANIFEST.md ./corpus/
# The fictional fixture corpus (ours) for the CI e2e-eval job: CORPUS_DIR=/app/eval/fixtures
COPY eval/fixtures ./eval/fixtures

# Non-root, numeric so runAsNonRoot can verify it without /etc/passwd.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin indexer
USER 10001
ENTRYPOINT ["python", "-m", "pipeline.run"]
