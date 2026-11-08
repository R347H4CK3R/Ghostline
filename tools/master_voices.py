"""Scan an expanding master folder without treating previews as working models."""
import hashlib,json,pathlib
from tools.voice_pack import validate_pack

def scan(directory):
 root=pathlib.Path(directory).resolve()
 if not root.is_dir():raise ValueError('Choose an existing Voices folder')
 profiles={};errors=[]
 for path in sorted(root.rglob('*.vmpack')):
  try:
   if path.is_symlink() or root not in path.resolve().parents:raise ValueError('Voice file is outside the selected folder')
   metadata=validate_pack(path);identifier=metadata['id']
   revision=hashlib.sha256(path.read_bytes()).hexdigest()
   if identifier in profiles:raise ValueError('Repeated voice ID: '+identifier)
   profiles[identifier]=dict(id=identifier,name=metadata['name'],categories=metadata['categories'],engine=metadata['engine'],revision=revision,file=str(path.relative_to(root)),nativeIOSVerified=False)
  except (ValueError,OSError) as error:errors.append(dict(file=str(path.relative_to(root)),error=str(error)))
 # A conflicting collection must be repaired before publishing its index.
 return dict(schemaVersion=1,status='ready' if not errors else 'needs-repair',voices=list(profiles.values()),errors=errors)

def compare(previous,current):
 if current['status']!='ready':raise ValueError('Repair invalid or conflicting voices before updating')
 old={v['id']:v for v in previous.get('voices',[])};new={v['id']:v for v in current['voices']}
 return dict(added=sorted(new.keys()-old.keys()),updated=sorted(k for k in new.keys()&old.keys() if new[k]['revision']!=old[k]['revision']),missing=sorted(old.keys()-new.keys()))
