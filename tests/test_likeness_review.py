import unittest
from tools.likeness_review import decide,new_reference

class ReviewTests(unittest.TestCase):
 def test_acceptance_also_requires_engine_checks(self):
  r=decide({'id':'one'},True,'Chris','a'*64,'b'*64,['Cartoons'])
  self.assertTrue(r['libraryApproved']);self.assertFalse(r['usable'])
 def test_rejected_voice_waits_for_different_reference(self):
  r=decide({'id':'one'},False,'Chris','a'*64,'b'*64,[])
  self.assertEqual(new_reference(r,'a'*64)['reviewStatus'],'waiting-for-better-reference')
  self.assertEqual(new_reference(r,'c'*64)['reviewStatus'],'retry-queued')
 def test_new_reference_requires_review_again(self):
  r=decide({'id':'one','engineVerified':True,'audioChecksPassed':True},True,'Chris','a'*64,'b'*64,['Cartoons'])
  self.assertTrue(r['usable']);self.assertFalse(new_reference(r,'c'*64)['usable'])

if __name__=='__main__':unittest.main()
