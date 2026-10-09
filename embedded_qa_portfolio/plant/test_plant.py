import unittest
import csv
import os
from plant.model import DiscretePackModel
from plant.analytic_reference import AnalyticPackModel

class TestPlantModel(unittest.TestCase):
    def run_profile(self, profile_name, steps):
        """
        steps is a list of (current_A, duration_s)
        """
        discrete_model = DiscretePackModel()
        analytic_model = AnalyticPackModel()
        
        csv_filename = os.path.join(os.path.dirname(__file__), f"b2b_{profile_name}.csv")
        
        max_diff = 0.0
        
        with open(csv_filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time_s", "current_A", "v_discrete_0", "v_analytic_0", "diff_mV"])
            
            t = 0.0
            for i_pack, duration in steps:
                # Number of 10ms steps
                num_steps = int(duration / 0.01)
                for _ in range(num_steps):
                    discrete_model.step_10ms(i_pack)
                    # Analytic model steps by 10ms for direct comparison at each step
                    analytic_model.step_exact(i_pack, 0.01)
                    t += 0.01
                    
                    v_discrete = discrete_model.get_outputs()["cell_voltages"][0]
                    v_analytic = analytic_model.get_outputs()["cell_voltages"][0]
                    
                    diff_mv = abs(v_discrete - v_analytic) * 1000.0
                    if diff_mv > max_diff:
                        max_diff = diff_mv
                        
                    # Write roughly every 1s to save space
                    if abs(t - round(t)) < 0.005 and round(t) % 1 == 0:
                        writer.writerow([round(t, 2), i_pack, v_discrete, v_analytic, diff_mv])
                        
        return max_diff

    def test_b2b_profiles(self):
        profiles = {
            "1c_discharge": [(100.0, 3600.0)],
            "pulse": [(50.0, 10.0), (0.0, 10.0), (-50.0, 10.0), (0.0, 10.0)] * 10,
            "charge_rest": [(-50.0, 1800.0), (0.0, 1800.0)]
        }
        
        report_lines = ["# Back-to-Back Test Report\n", "| Profile | Max Diff (mV) | Limit (mV) | Pass |", "|---|---|---|---|"]
        
        all_passed = True
        
        for name, steps in profiles.items():
            max_diff = self.run_profile(name, steps)
            passed = "Yes" if max_diff <= 5.0 else "No"
            report_lines.append(f"| {name} | {max_diff:.3f} | 5.0 | {passed} |")
            if max_diff > 5.0:
                all_passed = False
                
        report_path = os.path.join(os.path.dirname(__file__), "b2b_report.md")
        with open(report_path, "w") as f:
            f.write("\n".join(report_lines) + "\n")
            
        self.assertTrue(all_passed, "Max voltage difference exceeded 5 mV limit in at least one profile.")

    def test_fault_stuck_voltage(self):
        model = DiscretePackModel()
        model.inject_voltage_stuck(1, 4.5)
        out = model.get_outputs()
        self.assertEqual(out["cell_voltages"][1], 4.5)
        # Others should not be stuck (assuming init OCV is 4.2V)
        self.assertNotEqual(out["cell_voltages"][0], 4.5)

    def test_fault_sensor_offset(self):
        model = DiscretePackModel()
        out1 = model.get_outputs()["cell_voltages"][2]
        model.inject_sensor_offset(2, 0.1)
        out2 = model.get_outputs()["cell_voltages"][2]
        self.assertAlmostEqual(out2 - out1, 0.1)

    def test_fault_temperature_ramp(self):
        model = DiscretePackModel()
        model.inject_temperature_ramp(3, 1.0) # 1 K/s
        temp1 = model.get_outputs()["cell_temperatures"][3]
        for _ in range(100): # 1s
            model.step_10ms(0.0)
        temp2 = model.get_outputs()["cell_temperatures"][3]
        # temp should increase by roughly 1K, but there is also natural cooling to ambient.
        # Since temp starts at T_amb, cooling is 0. So exactly 1K.
        self.assertAlmostEqual(temp2 - temp1, 1.0, places=3)

if __name__ == '__main__':
    unittest.main()
