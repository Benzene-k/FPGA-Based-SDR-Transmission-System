import argparse
import logging
import sys

from .protocol import Message
from .serial_client import SerialClient, LinkError


def main():
    parser = argparse.ArgumentParser(description="FPGA 独立串口通信验证；不控制基带算法")
    parser.add_argument("--port", help="例如 COM5；不会自动向枚举到的串口发命令")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--verbose", action="store_true", help="记录原始 TX/RX 十六进制")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ports", help="只扫描串口")
    ping = sub.add_parser("ping", help="验证 PING/PONG")
    ping.add_argument("--count", type=int, default=1)
    for command in ("start", "stop", "reset"):
        sub.add_parser(command, help="独立通信模块的命令确认；尚未绑定基带")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(message)s")
    if args.command == "ports":
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        for port in ports:
            print("{}  {}  {}".format(port.device, port.description, port.hwid))
        if not ports:
            print("未检测到 COM 口。")
        return 0
    if not args.port:
        parser.error("需要 --port COM号")
    if args.command == "ping" and not 1 <= args.count <= 10000:
        parser.error("--count 范围为 1..10000")
    client = SerialClient()
    try:
        client.open(args.port, args.baud)
        info = client.ping(timeout=args.timeout)
        if args.command == "ping":
            for _ in range(args.count - 1):
                info = client.ping(timeout=args.timeout)
            print("PING/PONG {}/{}  协议={}.{}  COMM_ONLY={}  请求运行状态={}".format(args.count, args.count, info.major, info.minor, info.comm_only, info.requested_running))
        else:
            kind = {"start": Message.START, "stop": Message.STOP, "reset": Message.RESET}[args.command]
            state = client.control(kind, timeout=args.timeout)
            print("{} ACK 已收到；请求运行状态={}。COMM_ONLY={}，不代表基带实验已启动。".format(args.command.upper(), state, info.comm_only))
        return 0
    except (LinkError, OSError, ValueError) as exc:
        print("通信失败：{}".format(exc), file=sys.stderr)
        return 2
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
