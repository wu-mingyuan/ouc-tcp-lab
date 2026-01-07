import random
import dash
from dash import dcc, html, Input, Output, State, no_update, callback_context
import numpy as np
import pandas as pd
import plotly.graph_objs as go
import datetime
from collections import deque
from utils.relogger import log_to_csv
import base64
import io
import bisect


# --------------------------
# 时间解析函数
# --------------------------
def parse_custom_time(timestamp_str):
    try:
        if pd.isna(timestamp_str):
            return pd.NaT

        date_part, time_part = timestamp_str.split(" ")
        year, month, day = map(int, date_part.split("-"))
        h, m, s, ms = map(int, time_part.split(":"))
        return datetime.datetime(year, month, day, h, m, s, ms * 1000)
    except Exception as e:
        print(f"时间解析错误：{timestamp_str} - {str(e)}")
        raise


# 全局状态存储
throughput_history = deque(maxlen=120)
error_buckets_global = {"WRONG": {}, "LOSS": {}, "DELAY": {}}
BASE_INTERVAL = 100

# --------------------------
# Dash 应用初始化
# --------------------------
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    [
        dcc.Upload(
            id="upload-data",
            children=html.Div(["拖放或 ", html.A("选择日志文件")]),
            style={
                "width": "100%",
                "height": "60px",
                "lineHeight": "60px",
                "borderWidth": "1px",
                "borderStyle": "dashed",
                "borderRadius": "5px",
                "textAlign": "center",
                "margin": "10px",
            },
        ),
        dcc.Store(id="data-store"),
        dcc.Store(id="play-state", data={"playing": False}),
        html.Div(
            [
                html.Button(
                    "▶️ 播放",
                    id="play-pause-button",
                    n_clicks=0,
                    style={"marginRight": "10px"},
                ),
                html.Div(
                    [
                        html.Label("播放速率：", style={"marginRight": "10px"}),
                        dcc.Slider(
                            id="rate-slider",
                            min=0.1,
                            max=1,
                            value=1,
                            step=0.1,
                            marks={i: f"{i}x" for i in [0.1, 0.25, 0.5, 1]},
                            tooltip={"always_visible": True},
                        ),
                    ],
                    style={"width": "300px", "display": "inline-block"},
                ),
                dcc.Slider(
                    id="time-slider",
                    min=0,
                    max=0,
                    value=0,
                    step=2,
                ),
                dcc.RangeSlider(
                    id="range-slider",
                    min=0,
                    max=0,
                    value=[0, 0],
                    step=5,
                ),
                dcc.Interval(
                    id="animation-interval", interval=BASE_INTERVAL, disabled=True
                ),
            ],
            style={
                "width": "85%",
                "margin": "20px auto",
                "padding": "10px",
                "border": "1px solid #ddd",
            },
        ),
        html.Div(
            [
                dcc.Graph(id="network-graph", style={"height": "500px"}),
                dcc.Graph(id="throughput-graph", style={"height": "300px"}),
            ]
        ),
    ]
)


