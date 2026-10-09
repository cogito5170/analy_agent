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


typedef struct {
    uint32_t id;
    uint8_t dlc;
    uint8_t data[8];
} bms_can_frame_t;

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
    bool contactor_req;
} bms_inputs_t;

typedef struct {
    bool contactor_close;
    bms_state_t state;
    uint8_t faults; /* BMS_FAULT_* bits */
    bms_can_frame_t can_tx[4];
    uint8_t can_tx_count;
} bms_outputs_t;

typedef struct {
    bms_state_t state;
    uint8_t faults;
    uint8_t sig_cell_count;
    uint8_t sig_temp_count;
    uint8_t ov_count;
    uint8_t uv_count;
    uint8_t ot_count;
    uint8_t utc_count;
    uint8_t oc_count;
    uint16_t vcu_cmd_timer;
    uint8_t vcu_cmd_reject_count;
    uint8_t vcu_cmd_counter;
    bool vcu_cmd_first;
    uint16_t status_timer;
    uint16_t cellv_timer;
    uint16_t temp_timer;
    uint16_t fault_timer;
    uint8_t status_msg_counter;
    uint8_t fault_msg_counter;
    uint8_t low_current_count;
    bool contactor_closed;
    float soc;
    bool soc_initialized;
} bms_t;

void bms_init(bms_t *bms);
void bms_can_rx(bms_t *bms, bms_inputs_t *in, const bms_can_frame_t *frame);
void bms_step(bms_t *bms, const bms_inputs_t *in, bms_outputs_t *out);

#endif /* BMS_H */
