import unittest
from tools.retry_policy import attempt_with_retries

class RetryTests(unittest.TestCase):
 def test_resume_does_not_repeat_completed_failures(self):
  seen=[]
  r=attempt_with_retries(lambda n:(seen.append(n) or dict(passed=True)),previous=[dict(attempt=1,passed=False,reason='Missing words')])
  self.assertEqual(seen,[1]);self.assertTrue(r['passed'])
 def test_completed_attempts_are_checkpointed(self):
  saved=[]
  r=attempt_with_retries(lambda n:dict(passed=n==1),on_attempt=lambda rows:saved.append(len(rows)))
  self.assertEqual(saved,[1,2])
 def test_finished_failure_does_not_retry_forever(self):
  r=attempt_with_retries(lambda n:self.fail('must not retry'),previous=[dict(attempt=i+1,passed=False,reason='No speech') for i in range(4)])
  self.assertFalse(r['passed'])
 def test_four_attempts_then_reason(self):
  def fail(n):raise ValueError('Reference has no intelligible speech')
  result=attempt_with_retries(fail)
  self.assertEqual(len(result['attempts']),4);self.assertFalse(result['passed'])
  self.assertIn('no intelligible speech',result['reason'])
 def test_stop_at_first_pass(self):
  r=attempt_with_retries(lambda n:dict(passed=n==2,reason='Missing words'))
  self.assertTrue(r['passed']);self.assertEqual(len(r['attempts']),3)
 def test_quality_failures_are_not_exceptions(self):
  r=attempt_with_retries(lambda n:dict(passed=False,reason='Word error rate 25% exceeds 10%'))
  self.assertEqual(len(r['attempts']),4);self.assertIn('25%',r['reason'])

if __name__=='__main__':unittest.main()
