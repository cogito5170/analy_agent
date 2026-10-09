# Plant Model Parameters

Every parameter is a design assumption (no datasheet claims).

| Parameter | Value | Unit | Description |
|---|---|---|---|
| `Q_cap` | 100.0 | Ah | Cell capacity (design assumption) |
| `R0` | 0.002 | $\Omega$ | Series internal resistance (design assumption) |
| `R1` | 0.005 | $\Omega$ | RC branch resistance (design assumption) |
| `C1` | 2000.0 | F | RC branch capacitance (design assumption) |
| `C_th` | 500.0 | J/K | Cell thermal capacity (design assumption) |
| `R_th` | 2.0 | K/W | Cell thermal resistance to ambient (design assumption) |
| `T_amb` | 25.0 | $^\circ$C | Ambient temperature (design assumption) |
| `OCV(SOC)` | $3.0 + 1.2 \times SOC$ | V | Open-circuit voltage curve (design assumption) |
