/*
 * BMS calibration constants.
 *
 * Every value is a design assumption for this portfolio project, taken from
 * requirements/swr.yaml. None of them comes from a real cell datasheet.
 */
#ifndef BMS_CONFIG_H
#define BMS_CONFIG_H

#define BMS_NUM_CELLS 4
#define BMS_NUM_TEMPS 2

#define BMS_TASK_PERIOD_MS 10           /* SWR-001 */

/* Signal plausibility (SWR-002, SWR-003) */
#define BMS_CELL_SIGNAL_MIN_MV 500      /* below 0.50 V -> signal fault */
#define BMS_CELL_SIGNAL_MAX_MV 5000     /* above 5.00 V -> signal fault */
#define BMS_TEMP_SIGNAL_MIN_DC (-400)   /* below -40.0 degC -> signal fault (deci-degC) */
#define BMS_TEMP_SIGNAL_MAX_DC 1250     /* above 125.0 degC -> signal fault (deci-degC) */

/* Number of consecutive samples a fault condition must persist (SWR-004..009) */
#define BMS_FAULT_DEBOUNCE_SAMPLES 3

/* Startup deadline: INIT must reach STANDBY within this time (SWR-012) */
#define BMS_INIT_DEADLINE_MS 100

#endif /* BMS_CONFIG_H */
