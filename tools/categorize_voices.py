"""Add overlapping catalog categories without copying model/profile files.
Character tags describe the publisher's original roles; pitch tags are measured
from actual generated QA audio, not inferred from a profile name or reference.
"""
import argparse,importlib.util,json,pathlib
from acquire_reference_bank import median_pitch

def categorize(lock_path,phonon_qa,bank_artifacts):
 path=pathlib.Path(lock_path);lock=json.loads(path.read_text());original={}
 for wav in pathlib.Path(phonon_qa).glob('*.wav'):original[wav.stem]=wav
 bank={p.stem:p for p in pathlib.Path(bank_artifacts).rglob('bank-output/*.wav')}
 roles={
  'Azgorath':['Horror & Monsters','Fantasy & Characters'],
  'Captain Silas Blackwater':['Cinematic & Narration','Gaming Characters'],
  'Fairy Godmother':['Animation & Cartoon Styles','Fantasy & Characters'],
  'Fennick the Young Elf':['Animation & Cartoon Styles','Fantasy & Characters','Gaming Characters'],
  'Grub the Ogre':['Horror & Monsters','Animation & Cartoon Styles','Fantasy & Characters'],
  'Master Aldric':['Fantasy & Characters','Cinematic & Narration','Gaming Characters'],
  'Morwenna of the Deep':['Horror & Monsters','Fantasy & Characters'],
  'Old Mortlake':['Horror & Monsters','Cinematic & Narration'],
  'Sir Bramwell':['Fantasy & Characters','Gaming Characters','Cinematic & Narration'],
  'The Snow Queen':['Animation & Cartoon Styles','Fantasy & Characters'],
  'The Thing Under the Stairs':['Horror & Monsters','Fantasy & Characters'],
  'Vyrmathrax the Ancient':['Horror & Monsters','Fantasy & Characters','Gaming Characters']}
 counts={}
 for voice in lock['voices']:
  tags={voice['category'],'Original Voices'}
  if voice['id'].startswith('characters_'):tags.update(roles.get(voice['name'],['Fantasy & Characters']))
  elif voice['name']=='Wayfarer Merchant':tags.update(['Fantasy & Characters','Gaming Characters'])
  elif voice['engine']=='phonon31m':tags.add('Everyday & Conversation')
  else:tags.add('Everyday & Conversation')
  wav=(bank if voice['engine']=='phonon31m-openvoicev2' else original).get(voice['id'])
  pitch=median_pitch(wav) if wav else None
  if pitch is not None:
   voice['measuredPreviewPitchHz']=round(pitch,2)
   tags.add('Lower Voices' if pitch<165 else 'Higher Voices' if pitch>=220 else 'Midrange Voices')
  voice['categories']=sorted(tags)
  for tag in tags:counts[tag]=counts.get(tag,0)+1
 path.write_text(json.dumps(lock,indent=2)+'\n')
 pathlib.Path('models/category-audit.json').write_text(json.dumps(dict(uniqueProfiles=len(lock['voices']),categoryMemberships=counts,overlappingCategories=True,duplicateInferenceFilesCreated=0,pitchMethod='Median autocorrelation pitch measured from actual generated QA preview; not a quality or likeness score',characterTagBasis='Publisher-named original character roles; no official fictional-character identity or performer authorization implied'),indent=2)+'\n')
 print('Categorized',len(lock['voices']),'unique profiles:',counts)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--lock',default='models/phonon-lock.json');p.add_argument('--phonon-qa',required=True);p.add_argument('--bank-artifacts',required=True);a=p.parse_args();categorize(a.lock,a.phonon_qa,a.bank_artifacts)
