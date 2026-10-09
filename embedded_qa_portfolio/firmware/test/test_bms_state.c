/*
 * Unit tests for signal plausibility and the INIT/STANDBY/FAULT transitions.
 * Each test names the requirement it verifies with an @verifies tag, which the
 * traceability script reads.
 */
#include "bms.h"
#include "unity.h"

#include <string.h>

static bms_t bms;
static bms_inputs_t in;
static bms_outputs_t out;

void setUp(void)
{
    bms_init(&bms);
    (void)memset(&out, 0, sizeof(out)); /* no output may leak from a previous test */
    for (int i = 0; i < BMS_NUM_CELLS; i++) {
        in.cell_mv[i] = 3700;
    }
    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        in.temp_ddegc[i] = 250;
    }
    in.current_ma = 0;
    in.contactor_req = false;
}

void tearDown(void) {}

static void step_n(int n)
{
    for (int i = 0; i < n; i++) {
        bms_step(&bms, &in, &out);
    }
}

/* @verifies SWR-012 */
static void test_init_reaches_standby_within_deadline(void)
{
    int steps = 0;
    do { /* step at least once so the verdict always comes from the firmware */
        bms_step(&bms, &in, &out);
        steps++;
    } while (out.state != BMS_STATE_STANDBY && steps * BMS_TASK_PERIOD_MS < BMS_INIT_DEADLINE_MS);
    TEST_ASSERT_EQUAL(BMS_STATE_STANDBY, out.state);
    TEST_ASSERT_LESS_OR_EQUAL(BMS_INIT_DEADLINE_MS, steps * BMS_TASK_PERIOD_MS);
    TEST_ASSERT_FALSE(out.contactor_close);
}

/* @verifies SWR-002 — boundary values: 499/500 and 5000/5001 mV */
static void test_cell_signal_boundaries(void)
{
    const struct { uint16_t mv; bool fault; } cases[] = {
        {499, true}, {500, false}, {5000, false}, {5001, true},
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        setUp();
        in.cell_mv[2] = cases[i].mv;
        step_n(BMS_FAULT_DEBOUNCE_SAMPLES);
        TEST_ASSERT_EQUAL_MESSAGE(cases[i].fault, (out.faults & BMS_FAULT_SIG_CELL) != 0,
                                  "cell signal fault at boundary");
    }
}

/* @verifies SWR-003 — boundary values: -40.1/-40.0 and 125.0/125.1 degC */
static void test_temp_signal_boundaries(void)
{
    const struct { int16_t ddegc; bool fault; } cases[] = {
        {-401, true}, {-400, false}, {1250, false}, {1251, true},
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        setUp();
        in.temp_ddegc[1] = cases[i].ddegc;
        step_n(BMS_FAULT_DEBOUNCE_SAMPLES);
        TEST_ASSERT_EQUAL_MESSAGE(cases[i].fault, (out.faults & BMS_FAULT_SIG_TEMP) != 0,
                                  "temperature signal fault at boundary");
    }
}

/* @verifies SWR-004 — fault only after 3 consecutive bad samples */
static void test_signal_fault_debounce(void)
{
    step_n(1); /* STANDBY */
    in.cell_mv[0] = 0;
    step_n(BMS_FAULT_DEBOUNCE_SAMPLES - 1);
    TEST_ASSERT_EQUAL(BMS_STATE_STANDBY, out.state);
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_FAULT, out.state);
    TEST_ASSERT_FALSE(out.contactor_close);
}

/* @verifies SWR-004 — a good sample resets the debounce counter */
static void test_intermittent_signal_does_not_fault(void)
{
    step_n(1);
    for (int i = 0; i < 10; i++) {
        in.cell_mv[0] = (i % 2 == 0) ? 0 : 3700;
        step_n(1);
    }
    TEST_ASSERT_EQUAL(BMS_STATE_STANDBY, out.state);
    TEST_ASSERT_EQUAL_UINT8(0, out.faults);
}

/* @verifies SWR-004 — FAULT is latched after the signal recovers */
static void test_fault_is_latched(void)
{
    in.temp_ddegc[0] = 2000;
    step_n(BMS_FAULT_DEBOUNCE_SAMPLES);
    in.temp_ddegc[0] = 250;
    step_n(5);
    TEST_ASSERT_EQUAL(BMS_STATE_FAULT, out.state);
}

/* @verifies SWR-005 */
static void test_ov_boundary_and_debounce(void)
{
    const struct { uint16_t mv; int steps; bool fault; } cases[] = {
        {4250, 50, false},
        {4251, 2, false},
        {4251, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        step_n(10);
        in.cell_mv[0] = cases[i].mv;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_OV) != 0);
    }
}

