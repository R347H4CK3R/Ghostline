import unittest
from pathlib import Path
class BuildScriptSyntaxTests(unittest.TestCase):
 def test_every_python_build_script_compiles(self):
  for path in (Path(__file__).parents[1]/'tools').glob('*.py'):
   with self.subTest(script=path.name): compile(path.read_text(),str(path),'exec')
