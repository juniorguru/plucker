FROM apify/actor-python:3.13
ARG ACTOR_PATH_IN_DOCKER_CONTEXT

RUN rm -rf /usr/src/app/*
WORKDIR /usr/src/app

COPY . ./
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN echo "Python version:" \
 && python --version \
 && echo "uv version:" \
 && uv --version \
 && echo "Installing dependencies:" \
 && uv sync

RUN python3 -m compileall -q ./src/jg/plucker

ENV ACTOR_PATH_IN_DOCKER_CONTEXT="${ACTOR_PATH_IN_DOCKER_CONTEXT}"
CMD ["uv", "run", "plucker", "--debug", "crawl", "--apify"]