/* @verifies SWR-006 */
static void test_uv_boundary_and_debounce(void)
{
    const struct { uint16_t mv; int steps; bool fault; } cases[] = {
        {2800, 50, false},
        {2799, 2, false},
        {2799, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        step_n(10);
        in.cell_mv[0] = cases[i].mv;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_UV) != 0);
    }
}

/* @verifies SWR-007 */
static void test_ot_boundary_and_debounce(void)
{
    const struct { int16_t dc; int steps; bool fault; } cases[] = {
        {600, 50, false},
        {601, 2, false},
        {601, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        step_n(10);
        in.temp_ddegc[0] = cases[i].dc;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_OT) != 0);
    }
}

/* @verifies SWR-008 */
static void test_utc_boundary_and_debounce(void)
{
    const struct { int16_t dc; int32_t ma; int steps; bool fault; } cases[] = {
        {0, -1000, 50, false},
        {-1, 0, 50, false},
        {-1, -1000, 2, false},
        {-1, -1000, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        step_n(10);
        in.temp_ddegc[0] = cases[i].dc;
        in.current_ma = cases[i].ma;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_UTC) != 0);
    }
}

/* @verifies SWR-009 */
static void test_oc_boundary_and_debounce(void)
{
    const struct { int32_t ma; int steps; bool fault; } cases[] = {
        {150000, 50, false},
        {150001, 2, false},
        {150001, 3, true},
        {-50000, 50, false},
        {-50001, 2, false},
        {-50001, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        step_n(10);
        in.current_ma = cases[i].ma;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_OC) != 0);
    }
}

/* @verifies SWR-010 */
static void test_contactor_opens_on_fault_within_deadline(void)
{
    step_n(10);
    in.contactor_req = true;
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_CLOSED, out.state);
    TEST_ASSERT_TRUE(out.contactor_close);
    
    in.cell_mv[0] = 4251;
    step_n(3);
    TEST_ASSERT_EQUAL(BMS_STATE_FAULT, out.state);
    TEST_ASSERT_FALSE(out.contactor_close);
}

/* @verifies SWR-011 */
static void test_fault_ignores_contactor_req(void)
{
    in.cell_mv[0] = 5000;
    step_n(3);
    TEST_ASSERT_EQUAL(BMS_STATE_FAULT, out.state);
    
    in.contactor_req = true;
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_FAULT, out.state);
    TEST_ASSERT_FALSE(out.contactor_close);
}

/* @verifies SWR-013 */
static void test_standby_to_closed_on_req(void)
{
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_STANDBY, out.state);
    
    in.contactor_req = true;
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_CLOSED, out.state);
    TEST_ASSERT_TRUE(out.contactor_close);
}

/* @verifies SWR-014 */
static void test_closed_to_standby_on_req_drop(void)
{
    step_n(1);
    in.contactor_req = true;
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_CLOSED, out.state);
    
    in.contactor_req = false;
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_STANDBY, out.state);
    TEST_ASSERT_FALSE(out.contactor_close);
}


/* @verifies SWR-015 */
static void test_swr_015(void)
{
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    step_n(28); // 290ms total
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    step_n(1); // 300ms total
    TEST_ASSERT_NOT_EQUAL(0, out.faults & BMS_FAULT_COMM);
}

// Actually let's calculate CRC in test.
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

static void send_vcu_cmd(uint8_t req, uint8_t counter, bool bad_crc) {
    bms_can_frame_t frame;
    frame.id = 512;
    frame.dlc = 3;
    frame.data[0] = req;
    frame.data[1] = counter;
    uint8_t crc = crc8_j1850(frame.data, 2);
    frame.data[2] = bad_crc ? ~crc : crc;
    bms_can_rx(&bms, &in, &frame);
}

/* @verifies SWR-016 SWR-031 */
static void test_can_vcu_cmd(void)
{
    // wrap 15 -> 0 accepted
    send_vcu_cmd(0, 15, false);
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    
    send_vcu_cmd(0, 0, false);
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
}

/* @verifies SWR-016 SWR-031 */
static void test_swr_016_031_skipped_counter(void)
{
    send_vcu_cmd(0, 0, false);
    step_n(1);
    
    // 2 bad frames no fault
    send_vcu_cmd(0, 2, false); // skipped counter 1 -> 2
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    
    send_vcu_cmd(0, 4, false); // skipped counter 3 -> 4
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    
    // 3 bad frames fault
    send_vcu_cmd(0, 6, false); // skipped counter
    step_n(1);
    TEST_ASSERT_NOT_EQUAL(0, out.faults & BMS_FAULT_COMM);
}

