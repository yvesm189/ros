# ROS Console.
#
# The build context is the repository root, not this directory: the console
# serves the same typefaces the workstation uses, and those live once in
# branding/fonts rather than once per consumer.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROS_DB_PATH=/data/ros.db

WORKDIR /app

COPY management/console/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY management/console/app ./app

# Stage the brand fonts under names a stylesheet can reference without URL
# escaping - the upstream files are called FunnelDisplay[wght].ttf.
COPY branding/fonts/*.ttf /tmp/fonts/
RUN mkdir -p app/static/fonts \
    && cp "/tmp/fonts/FunnelDisplay[wght].ttf" app/static/fonts/funnel-display.ttf \
    && cp "/tmp/fonts/SpaceGrotesk[wght].ttf" app/static/fonts/space-grotesk.ttf \
    && rm -rf /tmp/fonts

RUN useradd --system --uid 10001 ros && mkdir -p /data && chown ros:ros /data
USER ros
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
