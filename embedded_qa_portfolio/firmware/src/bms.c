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
}

void bms_step(bms_t *bms, const bms_inputs_t *in, bms_outputs_t *out)
{
    bool cells_ok = true;
    bool temps_ok = true;

    for (int i = 0; i < BMS_NUM_CELLS; i++) {
        cells_ok = cells_ok && cell_signal_ok(in->cell_mv[i]);   /* SWR-002 */
    }
    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        temps_ok = temps_ok && temp_signal_ok(in->temp_ddegc[i]); /* SWR-003 */
    }

    if (debounce(&bms->sig_cell_count, !cells_ok)) {
        bms->faults |= BMS_FAULT_SIG_CELL;
    }
    if (debounce(&bms->sig_temp_count, !temps_ok)) {
        bms->faults |= BMS_FAULT_SIG_TEMP;
    }

    if (bms->faults != 0u) {
        bms->state = BMS_STATE_FAULT; /* SWR-004: latched until diagnostics clear it */
    } else if (bms->state == BMS_STATE_INIT) {
        /* SWR-012: leave INIT on the first sample with all channels plausible. A channel
         * that stays implausible reaches FAULT through the debounce above instead. */
        if (cells_ok && temps_ok) {
            bms->state = BMS_STATE_STANDBY;
        }
    }

    out->state = bms->state;
    out->faults = bms->faults;
    out->contactor_close = (bms->state == BMS_STATE_CLOSED);
}
