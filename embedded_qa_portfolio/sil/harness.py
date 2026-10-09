import ctypes
import os
import can
import json
from pathlib import Path
from plant.model import DiscretePackModel

# Load the shared library
lib_path = Path(__file__).parent / "bms_sil.so"
bms_lib = ctypes.CDLL(str(lib_path))

class BMS_Inputs(ctypes.Structure):
    _fields_ = [
        ("cell_mv", ctypes.c_uint16 * 4),
        ("temp_ddegc", ctypes.c_int16 * 2),
        ("current_ma", ctypes.c_int32),
        ("contactor_req", ctypes.c_bool),
    ]

class BMS_CAN_Frame(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("dlc", ctypes.c_uint8),
        ("data", ctypes.c_uint8 * 8),
    ]

class BMS_Outputs(ctypes.Structure):
    _fields_ = [
        ("contactor_close", ctypes.c_bool),
        ("state", ctypes.c_int32),
        ("faults", ctypes.c_uint8),
        ("can_tx", BMS_CAN_Frame * 4),
        ("can_tx_count", ctypes.c_uint8),
    ]

class BMS_State(ctypes.Structure):
    _fields_ = [
        ("state", ctypes.c_int32),
        ("faults", ctypes.c_uint8),
        ("contactor_closed", ctypes.c_bool),
        ("sig_cell_count", ctypes.c_uint8),
        ("sig_temp_count", ctypes.c_uint8),
        ("ov_count", ctypes.c_uint8),
        ("uv_count", ctypes.c_uint8),
        ("ot_count", ctypes.c_uint8),
        ("utc_count", ctypes.c_uint8),
        ("oc_count", ctypes.c_uint8),
        ("vcu_cmd_first", ctypes.c_bool),
        ("vcu_cmd_counter", ctypes.c_uint8),
        ("vcu_cmd_reject_count", ctypes.c_uint8),
        ("vcu_cmd_timer", ctypes.c_uint16),
        ("status_timer", ctypes.c_uint16),
        ("cellv_timer", ctypes.c_uint16),
        ("temp_timer", ctypes.c_uint16),
        ("fault_timer", ctypes.c_uint16),
        ("status_msg_counter", ctypes.c_uint8),
        ("fault_msg_counter", ctypes.c_uint8),
        ("low_current_count", ctypes.c_uint8),
    ]

bms_lib.bms_init.argtypes = [ctypes.POINTER(BMS_State)]
bms_lib.bms_step.argtypes = [ctypes.POINTER(BMS_State), ctypes.POINTER(BMS_Inputs), ctypes.POINTER(BMS_Outputs)]
bms_lib.bms_can_rx.argtypes = [ctypes.POINTER(BMS_State), ctypes.POINTER(BMS_Inputs), ctypes.POINTER(BMS_CAN_Frame)]

class VirtualCANBus:
    def __init__(self):
        self.bus = can.Bus(interface='virtual', channel='bms_sil', receive_own_messages=True)
    
    def send(self, msg):
        self.bus.send(msg)
        
    def recv(self, timeout=0):
        return self.bus.recv(timeout)

class SILHarness:
    def __init__(self, tc_id):
        self.tc_id = tc_id
        self.bms = BMS_State()
        self.inputs = BMS_Inputs()
        self.outputs = BMS_Outputs()
        bms_lib.bms_init(ctypes.byref(self.bms))
        
        self.plant = DiscretePackModel()
        self.bus = VirtualCANBus()
        self.time_ms = 0
        
        self.trace = []
        self.evidence_dir = Path("evidence") / self.tc_id
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # Fault injection queues
        self.faults = []

    def inject(self, fault_type, at_ms, duration_ms, **kwargs):
        self.faults.append({
            "type": fault_type,
            "start": at_ms,
            "end": at_ms + duration_ms,
            "params": kwargs,
            "active": False
        })

    def step_1ms(self):
        # 1. Apply faults for current time
        current = 0.0 # Pack current in Amps
        contactor_req = self.inputs.contactor_req
        
        # We need a way to track what faults are active
        active_faults = [f for f in self.faults if f["start"] <= self.time_ms < f["end"]]
        
        # Reset faults
        for i in range(4):
            self.plant.inject_voltage_stuck(i, None)
            self.plant.inject_sensor_offset(i, 0.0)
            self.plant.inject_temperature_ramp(i, 0.0)
            
        # Apply active faults to plant or inputs
        for f in active_faults:
            if f["type"] == "current_step":
                current = f["params"]["current_a"]
            elif f["type"] == "sensor_stuck":
                self.plant.inject_voltage_stuck(f["params"]["cell_idx"], f["params"]["voltage"])
            elif f["type"] == "sensor_offset":
                self.plant.inject_sensor_offset(f["params"]["cell_idx"], f["params"]["offset"])
            elif f["type"] == "temperature_ramp":
                self.plant.inject_temperature_ramp(f["params"]["cell_idx"], f["params"]["ramp_rate"])
            elif f["type"] == "can_loss":
                pass # Handled in rx

        # Plant steps every 10ms (but we call it per 10ms tick, wait, plant step_10ms expects 10ms dt)
        if self.time_ms % 10 == 0:
            self.plant.step_10ms(current)
            
        p_out = self.plant.get_outputs()
        
        # Map plant to inputs
        for i in range(4):
            self.inputs.cell_mv[i] = int(p_out["cell_voltages"][i] * 1000)
        for i in range(2):
            self.inputs.temp_ddegc[i] = int(p_out["cell_temperatures"][i] * 10)
        self.inputs.current_ma = int(current * 1000)

        # BMS steps every 10ms
        if self.time_ms % 10 == 0:
            bms_lib.bms_step(ctypes.byref(self.bms), ctypes.byref(self.inputs), ctypes.byref(self.outputs))
            
            # Send TX frames to virtual bus
            for i in range(self.outputs.can_tx_count):
                f = self.outputs.can_tx[i]
                msg = can.Message(arbitration_id=f.id, data=list(f.data)[:f.dlc], is_extended_id=False)
                self.bus.send(msg)

        # Record trace
        self.trace.append({
            "time_ms": self.time_ms,
            "state": self.bms.state,
            "faults": self.bms.faults,
            "contactor_close": self.outputs.contactor_close,
            "cell_mv": list(self.inputs.cell_mv),
            "temp_ddegc": list(self.inputs.temp_ddegc),
            "current_ma": self.inputs.current_ma
        })
        
        self.time_ms += 1

    def run(self, duration_ms):
        for _ in range(duration_ms):
            self.step_1ms()
            
    def save_trace(self):
        with open(self.evidence_dir / "trace.json", "w") as f:
            json.dump(self.trace, f)
        
