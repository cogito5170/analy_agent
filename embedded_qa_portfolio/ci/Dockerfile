# Build environment for the BMS firmware: host toolchain for unit tests and
# coverage, plus the ARM cross compiler. Everyone (CI and developers) builds
# inside this image, so "works on my machine" differences cannot creep in.
#
#   docker build -t bms-ci embedded_qa_portfolio/ci
#   docker run --rm -v "$PWD":/work -w /work/embedded_qa_portfolio bms-ci bash ci/pipeline.sh build/ci
FROM ubuntu:24.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bc ca-certificates cmake gcc git libc6-dev make python3 python3-yaml cppcheck \
      binutils-arm-none-eabi gcc-arm-none-eabi libnewlib-arm-none-eabi \
 && rm -rf /var/lib/apt/lists/*

# The work tree is bind-mounted with a different owner than the container user.
RUN git config --system --add safe.directory '*'
