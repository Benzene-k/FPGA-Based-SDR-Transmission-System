from datetime import datetime,timezone
import json,os
from pathlib import Path


def bind_fresh_session(radio,registry):
    state=radio.boot_session()
    if state.bound:return state
    block = _reserve_blocks(registry, 1)
    return radio.bind_boot_session(0xad000000+(block<<8))


def _reserve_blocks(registry, count):
    registry=Path(registry).resolve()
    if not registry.is_file():raise FileNotFoundError('Use the existing authoritative session ledger: '+str(registry))
    lock=registry.with_suffix('.lock')
    fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        ledger=json.loads(registry.read_text(encoding='utf8'))
        block=ledger['next_block']
        first, limit = ledger.get('first_block', 1), ledger.get('limit_block', 65535)
        if (any(type(v) is not int for v in (block, first, limit, count))
                or not 1 <= first <= block < limit <= 65535 or count < 1 or block+count > limit):
            raise ValueError('Session ledger exhausted or invalid; obtain a new exclusive range')
        base=0xad000000+(block<<8)
        ledger['next_block']=block+count
        tmp=registry.with_suffix('.tmp')
        with tmp.open('w',encoding='utf8') as f:
            json.dump(ledger,f,indent=2);f.flush();os.fsync(f.fileno())
        tmp.replace(registry)
        with (registry.parent/'flash_session_allocations.jsonl').open('a',encoding='utf8') as f:
            f.write(json.dumps(dict(base=base,blocks=count,allocated_utc=datetime.now(timezone.utc).isoformat(),
                                   purpose='reserved before use; never roll back or clone allocator'))+'\n')
            f.flush();os.fsync(f.fileno())
    finally:
        os.close(fd);lock.unlink()
    return block


def reserve_session_range(authority, destination, count=256):
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Do not overwrite an existing session allocator: '+str(destination))
    if not destination.parent.is_dir():
        raise FileNotFoundError('Create the destination directory first')
    block = _reserve_blocks(authority, count)
    grant = dict(kind='sdr_session_range_v1', first_block=block,
                 next_block=block, limit_block=block+count)
    with destination.open('x', encoding='utf8') as stream:
        json.dump(grant, stream, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    return grant


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Reserve an exclusive session range for ONE other PC; no hardware access')
    parser.add_argument('--authority', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--blocks', type=int, default=256)
    args = parser.parse_args()
    print(json.dumps(reserve_session_range(args.authority, args.output, args.blocks), indent=2))


if __name__ == '__main__':
    main()
