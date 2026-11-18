import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from simulation import Simulation
from control import Supervisor,MIN_GREEN,MAX_GREEN,YELLOW,CLEAR


class Safety(unittest.TestCase):
    def test_extreme_plans(self):
        for plan in (-4,200):
            supervisor=Supervisor()
            transitions=[]
            for t in range(1,220):
                stage,axis,start=supervisor.stage,supervisor.axis,supervisor.start
                supervisor.advance(t,plan,0)
                if stage!=supervisor.stage:
                    transitions.append(supervisor.stage)
                    if stage=="green":
                        self.assertLessEqual(MIN_GREEN,t-start)
                        self.assertLessEqual(t-start,MAX_GREEN)
                    elif stage=="yellow":
                        self.assertEqual(t-start,YELLOW)
                    else:
                        self.assertEqual(t-start,CLEAR)
                        self.assertNotEqual(axis,supervisor.axis)
            self.assertEqual(transitions[:6],["yellow","clear","green"]*2)


class Corridor(unittest.TestCase):
    def test_live(self):
        sim=Simulation()
        self.addCleanup(sim.close)
        links=set()
        stages=set()
        plans=set()
        for tick in range(170):
            if tick in (35,65,80,95,110):
                sim.action={35:"cross",65:"offline",80:"slow",95:"block",110:"normal"}[tick]
                sim.target="C"
            frame=sim.tick()
            for p in frame["predictions"]:
                links.add(p["source"]+p["destination"])
            for s,obs in frame["signals"].items():
                if sim.action=="offline" and s==sim.target:
                    self.assertFalse(obs["incoming"])
                if obs["stage"]=="green":
                    stages.add((s,obs["axis"]))
                    plans.add(obs["approved"])
                for axis,lamp in zip(sim.axes[s],obs["state"]):
                    if lamp.lower()=="g":
                        self.assertEqual(axis,obs["axis"])
                        self.assertEqual(obs["stage"],"green")
        self.assertTrue({"AB","BC","CD"}<=links)
        self.assertEqual(len(stages),8)
        self.assertGreater(len(plans),2)
        self.assertGreater(frame["completed"],0)


if __name__=="__main__":
    unittest.main()
