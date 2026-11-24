from pathlib import Path
p=Path('/home/boxd/trial/lattice-review/src/lattice/scheduler/fair.py')
text=p.read_text()
old='    estimated_work: int = 0\n\n\n@dataclass(eq=False)\nclass Permit:'
new='    estimated_work: int = 0\n    permit: "Permit | None" = None\n\n\n@dataclass(eq=False)\nclass Permit:'
assert text.count(old)==1
text=text.replace(old,new)
old='self.release()  # cancellation after ownership was handed off'
assert text.count(old)==1
text=text.replace(old,'self.release(waiter.permit)  # release this exact cancelled grant')
old='        self._holders.append(new_permit)\n        chosen.future.set_result(new_permit)'
assert text.count(old)==1
text=text.replace(old,'        chosen.permit = new_permit\n        self._holders.append(new_permit)\n        chosen.future.set_result(new_permit)')
p.write_text(text)
print('Patched precise cancellation ownership in the isolated test checkout')
