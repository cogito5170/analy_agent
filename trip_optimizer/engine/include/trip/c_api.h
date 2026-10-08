/*
 * C interface for WebAssembly (and any other FFI).
 *
 * Inputs are flat arrays in the layout of trip::Problem. Money and minutes are
 * passed as doubles because JavaScript numbers are doubles; they must hold whole
 * numbers below 2^53, which is checked, so results stay exact.
 *
 * Output layout, repeated for each plan:
 *   objective, transport_price, lodging_price, travel_minutes,
 *   n_legs,  then n_legs  x (from, to, day, mode, price, minutes),
 *   n_stays, then n_stays x (city, arrive_day, nights, lodging)
 */
#ifndef TRIP_C_API_H
#define TRIP_C_API_H

#ifdef __cplusplus
extern "C" {
#endif

/* Doubles needed in `out` for k plans of a trip with `visits` cities. */
int trip_output_size(int visits, int k);

/* Returns the number of plans written (0 = no feasible trip), or -1 on invalid
 * input (see trip_last_error) or -2 if `out_len` is too small. */
int trip_optimize(int visits, int days, int modes,
                  const double* price, const double* minutes, const double* lodging,
                  const int* stay_min, const int* stay_max,
                  int depart_min, int depart_max, double cost_per_minute,
                  int k, double* out, int out_len);

const char* trip_last_error(void);

#ifdef __cplusplus
}
#endif

#endif /* TRIP_C_API_H */
