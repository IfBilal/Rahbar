# The API image: reads the index, never writes it (case study 4.2). Build context: api/
FROM python:3.12.16-slim-trixie

# `upgrade` picks up Debian security fixes so the Trivy HIGH/CRITICAL gate passes.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# APP_VERSION is returned in the X-Rahbar-Version header: cd.yml passes the commit SHA,
# so "what is running?" has a one-word answer you can paste into `git show`.
ARG APP_VERSION=dev
# HOME=/tmp: the root filesystem is read-only on the cluster; /tmp is an emptyDir.
ENV APP_VERSION=${APP_VERSION} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 HOME=/tmp
WORKDIR /app
COPY requirements.txt .
# Nothing installs packages at runtime, so pip and setuptools leave the image: less attack
# surface, and pip's vendored setuptools 70.3.0 copy (CVE-2025-47273) goes with it.
RUN pip install -r requirements.txt && pip uninstall -y pip setuptools

COPY app ./app

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin api
USER 10001
EXPOSE 8000
# exec form: SIGTERM reaches uvicorn directly, so the preStop + grace period drain works.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
