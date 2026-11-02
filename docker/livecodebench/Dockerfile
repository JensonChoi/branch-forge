FROM python:3.12-slim
ARG REVISION=28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24
RUN pip install --no-cache-dir numpy==2.2.6 tqdm==4.67.1
ADD https://github.com/LiveCodeBench/LiveCodeBench/archive/${REVISION}.tar.gz /tmp/lcb.tar.gz
RUN mkdir /opt/lcb && tar -xzf /tmp/lcb.tar.gz -C /opt/lcb --strip-components=1 && rm /tmp/lcb.tar.gz
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
LABEL org.branchforge.grader.revision="28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"
