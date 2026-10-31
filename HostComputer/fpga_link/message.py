import binascii

MAX_MESSAGE_BYTES = 256
PREFIX = bytes.fromhex('aaaa d391c5a7')
VERSION = 1


def encode_text(text):
    if not isinstance(text, str):
        raise TypeError('text must be str')
    payload = text.encode('utf-8', errors='strict')
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError('UTF-8 message exceeds 256 bytes; do not truncate characters')
    return payload


def decode_text(payload):
    if not isinstance(payload, bytes):
        raise TypeError('payload must be bytes')
    return payload.decode('utf-8', errors='strict')


def encode_packet(payload, sequence):
    if not isinstance(payload, bytes):
        raise TypeError('payload must be bytes')
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError('message exceeds 256 bytes')
    if type(sequence) is not int or not 0 <= sequence <= 65535:
        raise ValueError('sequence must be an unsigned 16-bit integer')
    body = bytes((VERSION,)) + sequence.to_bytes(2, 'big')
    body += len(payload).to_bytes(2, 'big') + payload
    checksum = binascii.crc_hqx(body, 0xffff)
    return PREFIX + body + checksum.to_bytes(2, 'big')


def decode_packet(packet):
    if not isinstance(packet, bytes):
        raise TypeError('packet must be bytes')
    if len(packet) < 13 or packet[:6] != PREFIX or packet[6] != VERSION:
        raise ValueError('invalid message prefix or version')
    length = int.from_bytes(packet[9:11], 'big')
    if length > MAX_MESSAGE_BYTES or len(packet) != 13 + length:
        raise ValueError('invalid message byte length')
    if binascii.crc_hqx(packet[6:-2], 0xffff) != int.from_bytes(packet[-2:], 'big'):
        raise ValueError('message CRC mismatch')
    return int.from_bytes(packet[7:9], 'big'), packet[11:-2]
