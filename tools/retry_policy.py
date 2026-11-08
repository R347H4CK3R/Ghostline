"""Initial attempt plus three retries, preserving explicit failure reasons."""
def attempt_with_retries(operation,previous=None,on_attempt=None):
 attempts=list(previous or [])
 if len(attempts)>4 or any(row.get('attempt')!=i+1 or type(row.get('passed')) is not bool for i,row in enumerate(attempts)):raise ValueError('Invalid saved attempts')
 for row in attempts:
  if row['passed']:return dict(passed=True,attempts=attempts,selected=row,reason=None)
 for index in range(len(attempts),4):
  try:
   result=operation(index)
   if not isinstance(result,dict) or type(result.get('passed')) is not bool:raise ValueError('Stage returned no validation result')
   row=dict(result,attempt=index+1)
   if not row['passed']:row['reason']=str(row.get('reason') or 'Output did not pass required checks')
  except Exception as error:
   row=dict(attempt=index+1,passed=False,reason=str(error) or type(error).__name__,errorType=type(error).__name__)
  attempts.append(row)
  if on_attempt:on_attempt(attempts)
  if row['passed']:return dict(passed=True,attempts=attempts,selected=row,reason=None)
 return dict(passed=False,attempts=attempts,selected=None,reason='All four attempts failed. '+attempts[-1]['reason'])
