# syntax=docker/dockerfile:1.7
FROM python:3.15-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS deps
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY backend/requirements.txt /tmp/requirements.txt
# --require-hashes: forsyningskædebeskyttelse – alle pakker er hash-pinnet
RUN pip install --require-hashes --no-deps -r /tmp/requirements.txt

FROM deps AS deps-dev
COPY backend/requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --require-hashes --no-deps -r /tmp/requirements-dev.txt

FROM base AS runtime
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
ENV PYTHONPATH=/app
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic
COPY backend/app /app/app
COPY schema /app/schema
COPY data/sample_almenramme_survey.json /app/data/sample_almenramme_survey.json
COPY frontend /app/frontend
USER 10001:10001
EXPOSE 8000

FROM runtime AS test
USER root
COPY --from=deps-dev /opt/venv /opt/venv
COPY backend/pytest.ini /app/pytest.ini
COPY backend/tests /app/tests
USER 10001:10001

FROM runtime AS final
