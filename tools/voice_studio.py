"""Desktop companion entry point. Run python -m tools.voice_studio --help."""
import argparse,json,pathlib
from tools.voice_pack import export_reference_pack,validate_pack
from tools.pack_speech import speak
from tools.local_f5 import load_local_model

def main(argv=None):
 parser=argparse.ArgumentParser(description='VoiceMatrix offline desktop voice companion')
 commands=parser.add_subparsers(dest='command',required=True)
 create=commands.add_parser('create',help='Save an authorized reference as a reusable voice pack')
 create.add_argument('--audio',required=True);create.add_argument('--metadata',required=True);create.add_argument('--output',required=True)
 inspect=commands.add_parser('inspect',help='Validate pack integrity and show voice details');inspect.add_argument('pack')
 speech=commands.add_parser('speak',help='Generate WAV speech with the selected voice pack')
 for flag in ['pack','text','output','checkpoint','vocoder-directory','vocab']:speech.add_argument('--'+flag,required=True)
 args=parser.parse_args(argv)
 try:
  if args.command=='create':
   path=export_reference_pack(args.audio,json.loads(pathlib.Path(args.metadata).read_text()),args.output)
   print(json.dumps(dict(file=str(path),profile=validate_pack(path)),indent=2))
  elif args.command=='inspect':print(json.dumps(validate_pack(args.pack),indent=2))
  else:
   # Validate the selected pack and request before allocating large model weights.
   validate_pack(args.pack)
   if not args.text.strip() or len(args.text)>5000:raise ValueError('Enter 1–5000 characters')
   model=load_local_model(args.checkpoint,args.vocoder_directory,args.vocab)
   print(json.dumps(speak(args.pack,args.text,args.output,model),indent=2))
 except (ValueError,OSError) as error:parser.exit(2,str(error)+'\n')

if __name__=='__main__':main()
