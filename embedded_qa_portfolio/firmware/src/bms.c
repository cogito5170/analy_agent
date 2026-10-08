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

void bms_init(bms_t *bms)
{
    (void)memset(bms, 0, sizeof(*bms));
    bms->state = BMS_STATE_INIT;
    bms->first_step = true;
}

void bms_step(bms_t *bms, const bms_inputs_t *in, bms_outputs_t *out)
{
    bool cells_ok = true;
    bool temps_ok = true;

    for (int i = 0; i < BMS_NUM_CELLS; i++) {
        bool ok = cell_signal_ok(in->cell_mv[i]);
        cells_ok = cells_ok && ok;   /* SWR-002 */
        if (bms->first_step) {
            bms->cell_mv_avg[i] = in->cell_mv[i];
        } else if (ok) {
            bms->cell_mv_avg[i] = (uint16_t)((bms->cell_mv_avg[i] + in->cell_mv[i]) / 2);
        }
    }
    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        bool ok = temp_signal_ok(in->temp_ddegc[i]);
        temps_ok = temps_ok && ok; /* SWR-003 */
        if (bms->first_step) {
            bms->temp_ddegc_avg[i] = in->temp_ddegc[i];
        } else if (ok) {
            bms->temp_ddegc_avg[i] = (int16_t)((bms->temp_ddegc_avg[i] + in->temp_ddegc[i]) / 2);
        }
    }
    bms->first_step = false;

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
        if (bms->cell_mv_avg[i] > BMS_OV_THRESHOLD_MV) {
            any_ov = true;
        }
        if (bms->cell_mv_avg[i] < BMS_UV_THRESHOLD_MV) {
            any_uv = true;
        }
    }

    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        if (bms->temp_ddegc_avg[i] > BMS_OT_THRESHOLD_DC) {
            any_ot = true;
        }
        if (in->current_ma < 0 && bms->temp_ddegc_avg[i] < BMS_UTC_THRESHOLD_DC) {
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
    /* SWR-011: FAULT ignores ContactorReq */
    out->contactor_close = (bms->state == BMS_STATE_CLOSED);
}
