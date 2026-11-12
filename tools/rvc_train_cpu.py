"""Run the exact pinned RVC CPU trainer directly, without DDP or a TCP port.

The existing run function and neural code are unchanged. DataLoader workers
still use spawn and remain inside the adapter's existing process containment.
"""
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import pathlib
import re
import sys

PINNED_SOURCE_SHA256 = '5e7d316962943935422ff225468ab22ac8dee30668131ba53728ed2e4efe78fd'
MODE = 'cpu-direct-no-ddp-v1'


def _arguments(training_args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-e', required=True)
    parser.add_argument('-g', required=True)
    args, _ = parser.parse_known_args(training_args)
    if args.g != '':
        raise ValueError('CPU launcher requires an explicitly empty -g value')
    if not re.fullmatch('[a-z0-9_-]{1,80}', args.e):
        raise ValueError('Unsafe experiment name')
    return args


def load_training_module(root, training_args):
    """Execute verified bytes as train.train; never invoke its __main__ block."""
    _arguments(training_args)
    root = pathlib.Path(root).resolve()
    source = root / 'train/train.py'
    if source.is_symlink() or source.resolve() != source:
        raise ValueError('Linked training source is unsupported')
    with source.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Pinned training source hash mismatch')
    normalized = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    normalized_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    if normalized_hash != PINNED_SOURCE_SHA256:
        raise ValueError('Pinned training source hash mismatch; training not imported')
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    sys.path.insert(0, str(root))
    sys.argv = [str(source), *training_args]
    package = importlib.import_module('train')
    if str(root / 'train') not in getattr(package, '__path__', ()):
        raise ValueError('Unexpected training package location')
    spec = importlib.util.spec_from_file_location('train.train', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules['train.train'] = module
    package.train = module
    # Compile the bytes just checked, rather than re-reading through a loader.
    exec(compile(normalized, str(source), 'exec'), module.__dict__)
    provenance = dict(mode=MODE, sourceFile=str(source), sourceModified=False,
                      rawSourceSHA256=hashlib.sha256(raw).hexdigest(),
                      normalizedSourceSHA256=normalized_hash,
                      adapterSHA256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
                      entrypoint='train.train.run(0, 1, hps, logger, False)',
                      arguments=list(training_args))
    return module, provenance


def run_cpu(module):
    """Let normal training exceptions escape directly to the subprocess exit."""
    if module.hps.gpus != '' or module.torch.cuda.is_available():
        raise ValueError('CPU launcher refuses GPU execution')
    module.mp.set_start_method('spawn', force=True)
    logger = module.utils.get_logger(module.hps.model_dir)
    return module.run(0, 1, module.hps, logger, False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('training_args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    training_args = args.training_args[1:] if args.training_args[:1] == ['--'] else args.training_args
    parsed = _arguments(training_args)
    root = pathlib.Path(args.root).resolve()
    os.chdir(root)
    module, provenance = load_training_module(root, training_args)
    experiment = root / 'logs' / parsed.e
    if experiment.resolve() != experiment or pathlib.Path(module.hps.model_dir).resolve() != experiment:
        raise ValueError('Unexpected training experiment destination')
    # Upstream intentionally calls os._exit(0) after its final save, so persist
    # source/entrypoint provenance before run. The parent verifies the actual
    # model immediately afterward and never treats this receipt as success.
    (experiment / 'voicematrix-train-adapter.json').write_text(
        json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    run_cpu(module)


if __name__ == '__main__':
    main()
