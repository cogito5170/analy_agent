#include "bms.h"

#include <string.h>

static bool cell_signal_ok(uint16_t mv)
{
    return mv >= BMS_CELL_SIGNAL_MIN_MV && mv <= BMS_CELL_SIGNAL_MAX_MV;
}

static bool temp_signal_ok(int16_t ddegc)
{
    return ddegc >= BMS_TEMP_SIGNAL_MIN_DC && ddegc <= BMS_TEMP_SIGNAL_MAX_DC;
}

/* Count consecutive bad samples; return true once the debounce limit is reached. */
static bool debounce(uint8_t *count, bool bad)
{
    if (!bad) {
        *count = 0u;
        return false;
    }
    if (*count < BMS_FAULT_DEBOUNCE_SAMPLES) {
        (*count)++;
    }
    return *count >= BMS_FAULT_DEBOUNCE_SAMPLES;
}


static uint8_t crc8_j1850(const uint8_t *data, size_t len) {
    uint8_t crc = 0xFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 0x80) {
                crc = (uint8_t)((crc << 1) ^ 0x1D);
            } else {
                crc = (uint8_t)(crc << 1);
            }
        }
    }
    return crc ^ 0xFF;
}

void bms_can_rx(bms_t *bms, bms_inputs_t *in, const bms_can_frame_t *frame) {
    if (frame->id == 512 && frame->dlc == 3) {
        uint8_t crc = crc8_j1850(frame->data, 2);
        if (crc != frame->data[2]) {
            bms->vcu_cmd_reject_count++;
            if (bms->vcu_cmd_reject_count >= 3) {
                bms->faults |= BMS_FAULT_COMM;
            }
            return;
        }
        
        uint8_t counter = frame->data[1] & 0x0F;
        if (!bms->vcu_cmd_first) {
            uint8_t expected = (uint8_t)((bms->vcu_cmd_counter + 1) & 0x0F);
            if (counter != expected) {
                bms->vcu_cmd_reject_count++;
                if (bms->vcu_cmd_reject_count >= 3) {
                    bms->faults |= BMS_FAULT_COMM;
                }
                return;
            }
        }
        
        bms->vcu_cmd_first = false;
        bms->vcu_cmd_counter = counter;
        bms->vcu_cmd_reject_count = 0;
        bms->vcu_cmd_timer = 0;
        in->contactor_req = (frame->data[0] & 0x01) != 0;
    }
}

void bms_init(bms_t *bms)
{
    (void)memset(bms, 0, sizeof(*bms));
    bms->state = BMS_STATE_INIT;
    bms->vcu_cmd_first = true;
    bms->vcu_cmd_timer = 0;
    bms->status_timer = 100;
    bms->cellv_timer = 100;
    bms->temp_timer = 100;
    bms->fault_timer = 100;
}

