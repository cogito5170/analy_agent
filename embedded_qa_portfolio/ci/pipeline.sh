#!/usr/bin/env bash
# Firmware build pipeline with timing and quality metrics.
#
#   bash ci/pipeline.sh [out_dir]          (run from embedded_qa_portfolio/)
#
# Steps: host build (coverage) -> unit tests -> coverage -> ARM cross build ->
# reproducibility check. Every step is timed. Results go to <out_dir>/metrics.json
# and <out_dir>/summary.md. The script exits non-zero if any step fails; a step
# whose tool is missing (e.g. no ARM compiler on a dev machine) is "skipped".
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FW="$ROOT/firmware"
OUT="$(mkdir -p "${1:-$ROOT/build/ci}" && cd "${1:-$ROOT/build/ci}" && pwd)"
STEPS="$OUT/steps.tsv"
: > "$STEPS"
FAILED=0

run_step() {  # run_step <name> <command...>
  local name="$1"; shift
  local start end status
  start=$(date +%s.%N)
  if "$@" > "$OUT/$name.log" 2>&1; then status=passed; else status=failed; FAILED=1; fi
  end=$(date +%s.%N)
  printf '%s\t%s\t%.2f\n' "$name" "$status" "$(echo "$end - $start" | bc)" >> "$STEPS"
  echo "[$status] $name"
  [ "$status" = passed ] || tail -20 "$OUT/$name.log"
}

skip_step() {
  printf '%s\tskipped\t0\n' "$1" >> "$STEPS"
  echo "[skipped] $1: $2"
}

host_build() {
  cmake -S "$FW" -B "$OUT/host" -DBMS_COVERAGE=ON && cmake --build "$OUT/host"
}

unit_test() {
  ctest --test-dir "$OUT/host" --verbose   # verbose keeps Unity's per-case summary in the log
}

coverage() {
  # CMake names coverage files after the full source name (bms.c.gcda), so pass that to gcov.
  (cd "$OUT/host" && gcov -b -o CMakeFiles/bms.dir/src bms.c.gcda) > "$OUT/gcov.txt" \
    && grep -q "Lines executed" "$OUT/gcov.txt"
}

arm_build() {
  cmake -S "$FW" -B "$OUT/arm" -DCMAKE_TOOLCHAIN_FILE="$FW/cmake/arm-none-eabi.cmake" \
        -DBMS_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=MinSizeRel \
    && cmake --build "$OUT/arm" \
    && arm-none-eabi-size -t "$OUT/arm/libbms.a" > "$OUT/arm_size.txt"
}

# Two copies of the sources in different directories must give the same Debug library.
reproducible() {
  local a="$OUT/repro/a/src" b="$OUT/repro/b/elsewhere"
  rm -rf "$OUT/repro" && mkdir -p "$a" "$b"
  cp -r "$FW/." "$a" && cp -r "$FW/." "$b"
  for d in "$a" "$b"; do
    cmake -S "$d" -B "$d/build" -DBMS_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Debug >/dev/null \
      && cmake --build "$d/build" >/dev/null || return 1
  done
  sha256sum "$a/build/libbms.a" "$b/build/libbms.a" | tee "$OUT/repro.txt"
  [ "$(sha256sum < "$a/build/libbms.a")" = "$(sha256sum < "$b/build/libbms.a")" ]
}

run_step host_build host_build
run_step unit_test unit_test
run_step coverage coverage
if command -v arm-none-eabi-gcc > /dev/null; then
  run_step arm_build arm_build
else
  skip_step arm_build "arm-none-eabi-gcc not installed (use the CI container: ci/Dockerfile)"
fi
run_step reproducible reproducible

python3 "$ROOT/ci/metrics.py" "$OUT"
exit $FAILED