# --------------------------
# 文件上传回调
# --------------------------
@app.callback(
    Output("data-store", "data"),
    [Input("upload-data", "contents")],
    prevent_initial_call=True,
)
def process_uploaded_data(contents):
    if contents is None:
        return no_update

    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)

    csv_lines = log_to_csv(decoded, bytes=True)
    df = pd.read_csv(io.StringIO(csv_lines), sep=",", encoding="utf-8")

    df["timestamp"] = df["timestamp"].apply(parse_custom_time)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df["rel_time"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds()

    # 预处理数据结构
    processed_data = {
        "times": df["rel_time"].tolist(),
        "records": df[
            ["rel_time", "seq_num", "event_type", "status", "error_type"]
        ].to_dict("records"),
    }

    global throughput_history, error_buckets_global
    throughput_history = deque(maxlen=120)
    error_buckets_global = {"WRONG": {}, "LOSS": {}, "DELAY": {}}

    return processed_data


# --------------------------
# 更新滑动条范围
# --------------------------
@app.callback(
    [
        Output("time-slider", "max"),
        Output("range-slider", "max"),
        Output("range-slider", "value"),
    ],
    [Input("data-store", "data")],
)
def update_slider_ranges(data):
    if not data or not data["times"]:
        return 0, 0, [0, 0]

    max_time = max(data["times"])
    return max_time, max_time, [0, max_time]


# --------------------------
# 播放控制回调
# --------------------------
@app.callback(
    [
        Output("animation-interval", "disabled"),
        Output("play-pause-button", "children"),
        Output("play-state", "data"),
    ],
    [Input("play-pause-button", "n_clicks")],
    [State("play-state", "data")],
)
def control_animation(n_clicks, play_state):
    if n_clicks is None:
        return no_update

    current_playing = play_state.get("playing", False)
    return (
        (False, "⏸ 暂停", {"playing": True})
        if not current_playing
        else (True, "▶️ 播放", {"playing": False})
    )


# --------------------------
# 速率控制回调
# --------------------------
@app.callback(Output("animation-interval", "interval"), [Input("rate-slider", "value")])
def update_animation_speed(rate):
    return int(BASE_INTERVAL / max(0.1, rate))


# --------------------------
# 主更新回调
# --------------------------
@app.callback(
    [
        Output("network-graph", "figure"),
        Output("throughput-graph", "figure"),
        Output("time-slider", "value"),
    ],
    [Input("animation-interval", "n_intervals"), Input("time-slider", "value")],
    [
        State("range-slider", "value"),
        State("play-state", "data"),
        State("data-store", "data"),
    ],
)
def update_animation(n_intervals, slider_time, time_range, play_state, data):
    if not data or not data["times"]:
        return no_update

    # 判断触发源
    ctx = callback_context
    if ctx.triggered:
        trigger_source = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_source == "time-slider" and play_state.get("playing", False):
            return no_update

    current_time = slider_time
    if play_state.get("playing", False):
        current_time = min(current_time + 0.1, time_range[1])
    current_time = max(min(current_time, time_range[1]), time_range[0])

    # 使用二分查找优化数据查询
    times = data["times"]
    records = data["records"]
    current_index = bisect.bisect_right(times, current_time)

    active_packets = []
    max_ack = 0

    for i in range(current_index):
        row = records[i]
        try:
            seq_num = int(row["seq_num"])
            event_type = row["event_type"]
            error_type = row.get("error_type", "")

            if event_type in ["SEND", "RESEND"]:
                packet = {
                    "seq_num": seq_num,
                    "start_time": row["rel_time"],
                    "end_time": row["rel_time"] + 0.5,
                    "direction": "to_receiver",
                    "type": event_type,
                    "status": row["status"],
                    "error_type": error_type,
                }
                active_packets.append(packet)

                # 处理错误包
                if error_type in error_buckets_global:
                    error_buckets_global[error_type][seq_num] = packet
            elif event_type == "ACK":
                active_packets.append(
                    {
                        "seq_num": seq_num,
                        "start_time": row["rel_time"],
                        "end_time": row["rel_time"] + 0.5,
                        "direction": "to_sender",
                        "type": "ACK",
                        "status": row["status"],
                        "error_type": error_type,
                    }
                )
                if seq_num > max_ack:
                    max_ack = seq_num
                    # 清理已确认的错误包
                    for et in error_buckets_global.values():
                        for seq in list(et.keys()):
                            if seq <= max_ack:
                                del et[seq]
                if error_type in error_buckets_global:
                    error_buckets_global[error_type][seq_num] = packet
        except Exception as e:
            print(f"处理数据包时出错：{str(e)}")
            continue

    # 计算吞吐率
    window_start = max(0, current_time - 1)
    acked_count = sum(
        1
        for r in records[:current_index]
        if r["status"] == "ACKed" and r["rel_time"] >= window_start
    )
    throughput = acked_count / 1.0

    if not throughput_history or (current_time - throughput_history[-1]["time"] >= 0.1):
        throughput_history.append({"time": current_time, "throughput": throughput})

    return (
        create_network_figure(current_time, active_packets),
        create_throughput_figure(),
        current_time,
    )


def create_network_figure(current_time, active_packets):
    fig = go.Figure()

    # 网络链路
    fig.add_trace(
        go.Scatter(
            x=[0, 10],
            y=[0, 0],
            mode="lines+markers",
            marker=dict(size=20, color="black"),
            line=dict(width=3, color="gray"),
        )
    )

    # 错误桶
    bucket_positions = {"WRONG": (2, -2), "LOSS": (5, -2), "DELAY": (8, -2)}
    for name, (x, y) in bucket_positions.items():
        fig.add_trace(
            go.Scatter(
                x=[x],
                y=[y],
                mode="text",
                text=name,
                textposition="top center",
            )
        )

        y_offset = y - 0.5
        for p in error_buckets_global[name].values():
            fig.add_trace(
                go.Scatter(
                    x=[x],
                    y=[y_offset],
                    mode="markers+text",
                    marker=dict(size=12, color="#FF4444"),
                    text=str(p["seq_num"]),
                    textposition="middle right",
                    # 读取错误包的序列号和方向
                    customdata=np.stack(
                        (np.array([p["seq_num"]]), np.array([p["direction"]])), axis=-1
                    ),
                    # 使用 join
                    hovertemplate="<br>".join(
                        [
                            "<b>SEQ:%{customdata[0]}</b>",
                            "Direction: %{customdata[1]}",
                        ]
                    ),
                    name=f"{name}",
                    # name=f"seq:{p['seq_num']}, dir:{p['direction']}",
                )
            )
            y_offset -= 0.3

    # 分别处理发送包和 ACK 包
    send_traces = []
    ack_traces = []

    # 生成发送包轨迹
    send_packets = [p for p in active_packets if p["direction"] == "to_receiver"]
    send_text = [f"{p['seq_num']}" for i, p in enumerate(send_packets)]

    send_x = [0 + 15 * ((current_time - p["start_time"]) / 0.5) for p in send_packets]

    send_colors = [
        "#ff7f0e" if p["type"] == "RESEND" else "#1f77b4" for p in send_packets
    ]

    send_traces.append(
        go.Scatter(
            x=send_x,
            y=[0] * len(send_x),
            mode="markers+text",
            marker=dict(size=16, color=send_colors),
            text=send_text,
            textposition="top center",
            textfont=dict(size=10),
            customdata=[p["seq_num"] for p in send_packets],  # 保留完整数据
            hovertemplate="<b>SEQ:%{customdata}</b><br>Type:%{marker.color}<extra></extra>",
            name="Sending Packets",
        )
    )

    # 生成 ACK 包轨迹
    ack_packets = [p for p in active_packets if p["direction"] == "to_sender"]
    ack_text = [f"{p['seq_num']}" for p in ack_packets]

    ack_x = [15 - 15 * ((current_time - p["start_time"]) / 0.5) for p in ack_packets]

    ack_traces.append(
        go.Scatter(
            x=ack_x,
            y=[0] * len(ack_x),
            mode="markers+text",
            marker=dict(size=16, color="#2ca02c"),
            text=ack_text,
            textposition="bottom center",
            textfont=dict(size=10),
            customdata=[p["seq_num"] for p in ack_packets],
            hovertemplate="<b>ACK:%{customdata}</b><extra></extra>",
            name="ACK Packets",
        )
    )

    # 添加所有轨迹
    for trace in send_traces + ack_traces:
        fig.add_trace(trace)
    fig.update_layout(
        xaxis=dict(range=[-1, 11], showgrid=False),
        yaxis=dict(range=[-5, 3], showgrid=False),
        plot_bgcolor="white",
        showlegend=False,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def create_throughput_figure():
    return go.Figure(
        data=[
            go.Scatter(
                x=[d["time"] for d in throughput_history],
                y=[d["throughput"] for d in throughput_history],
                mode="lines",
                line=dict(width=2, color="#1f77b4"),
            )
        ],
        layout=go.Layout(
            title="实时吞吐率 (packets/sec)",
            xaxis_title="时间 (秒)",
            yaxis_title="吞吐率",
            margin=dict(l=50, r=20, t=40, b=40),
        ),
    )


if __name__ == "__main__":
    app.run_server(debug=False)
