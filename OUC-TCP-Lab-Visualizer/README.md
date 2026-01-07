# TCP-Lab-Visualizer

用于可视化 TCP 实验的 log 文件。使用 uv 作为 Python 的包管理工具，使用 Dash 作为 Web 服务器。

项目中提供了 requirements.txt 和 uv.lock 两个文件，用于安装依赖包。可以使用以下命令安装依赖包：

```shell
pip install -r requirements.txt
# 或者使用以下命令安装 uv 并安装依赖包：
pip install uv
uv sync
```

安装完成后，可以使用以下命令启动 Web 服务器：

```shell
python main.py
# 或者
uv run main.py
```

在控制台中会输出 Web 服务器的地址，可以在浏览器中打开该地址查看可视化界面。

Have fun! 🎉
