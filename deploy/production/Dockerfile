# Build from repository root AFTER prepare_release.py, then record the image digest.
# Resolve/record the base image digest on the approved builder before release.
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WAIKE_ENV=production WAIKE_FACTORY_MODE=true \
    WAIKE_HUB_DB=/var/lib/waike/hub.sqlite3 WAIKE_ROOT=/opt/waike/curriculum-source \
    WAIKE_STATIC_ROOT=/opt/waike/reader WAIKE_RELEASE_MANIFEST=/opt/waike/runtime-release.json \
    WAIKE_PRACTICE_SIGNING_KEY_FILE=/run/secrets/practice_signing_key
WORKDIR /opt/waike
COPY deploy/production/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && groupadd --gid 10001 waike && useradd --uid 10001 --gid 10001 --no-create-home waike
COPY services/hub/app /opt/waike/services/hub/app
COPY curriculum/registry/PIN.json /opt/waike/curriculum/registry/PIN.json
COPY deploy/production/operations.py /opt/waike/deploy/production/operations.py
COPY .release/curriculum /opt/waike/curriculum-source
COPY .release/reader /opt/waike/reader
COPY .release/runtime-release.json /opt/waike/runtime-release.json
ENV PYTHONPATH=/opt/waike/services/hub
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/readyz', timeout=4)"]
CMD ["uvicorn", "app.production:create_production_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--limit-concurrency", "32", "--backlog", "64", "--timeout-keep-alive", "5", "--timeout-graceful-shutdown", "30", "--no-access-log", "--no-proxy-headers"]
