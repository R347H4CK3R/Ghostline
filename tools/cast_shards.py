"""Partition pending preview work without duplicating completed characters."""
import hashlib,json,pathlib,shutil

def prepare(root,count=2):
 root=pathlib.Path(root)
 if count not in (1,2):raise ValueError('Use one or two workers')
 manifest=json.loads((root/'references/manifest.json').read_text())
 state=json.loads((root/'job-state.json').read_text())
 completed={row['id'] for row in state['completed']}
 pending=[p for p in manifest['profiles'] if p['id'] not in completed]
 if len({p['id'] for p in manifest['profiles']})!=len(manifest['profiles']):raise ValueError('Duplicate profile IDs')
 buckets=[[] for _ in range(count)];loads=[0]*count
 for profile in sorted(pending,key=lambda p:p.get('referenceSeconds',0),reverse=True):
  slot=loads.index(min(loads));buckets[slot].append(profile);loads[slot]+=profile.get('referenceSeconds',0)
 destinations=[]
 for i,profiles in enumerate(buckets):
  destination=root/('shard-'+str(i+1))
  if destination.exists():raise ValueError('Shard exists; resume it rather than repartitioning')
  destinations.append(destination)
 # Validate all inputs before creating any shard.
 for profile in pending:
  source=root/'references'/profile['file']
  if hashlib.sha256(source.read_bytes()).hexdigest()!=profile['referenceSHA256']:raise ValueError('Invalid reference '+profile['id'])
 for destination,profiles in zip(destinations,buckets):
  references=destination/'references';references.mkdir(parents=True)
  for profile in profiles:
   shutil.copyfile(root/'references'/profile['file'],references/profile['file'])
   private=root/'references'/(profile['id']+'.private.json')
   if private.exists():shutil.copyfile(private,references/private.name)
  (references/'manifest.json').write_text(json.dumps(dict(manifest,profiles=profiles),indent=2))
 return [dict(directory=str(p),candidates=len(b),referenceSeconds=seconds) for p,b,seconds in zip(destinations,buckets,loads)]