/* @verifies SWR-016 SWR-031 */
static void test_swr_016_031_bad_checksum(void)
{
    send_vcu_cmd(0, 0, false);
    step_n(1);
    
    send_vcu_cmd(0, 1, true); // bad checksum
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    
    send_vcu_cmd(0, 2, true); // bad checksum
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    
    send_vcu_cmd(0, 3, true); // bad checksum
    step_n(1);
    TEST_ASSERT_NOT_EQUAL(0, out.faults & BMS_FAULT_COMM);
}

/* @verifies SWR-017 */
static void test_swr_017(void)
{
    // BMS_Status every 100 ms
    step_n(1);
    bool found = false;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 256) found = true;
    }
    TEST_ASSERT_TRUE(found);
    
    // not in next step
    step_n(1);
    found = false;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 256) found = true;
    }
    TEST_ASSERT_FALSE(found);
    
    // at 10th step (100ms later)
    step_n(9);
    found = false;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 256) found = true;
    }
    TEST_ASSERT_TRUE(found);
}

/* @verifies SWR-018 */
static void test_swr_018(void)
{
    step_n(1);
    bool cell_found = false, temp_found = false;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 257) cell_found = true;
        if (out.can_tx[i].id == 258) temp_found = true;
    }
    TEST_ASSERT_TRUE(cell_found);
    TEST_ASSERT_TRUE(temp_found);
    
    step_n(10); // Next 100ms
    cell_found = false; temp_found = false;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 257) cell_found = true;
        if (out.can_tx[i].id == 258) temp_found = true;
    }
    TEST_ASSERT_TRUE(cell_found);
    TEST_ASSERT_TRUE(temp_found);
}

/* @verifies SWR-019 */
static void test_swr_019(void)
{
    step_n(10);
    // Trigger protection fault
    in.cell_mv[0] = 4251;
    step_n(3);
    
    // Fault triggered. BMS_Fault should be tx'd in this step (within 10ms)
    bool found = false;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 272) found = true;
    }
    TEST_ASSERT_TRUE(found);
    
    // 100ms later
    step_n(10);
    found = false;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 272) found = true;
    }
    TEST_ASSERT_TRUE(found);
}


/* @verifies SWR-017 */
static void test_determinism(void)
{
    bms_t bms1, bms2;
    bms_outputs_t out1, out2;
    bms_inputs_t in1, in2;

    bms_init(&bms1);
    bms_init(&bms2);
    (void)memset(&out1, 0, sizeof(out1));
    (void)memset(&out2, 0, sizeof(out2));
    (void)memset(&in1, 0, sizeof(in1));
    (void)memset(&in2, 0, sizeof(in2));

    for (int i = 0; i < BMS_NUM_CELLS; i++) {
        in1.cell_mv[i] = 3700;
        in2.cell_mv[i] = 3700;
    }
    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        in1.temp_ddegc[i] = 250;
        in2.temp_ddegc[i] = 250;
    }

    for (int i = 0; i < 40; i++) {
        bms_step(&bms1, &in1, &out1);
        bms_step(&bms2, &in2, &out2);
        TEST_ASSERT_EQUAL_MEMORY(&out1, &out2, sizeof(bms_outputs_t));
    }
}

/* @verifies SWR-030 */
static void test_swr_030_comm_loss_contactor_handling(void)
{
    step_n(15);
    TEST_ASSERT_EQUAL(BMS_STATE_STANDBY, out.state);
    
    in.contactor_req = true;
    step_n(1);
    TEST_ASSERT_EQUAL(BMS_STATE_CLOSED, out.state);
    
    in.current_ma = 100000;
    
    step_n(24);
    
    TEST_ASSERT_EQUAL(BMS_STATE_FAULT, out.state);
    TEST_ASSERT_EQUAL(BMS_FAULT_COMM, out.faults);
    TEST_ASSERT_TRUE(out.contactor_close);
    
    in.current_ma = 5000;
    step_n(1);
    TEST_ASSERT_TRUE(out.contactor_close);
    step_n(1);
    TEST_ASSERT_TRUE(out.contactor_close);
    step_n(1);
    TEST_ASSERT_FALSE(out.contactor_close);
}