void bms_step(bms_t *bms, const bms_inputs_t *in, bms_outputs_t *out)
{
    uint8_t prev_faults = bms->faults;
    out->can_tx_count = 0;
    
    bms->vcu_cmd_timer = (uint16_t)(bms->vcu_cmd_timer + BMS_TASK_PERIOD_MS);
    if (bms->vcu_cmd_timer >= 300) {
        bms->faults |= BMS_FAULT_COMM;
    }

    bool cells_ok = true;
    bool temps_ok = true;

    for (int i = 0; i < BMS_NUM_CELLS; i++) {
        bool ok = cell_signal_ok(in->cell_mv[i]);
        cells_ok = cells_ok && ok;   /* SWR-002 */
    }
    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        bool ok = temp_signal_ok(in->temp_ddegc[i]);
        temps_ok = temps_ok && ok; /* SWR-003 */
    }

    if (debounce(&bms->sig_cell_count, !cells_ok)) {
        bms->faults |= BMS_FAULT_SIG_CELL;
    }
    if (debounce(&bms->sig_temp_count, !temps_ok)) {
        bms->faults |= BMS_FAULT_SIG_TEMP;
    }

    /* Protection checks */
    bool any_ov = false;
    bool any_uv = false;
    bool any_ot = false;
    bool any_utc = false;
    bool oc = false;

    for (int i = 0; i < BMS_NUM_CELLS; i++) {
        if (in->cell_mv[i] > BMS_OV_THRESHOLD_MV) {
            any_ov = true;
        }
        if (in->cell_mv[i] < BMS_UV_THRESHOLD_MV) {
            any_uv = true;
        }
    }

    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        if (in->temp_ddegc[i] > BMS_OT_THRESHOLD_DC) {
            any_ot = true;
        }
        if (in->current_ma < 0 && in->temp_ddegc[i] < BMS_UTC_THRESHOLD_DC) {
            any_utc = true;
        }
    }

    if (in->current_ma > BMS_OC_DISCHARGE_MA || in->current_ma < -BMS_OC_CHARGE_MA) {
        oc = true;
    }

    if (debounce(&bms->ov_count, any_ov)) { bms->faults |= BMS_FAULT_OV; }
    if (debounce(&bms->uv_count, any_uv)) { bms->faults |= BMS_FAULT_UV; }
    if (debounce(&bms->ot_count, any_ot)) { bms->faults |= BMS_FAULT_OT; }
    if (debounce(&bms->utc_count, any_utc)) { bms->faults |= BMS_FAULT_UTC; }
    if (debounce(&bms->oc_count, oc)) { bms->faults |= BMS_FAULT_OC; }

    /* State machine */
    if (bms->faults != 0u) {
        bms->state = BMS_STATE_FAULT; /* SWR-004 to SWR-009 */
    } else {
        switch (bms->state) {
            case BMS_STATE_INIT:
                if (cells_ok && temps_ok) {
                    bms->state = BMS_STATE_STANDBY; /* SWR-012 */
                }
                break;
            case BMS_STATE_STANDBY:
                if (in->contactor_req) {
                    bms->state = BMS_STATE_CLOSED; /* SWR-013 */
                }
                break;
            case BMS_STATE_CLOSED:
                if (!in->contactor_req) {
                    bms->state = BMS_STATE_STANDBY; /* SWR-014 */
                }
                break;
            case BMS_STATE_FAULT:
                /* Latched until diagnostics clear it */
                break;
        }
    }

    out->state = bms->state;
    out->faults = bms->faults;

    if (bms->state == BMS_STATE_CLOSED) {
        bms->contactor_closed = true;
        bms->low_current_count = 0;
    } else if (bms->state == BMS_STATE_FAULT) {
        if (bms->faults == BMS_FAULT_COMM && bms->contactor_closed) {
            if (in->current_ma <= 5000 && in->current_ma >= -5000) {
                bms->low_current_count++;
                if (bms->low_current_count >= 3) {
                    bms->contactor_closed = false;
                }
            } else {
                bms->low_current_count = 0;
            }
        } else {
            bms->contactor_closed = false;
        }
    } else {
        bms->contactor_closed = false;
    }

    out->contactor_close = bms->contactor_closed;

    bms->status_timer = (uint16_t)(bms->status_timer + BMS_TASK_PERIOD_MS);
    if (bms->status_timer >= 100) {
        bms->status_timer = 0;
        bms_can_frame_t *f = &out->can_tx[out->can_tx_count++];
        f->id = 256;
        f->dlc = 8;
        (void)memset(f->data, 0, 8);
        f->data[0] = (uint8_t)(bms->state & 0x0F) | (out->contactor_close ? 0x10 : 0x00) | ((bms->faults & BMS_FAULT_COMM) ? 0x20 : 0x00) | ((bms->faults != 0) ? 0x40 : 0x00);
        uint16_t pack_v = 0; // PackVoltage
        for (int i=0; i<BMS_NUM_CELLS; i++) pack_v = (uint16_t)(pack_v + in->cell_mv[i]);
        f->data[1] = (uint8_t)(pack_v & 0xFF);
        f->data[2] = (uint8_t)(pack_v >> 8);
        
        // PackCurrent offset 0, scale 0.1, -3276.8 to 3276.7
        int32_t current_da = in->current_ma / 100;
        f->data[3] = (uint8_t)(current_da & 0xFF);
        f->data[4] = (uint8_t)((current_da >> 8) & 0xFF);
        
        f->data[5] = 100; // SOC = 50%
        f->data[6] = bms->status_msg_counter++ & 0x0F;
    }
    
    bms->cellv_timer = (uint16_t)(bms->cellv_timer + BMS_TASK_PERIOD_MS);
    if (bms->cellv_timer >= 100) {
        bms->cellv_timer = 0;
        bms_can_frame_t *f = &out->can_tx[out->can_tx_count++];
        f->id = 257;
        f->dlc = 8;
        for (int i=0; i<4; i++) {
            f->data[i*2] = (uint8_t)(in->cell_mv[i] & 0xFF);
            f->data[i*2+1] = (uint8_t)(in->cell_mv[i] >> 8);
        }
    }
    
    bms->temp_timer = (uint16_t)(bms->temp_timer + BMS_TASK_PERIOD_MS);
    if (bms->temp_timer >= 100) {
        bms->temp_timer = 0;
        bms_can_frame_t *f = &out->can_tx[out->can_tx_count++];
        f->id = 258;
        f->dlc = 4;
        for (int i=0; i<2; i++) {
            f->data[i*2] = (uint8_t)(in->temp_ddegc[i] & 0xFF);
            f->data[i*2+1] = (uint8_t)(in->temp_ddegc[i] >> 8);
        }
    }
    
    if (bms->faults != 0) {
        if (prev_faults == 0) {
            bms->fault_timer = 100; // Force immediate tx SWR-019
        }
        bms->fault_timer = (uint16_t)(bms->fault_timer + BMS_TASK_PERIOD_MS);
        if (bms->fault_timer >= 100) {
            bms->fault_timer = 0;
            bms_can_frame_t *f = &out->can_tx[out->can_tx_count++];
            f->id = 272;
            f->dlc = 2;
            f->data[0] = bms->faults;
            f->data[1] = bms->fault_msg_counter++ & 0x0F;
        }
    }

}
