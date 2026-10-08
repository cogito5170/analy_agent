/*
 * BMS application layer: hardware independent.
 *
 * The integration (a real MCU main loop, or the SIL harness) calls bms_step()
 * every BMS_TASK_PERIOD_MS with the latest measurements and applies the
 * returned outputs. The application never touches hardware directly, so the
 * same code runs on the host for unit tests and SIL, and on the target MCU.
 */
#ifndef BMS_H
#define BMS_H

#include <stdbool.h>
#include <stdint.h>

#include "bms_config.h"

typedef enum {
    BMS_STATE_INIT = 0,
    BMS_STATE_STANDBY = 1,
    BMS_STATE_CLOSED = 2,
    BMS_STATE_FAULT = 3,
} bms_state_t;

/* Fault bits, matching signal order in BMS_Fault (can/bms.dbc). */
enum {
    BMS_FAULT_OV = 1u << 0,
    BMS_FAULT_UV = 1u << 1,
    BMS_FAULT_OT = 1u << 2,
    BMS_FAULT_UTC = 1u << 3,
    BMS_FAULT_OC = 1u << 4,
    BMS_FAULT_SIG_CELL = 1u << 5,
    BMS_FAULT_SIG_TEMP = 1u << 6,
    BMS_FAULT_COMM = 1u << 7,
};

typedef struct {
    uint16_t cell_mv[BMS_NUM_CELLS];
    int16_t temp_ddegc[BMS_NUM_TEMPS]; /* 0.1 degC */
    int32_t current_ma;                /* positive = discharge */
} bms_inputs_t;

typedef struct {
    bool contactor_close;
    bms_state_t state;
    uint8_t faults; /* BMS_FAULT_* bits */
} bms_outputs_t;

typedef struct {
    bms_state_t state;
    uint8_t faults;
    uint8_t sig_cell_count;
    uint8_t sig_temp_count;
} bms_t;

void bms_init(bms_t *bms);
void bms_step(bms_t *bms, const bms_inputs_t *in, bms_outputs_t *out);

#endif /* BMS_H */
