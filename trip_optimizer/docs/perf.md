# Performance Budgets

Rule: Each budget is set to 2x its measured median with a floor of 5 ms for native and 20 ms for browser to absorb shared-runner noise.

Measured on GitHub runner, 2026-10-08:
- Native median: 0.490158 ms
- Web median: 3.90 ms
- Native Budget: 5 ms
- Web Budget: 20 ms
- Lighthouse Performance: 100
- Lighthouse Accessibility: 87
