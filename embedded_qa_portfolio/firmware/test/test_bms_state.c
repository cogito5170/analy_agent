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
        {4250, 3, false},
        {4251, 2, false},
        {4251, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        in.cell_mv[0] = cases[i].mv;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_OV) != 0);
    }
}

/* @verifies SWR-006 */
static void test_uv_boundary_and_debounce(void)
{
    const struct { uint16_t mv; int steps; bool fault; } cases[] = {
        {2800, 3, false},
        {2799, 2, false},
        {2799, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        in.cell_mv[0] = cases[i].mv;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_UV) != 0);
    }
}

/* @verifies SWR-007 */
static void test_ot_boundary_and_debounce(void)
{
    const struct { int16_t dc; int steps; bool fault; } cases[] = {
        {600, 3, false},
        {601, 2, false},
        {601, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        in.temp_ddegc[0] = cases[i].dc;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_OT) != 0);
    }
}

/* @verifies SWR-008 */
static void test_utc_boundary_and_debounce(void)
{
    const struct { int16_t dc; int32_t ma; int steps; bool fault; } cases[] = {
        {0, -1000, 3, false},
        {-1, 0, 3, false},
        {-1, -1000, 2, false},
        {-1, -1000, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
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
        {150000, 3, false},
        {150001, 2, false},
        {150001, 3, true},
        {-50000, 3, false},
        {-50001, 2, false},
        {-50001, 3, true},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        setUp();
        in.current_ma = cases[i].ma;
        step_n(cases[i].steps);
        TEST_ASSERT_EQUAL(cases[i].fault, (out.faults & BMS_FAULT_OC) != 0);
    }
}

/* @verifies SWR-010 */
static void test_contactor_opens_on_fault_within_deadline(void)
{
    step_n(1);
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
    in.cell_mv[0] = 4251;
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
    return UNITY_END();
}
