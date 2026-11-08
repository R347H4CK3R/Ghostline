"""Initial attempt plus three retries, preserving explicit failure reasons."""
def attempt_with_retries(operation):
 attempts=[]
 for index in range(4):
  try:
   result=operation(index)
   if not isinstance(result,dict) or type(result.get('passed')) is not bool:raise ValueError('Stage returned no validation result')
   row=dict(result,attempt=index+1)
   if not row['passed']:row['reason']=str(row.get('reason') or 'Output did not pass required checks')
  except Exception as error:
   row=dict(attempt=index+1,passed=False,reason=str(error) or type(error).__name__,errorType=type(error).__name__)
  attempts.append(row)
  if row['passed']:return dict(passed=True,attempts=attempts,selected=row,reason=None)
 return dict(passed=False,attempts=attempts,selected=None,reason='All four attempts failed. '+attempts[-1]['reason'])
