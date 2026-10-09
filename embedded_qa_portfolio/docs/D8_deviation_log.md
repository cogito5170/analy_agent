# D8 Static Analysis Deviation Log

| Rule / Suppression | Module | Reason |
| --- | --- | --- |
| `unusedFunction` | `bms.c`, `bms_init`, `bms_step`, `bms_can_rx` | These functions form the public API of the BMS application layer and are meant to be called by the integration/harness, so they are not used within `bms.c` itself. |
| `missingIncludeSystem` | Global | System headers like `<stdint.h>` and `<stdbool.h>` are provided by the compiler and are not available or necessary for Cppcheck's analysis of the application logic. |
