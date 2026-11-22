# syntax=docker/dockerfile:1
# ------------------------------------------------------------------------------
# Stage 1: Build native llama.cpp backend & Python wheel
# ------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ninja-build \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pinned llama.cpp commit for exact reproducibility
ARG LLAMA_COMMIT=b1b770d90d94cad9e9ea5b993bdbc383a522fb28

WORKDIR /build/llama.cpp
RUN git init . && \
    git remote add origin https://github.com/ggml-org/llama.cpp.git && \
    git fetch --depth 1 origin ${LLAMA_COMMIT} && \
    git checkout --detach ${LLAMA_COMMIT}

RUN cmake -B build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=OFF \
    -DGGML_NATIVE=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_TOOLS=ON \
    -DLLAMA_BUILD_SERVER=ON \
    -DLLAMA_OPENSSL=OFF \
    -DLLAMA_BUILD_UI=OFF \
    -DLLAMA_USE_PREBUILT_UI=OFF && \
    cmake --build build --target llama-server -j $(nproc)

# Stage native artifacts
RUN mkdir -p /opt/lattice/bin /opt/lattice/lib && \
    cp build/bin/llama-server /opt/lattice/bin/ && \
    cp -d build/bin/*.so* /opt/lattice/lib/

# Build Lattice python wheel
WORKDIR /build/lattice
COPY . .
RUN pip install --no-cache-dir build && \
    python -m build --wheel --outdir /opt/lattice/dist

# ------------------------------------------------------------------------------
# Stage 2: Minimal runtime image
# ------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runner

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/opt/lattice/lib:${LD_LIBRARY_PATH} \
    PATH=/opt/lattice/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create application directories
WORKDIR /app
RUN mkdir -p /app/configs /app/models /app/artifacts

# Copy native backend & python wheel from builder
COPY --from=builder /opt/lattice /opt/lattice

# Install Lattice into container python environment
RUN pip install --no-cache-dir /opt/lattice/dist/*.whl

# Default ports and healthcheck
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# Launch Lattice with preemptive chat preset binding 0.0.0.0
ENTRYPOINT ["lattice"]
CMD ["serve", "--preset", "chat", "--host", "0.0.0.0", "--port", "8000", "--allow-unauthenticated"]
