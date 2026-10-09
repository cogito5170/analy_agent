import math
from .model import PlantConfig

class AnalyticCellModel:
    def __init__(self):
        self.soc = 1.0
        self.v_rc = 0.0
        self.temp = PlantConfig.T_amb
        
    def step_exact(self, i_pack, dt):
        """
        Advances the state exactly for a piecewise-constant current `i_pack` over duration `dt`.
        """
        # 1. Exact SOC
        soc_new = self.soc - (i_pack * dt) / (PlantConfig.Q_cap * 3600.0)
        
        # 2. Exact v_rc
        tau_rc = PlantConfig.R1 * PlantConfig.C1
        v_rc_inf = i_pack * PlantConfig.R1
        v_rc_new = self.v_rc * math.exp(-dt / tau_rc) + v_rc_inf * (1.0 - math.exp(-dt / tau_rc))
        
        # 3. Exact Temperature
        # Simplified heat: I^2 * R0
        tau_th = PlantConfig.R_th * PlantConfig.C_th
        q_dot = i_pack**2 * PlantConfig.R0
        t_inf = PlantConfig.T_amb + q_dot * PlantConfig.R_th
        temp_new = self.temp * math.exp(-dt / tau_th) + t_inf * (1.0 - math.exp(-dt / tau_th))
        
        # Update state
        self.soc = soc_new
        self.v_rc = v_rc_new
        self.temp = temp_new

    def get_voltage(self, i_pack):
        return PlantConfig.ocv(self.soc) - i_pack * PlantConfig.R0 - self.v_rc

class AnalyticPackModel:
    def __init__(self):
        self.cells = [AnalyticCellModel() for _ in range(4)]
        self.i_pack = 0.0
        
    def step_exact(self, i_pack, dt):
        self.i_pack = i_pack
        for cell in self.cells:
            cell.step_exact(i_pack, dt)
            
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
