FROM mcr.microsoft.com/playwright/python:v1.58.0-noble@sha256:678457c4c323b981d8b4befc57b95366bb1bb6aa30057b1269f6b171e8d9975a

WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.18
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY crawler ./crawler
COPY tests ./tests
ENV PYTHONUNBUFFERED=1
CMD ["xvfb-run", "--auto-servernum", "uv", "run", "--locked", "--offline", "python", "-m", "crawler.run"]
