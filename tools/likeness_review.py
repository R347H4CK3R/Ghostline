"""Explicit listening decisions; automated word checks never approve likeness."""
from copy import deepcopy

def decide(profile,matches,reviewer,reference_sha256,generated_sha256,categories):
 if type(matches) is not bool or not reviewer.strip():raise ValueError('A listening decision and reviewer are required')
 for digest in [reference_sha256,generated_sha256]:
  if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Invalid audio checksum')
 if matches and (not categories or any(not isinstance(c,str) or not c.strip() for c in categories)):raise ValueError('Choose a category before approving')
 result=deepcopy(profile)
 result.update(likenessReview=dict(matches=matches,reviewer=reviewer,referenceSHA256=reference_sha256,generatedSHA256=generated_sha256),reviewStatus='accepted' if matches else 'waiting-for-better-reference',categories=list(dict.fromkeys(categories)) if matches else profile.get('categories',[]),libraryApproved=matches)
 # Native engine/audio validation remains a separate condition for usability.
 result['usable']=matches and profile.get('engineVerified') is True and profile.get('audioChecksPassed') is True
 return result

def new_reference(profile,reference_sha256):
 if len(reference_sha256)!=64 or any(c not in '0123456789abcdef' for c in reference_sha256):raise ValueError('Invalid audio checksum')
 result=deepcopy(profile)
 if profile.get('likenessReview',{}).get('referenceSHA256')==reference_sha256:return result
 result.update(reviewStatus='retry-queued',libraryApproved=False,usable=False,referenceSHA256=reference_sha256)
 return result