/* @verifies SWR-019 */
static void test_swr_019_escalation(void)
{
    step_n(10);
    // Comm fault
    send_vcu_cmd(0, 0, false);
    step_n(1);
    send_vcu_cmd(0, 2, false);
    step_n(1);
    send_vcu_cmd(0, 4, false);
    step_n(1);
    send_vcu_cmd(0, 6, false);
    step_n(1);
    
    out.can_tx_count = 0;
    
    // Comm fault active, now OV
    in.cell_mv[0] = 4251;
    step_n(3);
    
    bool found = false;
    uint8_t faults_tx = 0;
    for (int i=0; i<out.can_tx_count; i++) {
        if (out.can_tx[i].id == 272) {
            found = true;
            faults_tx = out.can_tx[i].data[0];
        }
    }
    TEST_ASSERT_TRUE(found);
    TEST_ASSERT_EQUAL(BMS_FAULT_COMM | BMS_FAULT_OV, faults_tx);
}

/* @verifies SWR-016 SWR-031 */
static void test_counter_resync(void)
{
    send_vcu_cmd(0, 0, false);
    step_n(1);
    
    // One lost frame -> jumps to 2
    send_vcu_cmd(0, 2, false);
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    
    // Next frame is 3, should be accepted without fault
    send_vcu_cmd(0, 3, false);
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
    
    // 3 consecutive bad checksums
    send_vcu_cmd(0, 4, true);
    step_n(1);
    send_vcu_cmd(0, 5, true);
    step_n(1);
    send_vcu_cmd(0, 6, true);
    step_n(1);
    TEST_ASSERT_NOT_EQUAL(0, out.faults & BMS_FAULT_COMM);
}

/* @verifies SWR-016 */
static void test_counter_wrap(void)
{
    send_vcu_cmd(0, 15, false);
    step_n(1);
    
    send_vcu_cmd(0, 0, false);
    step_n(1);
    TEST_ASSERT_EQUAL(0, out.faults & BMS_FAULT_COMM);
}

/* @verifies SWR-030 */
static void test_swr_030_reset(void)
{
    step_n(15);
    in.contactor_req = true;
    step_n(1);
    
    in.current_ma = 10000;
    
    send_vcu_cmd(1, 0, false);
    step_n(1);
    send_vcu_cmd(1, 2, false);
    step_n(1);
    send_vcu_cmd(1, 4, false);
    step_n(1);
    send_vcu_cmd(1, 6, false);
    step_n(1);
    
    TEST_ASSERT_EQUAL(BMS_STATE_FAULT, out.state);
    
    in.current_ma = 4000;
    step_n(1);
    step_n(1);
    TEST_ASSERT_TRUE(out.contactor_close);
    
    in.current_ma = 6000;
    step_n(1);
    TEST_ASSERT_TRUE(out.contactor_close);
    
    in.current_ma = 4000;
    step_n(1);
    step_n(1);
    TEST_ASSERT_TRUE(out.contactor_close);
    
    step_n(1);
    TEST_ASSERT_FALSE(out.contactor_close);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_init_reaches_standby_within_deadline);
    RUN_TEST(test_cell_signal_boundaries);
    RUN_TEST(test_temp_signal_boundaries);
    RUN_TEST(test_signal_fault_debounce);
    RUN_TEST(test_intermittent_signal_does_not_fault);
    RUN_TEST(test_fault_is_latched);
    
    RUN_TEST(test_ov_boundary_and_debounce);
    RUN_TEST(test_uv_boundary_and_debounce);
    RUN_TEST(test_ot_boundary_and_debounce);
    RUN_TEST(test_utc_boundary_and_debounce);
    RUN_TEST(test_oc_boundary_and_debounce);
    RUN_TEST(test_contactor_opens_on_fault_within_deadline);
    RUN_TEST(test_fault_ignores_contactor_req);
    RUN_TEST(test_standby_to_closed_on_req);
    RUN_TEST(test_closed_to_standby_on_req_drop);
    RUN_TEST(test_swr_015);
    RUN_TEST(test_can_vcu_cmd);
    RUN_TEST(test_swr_016_031_skipped_counter);
    RUN_TEST(test_swr_016_031_bad_checksum);
    RUN_TEST(test_swr_017);
    RUN_TEST(test_swr_018);
    RUN_TEST(test_swr_019);
        RUN_TEST(test_determinism);
    RUN_TEST(test_swr_030_comm_loss_contactor_handling);
    RUN_TEST(test_swr_030_reset);
    RUN_TEST(test_counter_wrap);
    RUN_TEST(test_counter_resync);
    RUN_TEST(test_swr_019_escalation);
return UNITY_END();
}
