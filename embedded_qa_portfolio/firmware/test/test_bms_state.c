/*
 * Unit tests for signal plausibility and the INIT/STANDBY/FAULT transitions.
 * Each test names the requirement it verifies with an @verifies tag, which the
 * traceability script reads.
 */
#include "bms.h"
#include "unity.h"

static bms_t bms;
static bms_inputs_t in;
static bms_outputs_t out;

void setUp(void)
{
    bms_init(&bms);
    for (int i = 0; i < BMS_NUM_CELLS; i++) {
        in.cell_mv[i] = 3700;
    }
    for (int i = 0; i < BMS_NUM_TEMPS; i++) {
        in.temp_ddegc[i] = 250;
    }
    in.current_ma = 0;
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
    while (out.state != BMS_STATE_STANDBY && steps * BMS_TASK_PERIOD_MS < BMS_INIT_DEADLINE_MS) {
        bms_step(&bms, &in, &out);
        steps++;
    }
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

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_init_reaches_standby_within_deadline);
    RUN_TEST(test_cell_signal_boundaries);
    RUN_TEST(test_temp_signal_boundaries);
    RUN_TEST(test_signal_fault_debounce);
    RUN_TEST(test_intermittent_signal_does_not_fault);
    RUN_TEST(test_fault_is_latched);
    return UNITY_END();
}
