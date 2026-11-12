"""Observable catalog evidence must never mutate or expose private source payloads."""
import json, threading, time, unittest
from unittest.mock import patch

class CatalogActivityTests(unittest.TestCase):
 def activity(self):
  from tools import catalog_activity
  return catalog_activity.CatalogActivity()
 def catalog(self, count=60):
  return dict(voices=[dict(id=f'voice-{i}',name=f'Voice {i}',referenceText='PRIVATE TRANSCRIPT',source='/private/source',referenceSHA256=f'{i:064x}') for i in range(count)])
 def test_first_snapshot_labels_existing_voices_as_observed_not_added(self):
  activity=self.activity();catalog=self.catalog();original=json.dumps(catalog)
  activity.observe(catalog,now=10)
  result=activity.snapshot()
  self.assertEqual(result['count'],60);self.assertEqual(len(result['voices']),60)
  self.assertEqual(result['checkedAt'],10)
  self.assertEqual({e['kind'] for e in result['events']},{'observed'})
  self.assertEqual(json.dumps(catalog),original)
  self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('/private',json.dumps(result))
 def test_add_change_and_missing_are_timestamped_observations_without_erasing_history(self):
  activity=self.activity();catalog=self.catalog(2);activity.observe(catalog,now=10)
  catalog['voices'][0]['referenceText']='Changed private words'
  catalog['voices'].append(dict(id='new',name='New Voice',referenceText='Secret words'))
  activity.observe(catalog,now=20);activity.observe(catalog,now=30)
  result=activity.snapshot()
  self.assertEqual([e['kind'] for e in result['events']],['observed','observed','changed','added'])
  self.assertEqual(result['lastChangedAt'],20);self.assertEqual(result['checkedAt'],30)
  self.assertEqual(result['voices'][0]['firstObservedAt'],10)
  catalog['voices'].pop(1);activity.observe(catalog,now=40)
  self.assertEqual(activity.snapshot()['events'][-1]['kind'],'missing')
  self.assertEqual(activity.snapshot()['count'],2)
  self.assertNotIn('Secret',json.dumps(activity.snapshot()))
 def test_failure_keeps_last_verified_list_and_redacts_untrusted_labels(self):
  activity=self.activity();catalog=self.catalog(1)
  for label in ['/Users/me/private.wav',r'C:\Users\secret', 'token=secret', 'Bearer secret', 'line\nprivate', 'https://private/?key=secret']:
   catalog['voices'][0]['name']=label;activity.observe(catalog,now=10)
   self.assertEqual(activity.snapshot()['voices'][0]['name'],'Name hidden')
  activity.failed()
  result=activity.snapshot();self.assertEqual(result['state'],'unavailable');self.assertEqual(result['count'],1)
  self.assertEqual(result['checkedAt'],10)
 def test_bounds_duplicate_ids_and_copies(self):
  activity=self.activity();activity.observe(self.catalog(1000),now=10)
  self.assertEqual(len(activity.snapshot()['events']),160)
  result=activity.snapshot();result['voices'].clear()
  self.assertEqual(activity.snapshot()['count'],1000)
  for catalog in [self.catalog(1001),dict(voices=[dict(id='same',name='One'),dict(id='same',name='Two')])]:
   with self.assertRaises(ValueError):activity.observe(catalog)
  self.assertEqual(activity.snapshot()['count'],1000)
 def test_background_check_returns_immediately_and_cannot_overlap(self):
  activity=self.activity();entered=threading.Event();release=threading.Event();finished=threading.Event();calls=[]
  def source():
   calls.append(1);entered.set();release.wait(3);return self.catalog(1)
  with patch('tools.catalog_activity.time.monotonic',return_value=100):
   activity.refresh(source);self.assertTrue(entered.wait(1))
   self.assertEqual(activity.snapshot()['state'],'checking')
   activity.refresh(source);self.assertEqual(len(calls),1)
   release.set()
   deadline=time.time()+2
   while activity.snapshot()['state']=='checking' and time.time()<deadline:time.sleep(.01)
   self.assertEqual(activity.snapshot()['state'],'current');activity.refresh(source)
   self.assertEqual(len(calls),1)
 def test_long_unicode_names_cannot_overflow_combined_phone_snapshot_limit(self):
  activity=self.activity();catalog=self.catalog(1000)
  for row in catalog['voices']:row['name']='🎙'*120
  activity.observe(catalog,now=1700000000.123456)
  self.assertTrue(all(row['name']=='Name hidden' for row in activity.snapshot()['voices']))
  for row in catalog['voices']:row['name']='🎙'*40
  activity.observe(catalog,now=1700000001.123456)
  from tools.workflow_activity import MESSAGES
  stage=max(MESSAGES,key=lambda key:len(MESSAGES[key]))
  event=dict(sequence=999999999999999,time=1700000000.123456,stage=stage,message=MESSAGES[stage],attempt=1000000,completed=1000000,total=1000000)
  video=dict(id='SYNTHETIC00',status='awaiting-preparation',progress=0.123456789,updated=1700000000.123456,attempts=1000000,nextAttempt=1700000000.123456,workerLeaseUntil=1700000000.123456,workerActive=False,historyAvailable=False,currentStage=stage,currentStageAt=1700000000.123456,lastEventAt=1700000000.123456,events=[event]*20)
  response=dict(schemaVersion=1,observedAt=1700000000.123456,videos=[video]*200,catalog=activity.snapshot())
  self.assertLess(len(json.dumps(response).encode()),2*1024*1024)
