import math

class PlantConfig:
    # Design assumptions (no datasheet claims)
    Q_cap = 100.0       # Ah
    R0 = 0.002          # Ohm
    R1 = 0.005          # Ohm
    C1 = 2000.0         # F
    C_th = 500.0        # J/K
    R_th = 2.0          # K/W
    T_amb = 25.0        # C
    
    @staticmethod
    def ocv(soc):
        # Design assumption for OCV curve
        return 3.0 + 1.2 * soc

class DiscreteCellModel:
    def __init__(self):
        self.soc = 1.0
        self.v_rc = 0.0
        self.temp = PlantConfig.T_amb
        
        # Fault injection states
        self.stuck_voltage = None
        self.sensor_offset = 0.0
        self.temp_ramp_rate = 0.0 # K/s
        
    def step_10ms(self, i_pack):
        dt = 0.01
        
        # 1. True SOC update
        self.soc -= (i_pack * dt) / (PlantConfig.Q_cap * 3600.0)
        
        # 2. RC branch update (Forward Euler)
        self.v_rc += dt * (i_pack / PlantConfig.C1 - self.v_rc / (PlantConfig.R1 * PlantConfig.C1))
        
        # 3. Thermal update (Forward Euler)
        # Heat generation: I^2 * R0 + v_rc^2 / R1
        q_dot = i_pack**2 * PlantConfig.R0
        self.temp += dt * (q_dot / PlantConfig.C_th - (self.temp - PlantConfig.T_amb) / (PlantConfig.R_th * PlantConfig.C_th))
        
        # Fault injection: temperature ramp
        if self.temp_ramp_rate != 0.0:
            self.temp += self.temp_ramp_rate * dt
            
    def get_voltage(self, i_pack):
        if self.stuck_voltage is not None:
            return self.stuck_voltage
        v_true = PlantConfig.ocv(self.soc) - i_pack * PlantConfig.R0 - self.v_rc
        return v_true + self.sensor_offset

class DiscretePackModel:
    def __init__(self):
        self.cells = [DiscreteCellModel() for _ in range(4)]
        self.i_pack = 0.0
        
    def step_10ms(self, i_pack):
        self.i_pack = i_pack
        for cell in self.cells:
            cell.step_10ms(i_pack)
            
    def get_outputs(self):
        voltages = [cell.get_voltage(self.i_pack) for cell in self.cells]
        temperatures = [cell.temp for cell in self.cells]
        true_socs = [cell.soc for cell in self.cells]
        return {
            "cell_voltages": voltages,
            "cell_temperatures": temperatures,
            "pack_current": self.i_pack,
            "true_socs": true_socs
        }

    # Fault injection API
    def inject_voltage_stuck(self, cell_idx, voltage):
        self.cells[cell_idx].stuck_voltage = voltage
        
    def inject_sensor_offset(self, cell_idx, offset):
        self.cells[cell_idx].sensor_offset = offset
        
    def inject_temperature_ramp(self, cell_idx, ramp_rate):
        self.cells[cell_idx].temp_ramp_rate = ramp_rate

