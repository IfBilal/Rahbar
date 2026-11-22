# The RAGOps tools image (rahbar-ragops): the evaluation suite, the release gate, the coverage
# check and the trace tools. It is used by the eval Job and as the in-cluster tool shell
# (the loader pod). Build from the REPOSITORY ROOT:   docker build -f ragops/Dockerfile .
FROM python:3.12.16-slim-trixie

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp
WORKDIR /app
COPY ragops/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt && pip uninstall -y pip setuptools

COPY ragops ./ragops
# The trace tool rebuilds prompts with the API's own prompt and rail code (docs/a3-ragops/08 §6),
# so those two import-light modules ship in this image once they exist:
#   COPY api/app/services/prompt.py api/app/services/rails.py ./api_services/

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin ragops
USER 10001
# `sleep infinity` keeps the loader pod alive; the eval Job overrides the command.
ENTRYPOINT ["python", "-m"]
CMD ["ragops.gate.apply", "--help"]
