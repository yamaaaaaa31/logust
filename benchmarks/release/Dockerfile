FROM python:3.14.9-slim-bookworm@sha256:945c2676dc2b18e0c1f16879244122c57c0ffede60006bf3df159c507a31bcae

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates pkg-config \
    && rm -rf /var/lib/apt/lists/*
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo
ENV PATH=/opt/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --default-toolchain 1.96.0
RUN python -m pip install --no-cache-dir \
    maturin==1.15.0 loguru==0.7.3 pytest rich httpx fastapi starlette uuid-utils \
    ruff mypy mkdocs-material mkdocs-redirects mkdocs-minify-plugin mike
WORKDIR /work
