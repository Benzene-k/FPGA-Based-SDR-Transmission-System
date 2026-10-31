import argparse
from pathlib import Path

from .protocol import Frame, FrameDecoder, Message, encode_frame

ROOT = Path(__file__).resolve().parents[1] / "fpga" / "communication"


def cases(pings=1000):
    result = []
    sequence = 0
    state = 0
    config = (30).to_bytes(2,"big")+(13).to_bytes(2,"big")+(20260919).to_bytes(4,"big")
    def command(kind, payload=b"", prefix=b"", damage_crc=False, bad_stop=False):
        nonlocal sequence, state, config
        request = encode_frame(Frame(kind, sequence, payload))
        if damage_crc:
            request = request[:-1] + bytes((request[-1] ^ 1,))
        if damage_crc or bad_stop:
            reply = b""
        elif kind in (0x30, 0x32):
            if (kind == 0x30 and payload) or (kind == 0x32 and len(payload) != 8):
                reply = encode_frame(Frame(Message.ERROR, sequence, bytes((kind, 2))))
            elif kind == 0x32:
                frame, sync, seed = int.from_bytes(payload[:2],'big'), int.from_bytes(payload[2:4],'big'), int.from_bytes(payload[4:],'big')
                if not (2 <= frame <= 4096 and 1 <= sync <= 1024 and sync < frame and seed <= 2147483647):
                    reply = encode_frame(Frame(Message.ERROR, sequence, bytes((kind, 3))))
                else:
                    config = payload
                    reply = encode_frame(Frame(0x31, sequence, config))
            else:
                reply = encode_frame(Frame(0x31, sequence, config))
        elif kind == Message.ECHO:
            reply = encode_frame(Frame(Message.ECHO_REPLY, sequence, payload))
        elif kind not in (Message.PING, Message.START, Message.STOP, Message.RESET):
            reply = encode_frame(Frame(Message.ERROR, sequence, bytes((kind, 1))))
        elif payload:
            reply = encode_frame(Frame(Message.ERROR, sequence, bytes((kind, 2))))
        elif kind == Message.PING:
            reply = encode_frame(Frame(Message.PONG, sequence, bytes((1, 2, 7, state))))
        else:
            state = int(kind == Message.START)
            reply = encode_frame(Frame(Message.ACK, sequence, bytes((kind, 0, state))))
        result.append((prefix + request, reply, int(bad_stop)))
        sequence = (sequence + 1) & 255
    command(Message.PING)
    command(Message.START)
    command(Message.PING)
    command(0x30)
    command(0x32, bytes.fromhex('10 00 04 00 7f ff ff ff'))
    command(0x30)
    for data in ('00 01 00 01 00 00 00 00','00 1e 00 1e 00 00 00 00','00 1e 00 01 80 00 00 00','10 01 00 01 00 00 00 00','10 00 04 01 00 00 00 00'):
        command(0x32, bytes.fromhex(data))
        command(0x30)
    command(0x32, b'bad')
    command(0x30, b'x')
    command(0x32, bytes.fromhex('00 80 00 10 00 00 00 07'), damage_crc=True)
    command(0x30)
    command(0x32, bytes.fromhex('00 02 00 01 00 00 00 00'))
    command(Message.RESET)
    command(0x30)
    command(Message.STOP)
    command(Message.START)
    command(Message.RESET)
    command(0x77)
    command(Message.PING, b"\xaa\x55")
    command(Message.PING, damage_crc=True)
    result.append((b"\xaa\x55\x01\x09\x01\x01", b"", 0))
    result.append((b"\xaa\x55\x01\x0a\x00", b"", 0))
    command(Message.PING, prefix=b"\x00\xaa\xaa")
    command(Message.PING, bad_stop=True)
    command(Message.PING, bytes(range(256)))
    for payload in (b"", b"x", "你好 FPGA".encode(), b"\x00\xaa\x55\xff", bytes(range(63)), bytes(range(255)), bytes(range(256))):
        command(Message.ECHO, payload)
    command(Message.ECHO, bytes(range(256)), damage_crc=True)
    command(Message.ECHO, b"after bad CRC")
    command(Message.PING)
    for _ in range(pings):
        command(Message.PING)
    return result


def generate(pings=1000):
    ROOT.mkdir(parents=True, exist_ok=True)
    vectors = cases(pings)
    with (ROOT / "uart_vectors.txt").open("w", encoding="ascii") as output:
        output.write(str(len(vectors)) + "\n")
        for request, reply, bad_stop in vectors:
            output.write("{} {} {}\n".format(len(request), len(reply), bad_stop))
            output.write(request.hex(" ") + "\n")
            output.write(reply.hex(" ") + "\n")
    print("Generated {} UART cases ({} repeated PINGs)".format(len(vectors), pings))


def verify(pings=1000):
    completed = int((ROOT / "completed_cases.txt").read_text(encoding="ascii").strip())
    vectors = cases(pings)[:completed]
    expected = b"".join(reply for _, reply, _ in vectors)
    actual = bytes.fromhex((ROOT / "uart_rx_dump.txt").read_text(encoding="ascii"))
    if actual != expected:
        raise AssertionError("RTL capture differs from Python vectors: {} vs {} bytes".format(len(actual), len(expected)))
    decoder = FrameDecoder()
    frames = decoder.feed(actual)
    if decoder.crc_errors or decoder.length_errors or len(frames) != sum(bool(reply) for _, reply, _ in vectors):
        raise AssertionError("Python decoder rejected RTL replies")
    print("UART INTEROP PASS: {} cases, {} replies, {} bytes, all CRC/SEQ/payload correct".format(completed, len(frames), len(actual)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("generate", "verify"))
    parser.add_argument("--pings", type=int, default=1000)
    args = parser.parse_args()
    (generate if args.action == "generate" else verify)(args.pings)
