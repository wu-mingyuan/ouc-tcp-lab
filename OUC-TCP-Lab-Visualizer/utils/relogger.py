import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class LogEvent:
    timestamp: datetime.datetime
    seq_num: int
    event_type: str  # 'SEND', 'ACK', 'RESEND'
    status: str  # 'ACKed', 'NO_ACK'
    error_type: Optional[str] = None  # 'WRONG', 'DELAY', 'LOSS'


def parse_line(line: str) -> Optional[LogEvent]:
    try:
        # 删除开头的制表符并分割
        line = line.strip()

        # 解析时间戳
        timestamp_str = line.split("CST")[0].strip()
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S:%f")

        # 解析剩余部分
        remaining = line.split("CST")[1].strip()

        # 判断事件类型
        if "DATA_seq" in remaining:
            # 处理发送方数据
            if remaining.startswith("*Re:"):
                event_type = "RESEND"
                seq_part = remaining.split("DATA_seq:")[1]
            else:
                event_type = "SEND"
                seq_part = remaining.split("DATA_seq:")[1]

            # 解析序列号和状态
            parts = seq_part.strip().split()
            seq_num = int(parts[0])

            # 检查是否有错误类型
            error_type = None
            if "WRONG" in parts:
                error_type = "WRONG"
            elif "DELAY" in parts:
                error_type = "DELAY"
            elif "LOSS" in parts:
                error_type = "LOSS"

            # 获取确认状态
            status = "ACKed" if "ACKed" in remaining else "NO_ACK"

        elif "ACK_ack" in remaining:
            # 处理接收方确认
            event_type = "ACK"
            seq_num = int(remaining.split("ACK_ack:")[1].split()[0])
            status = "ACK"
            error_type = None
            if "WRONG" in remaining:
                error_type = "WRONG"
            elif "DELAY" in remaining:
                error_type = "DELAY"
            elif "LOSS" in remaining:
                error_type = "LOSS"

        else:
            return None
        # if error_type is not None:
        #     print(f"Error: {error_type}, seq_num: {seq_num}")
        return LogEvent(
            timestamp=timestamp,
            seq_num=seq_num,
            event_type=event_type,
            status=status,
            error_type=error_type,
        )
    except Exception as e:
        print(f"Error parsing line: {line}")
        print(f"Error: {e}")
        return None


def parse_log(filename, bytes=False):
    events = []

    if not bytes:
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("发送方") or line.startswith("接收方"):
                    continue

                event = parse_line(line)
                if event:
                    events.append(event)
    else:
        file = filename.decode("utf-8")
        for line in file.split("\n"):
            line = line.strip()
            if not line or line.startswith("发送方") or line.startswith("接收方"):
                continue

            event = parse_line(line)
            if event:
                events.append(event)

    # 按时间排序
    events.sort(key=lambda x: x.timestamp)

    return events


def print_sorted_events(events):
    for event in events:
        # 格式化输出
        timestamp_str = event.timestamp.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]

        if event.event_type == "ACK":
            print(f"\t{timestamp_str} CST\tACK_ack: {event.seq_num}")
        else:
            prefix = "*Re: " if event.event_type == "RESEND" else ""
            error = f"\t{event.error_type}" if event.error_type else ""
            print(
                f"\t{timestamp_str} CST\t{prefix}DATA_seq: {event.seq_num}{error}\t{event.status}"
            )


def log_to_csv(filename, bytes=False):
    events = parse_log(filename, bytes)
    csv = "timestamp,seq_num,event_type,status,error_type\n"
    for event in events:
        timestamp_str = event.timestamp.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]
        error_type = event.error_type if event.error_type else ""
        # csv.append(
        #     f"{timestamp_str},{event.seq_num},{event.event_type},{event.status},{error_type}\n"
        # )
        csv += f"{timestamp_str},{event.seq_num},{event.event_type},{event.status},{error_type}\n"
    return csv
