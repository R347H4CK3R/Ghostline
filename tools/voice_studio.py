"""Desktop companion entry point. Run python -m tools.voice_studio --help."""
import argparse,json,pathlib
from tools.voice_pack import export_reference_pack,validate_pack,export_collection_folder
from tools.pack_speech import speak
from tools.local_f5 import load_local_model

def main(argv=None):
 parser=argparse.ArgumentParser(description='VoiceMatrix offline desktop voice companion')
 commands=parser.add_subparsers(dest='command',required=True)
 create=commands.add_parser('create',help='Save an authorized reference as a reusable voice pack')
 create.add_argument('--audio',required=True);create.add_argument('--metadata',required=True);create.add_argument('--output',required=True)
 inspect=commands.add_parser('inspect',help='Validate pack integrity and show voice details');inspect.add_argument('pack')
 collection=commands.add_parser('export-folder',help='Export packs as a separate importable Voices collection folder')
 collection.add_argument('--output',required=True);collection.add_argument('packs',nargs='+')
 publish=commands.add_parser('publish-folder',help='Add voices to the master folder; preserve changed voices separately for review')
 publish.add_argument('--master',required=True);publish.add_argument('packs',nargs='+')
 audit=commands.add_parser('audit-training',help='Check whether clean recordings provide enough unique audio');audit.add_argument('dataset')
 training=commands.add_parser('train-rvc',help='Run the pinned local RVC training stages; outputs require independent conversion checks')
 for flag in ['root','dataset','experiment','permission']:training.add_argument('--'+flag,required=True)
 training.add_argument('--epochs',type=int,default=200)
 speech=commands.add_parser('speak',help='Generate WAV speech with the selected voice pack')
 for flag in ['pack','text','output','checkpoint','vocoder-directory','vocab']:speech.add_argument('--'+flag,required=True)
 args=parser.parse_args(argv)
 try:
  if args.command=='create':
   path=export_reference_pack(args.audio,json.loads(pathlib.Path(args.metadata).read_text()),args.output)
   print(json.dumps(dict(file=str(path),profile=validate_pack(path)),indent=2))
  elif args.command=='inspect':print(json.dumps(validate_pack(args.pack),indent=2))
  elif args.command=='export-folder':print(json.dumps(dict(folder=str(export_collection_folder(args.packs,args.output))),indent=2))
  elif args.command=='publish-folder':
   from tools.master_voices import publish
   print(json.dumps(publish(args.packs,args.master),indent=2))
  elif args.command=='audit-training':
   from tools.rvc_training import audit_dataset
   print(json.dumps(audit_dataset(args.dataset),indent=2))
  elif args.command=='train-rvc':
   from tools.rvc_training import train
   print(json.dumps(train(args.root,args.dataset,args.experiment,args.permission,epochs=args.epochs),indent=2))
  else:
   # Validate the selected pack and request before allocating large model weights.
   validate_pack(args.pack)
   if not args.text.strip() or len(args.text)>5000:raise ValueError('Enter 1–5000 characters')
   model=load_local_model(args.checkpoint,args.vocoder_directory,args.vocab)
   print(json.dumps(speak(args.pack,args.text,args.output,model),indent=2))
 except (ValueError,OSError) as error:parser.exit(2,str(error)+'\n')

if __name__=='__main__':main()
