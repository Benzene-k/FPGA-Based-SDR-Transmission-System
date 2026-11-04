# Chirp SDR 通信系统复现

本文档基于仓库已有代码，说明如何从源码复现该
FPGA + 上位机通信系统的编译、仿真与运行流程。仓库只包含源码、约束、IP 配置和
上位机代码，不包含 Vivado 工程文件（`.xpr`），因此需要在 Vivado 中手动重建工程。

## 1. 项目简介

该项目是一套基于 **Zynq-7000（`xc7z020clg400-2`）** 的 Chirp（线性调频）扩频通信
演示平台：

- FPGA 端完成 Chirp 基带调制/解调、数字上变频/下变频（DUC/DDC）、8 bit ADC/DAC
  接口以及串口命令解析与响应。
- 上位机端基于 PyQt5，提供串口通信验证、AD/DA 采集分析和文本收发三个页面。
- 调制采用二进制 Chirp（正/负斜率表示 bit 1/0），接收端使用 dechirp + FFT + 峰值
  检测完成符号判决，并统计 BER、校验 CRC。

## 2. 目录结构

```text
cxs_2026
├── FPGA_constrs
│   └── sdr_top.xdc            # 约束（实际对应 rf_board_top 顶层）
├── FPGA_IP
│   ├── cmpy_0 / cmpy_1        # 复数乘法器，用于 dechirp
│   ├── dds_compiler_0 / dds_compiler_1  # DDS，用于 Chirp 参考信号
│   └── xfft_0                 # 4096 点 FFT
├── FPGA_src                    # 全部 RTL 源码（.v/.sv/.vh/.mem）
├── FPGA_tb                     # 仿真测试台
│   ├── tb_demod_top.v
│   └── tb_sdr_loopback.v
└── HostComputer                # 上位机
    ├── chirp_upper_computer_v0_11.py   # 旧版 GUI（被 v1.0 继承）
    ├── chirp_upper_computer_v1_0.py    # 新版入口（V1.5.0）
    ├── fpga_link/              # FPGA 串口通信、SDR 消息、RF 服务
    ├── adda/                   # AD/DA 数字采集与展示
    ├── tools/portable_bootstrap.py     # 便携启动引导
    ├── runtime/python/         # 内置便携 Python + PyQt5
    └── 启动上位机.cmd          # Windows 一键启动脚本
```

## 3. FPGA 系统架构

综合用的顶层模块是 `rf_board_top`，不是 `sdr_top`。模块层次如下：

```text
rf_board_top
├── MMCME2_BASE                # 50 MHz -> 25 MHz（0°/180°）
├── board_reset_epoch          # 复位释放与 session_id 生成
└── sdr_rf_top
    ├── rf_upconverter         # TX 数字上变频（DUC）
    ├── rf_downconverter       # RX 数字下变频（DDC）
    └── sdr_control_top
        ├── uart_rx / uart_tx_byte
        ├── unified_uart_adapter
        ├── sdr_uart_endpoint
        └── message_autosync
```

基带 Chirp 收发信号链：

```text
TX: frame_tx -> chirp_mod -> chirp_gen(DDS) -> rf_upconverter -> DAC
RX: ADC -> rf_downconverter -> dechirp(cmpy*2) -> fft(xfft) -> peak_detect -> bit
```

IP 核调用关系：

| IP | 使用位置 | 作用 |
| --- | --- | --- |
| `dds_compiler_0` / `dds_compiler_1` | `chirp_gen.v` | 生成正/负斜率 Chirp 参考 |
| `cmpy_0` / `cmpy_1` | `dechirp.v` | 接收信号与参考的复数相乘 |
| `xfft_0` | `fft.v` | 4096 点 FFT 频谱分析 |

其它关键文件：

- `rf_coefficients.vh`：`rf_interpolator.v`、`rf_decimator.v` 使用的滤波器系数。
- `rf_cos_q15.mem`：`rf_nco.v` 使用的 COS 查找表。

闭环仿真顶层 `sdr_top.v` 是独立的内部回环测试，将 `tx_i/tx_q` 直接接到 `rx_i/rx_q`，
解调后统计 BER 和 CRC，结果通过 UART 输出，用于纯逻辑验证，不依赖 ADC/DAC 硬件。

## 4. 硬件与软件环境

| 项目 | 要求 |
| --- | --- |
| FPGA 器件 | `xc7z020clg400-2`（Zynq-7000） |
| 系统时钟 | 50 MHz（约束 `create_clock -period 20.000`） |
| 采样时钟 | 25 MHz（MMCM 分频后） |
| 串口 | 115200 baud，8N1 |
| 数据接口 | 8 bit ADC / 8 bit DAC |
| Vivado | 2019.2 或更高（IP：`xfft 9.1`、`dds_compiler 6.0`、`cmpy 6.0`） |
| 上位机 | 内置 Python 运行时，或系统 Python 3 + PyQt5 |

## 5. 复现准备

### 5.1 获取源码

确认仓库目录包含以下五个子目录，且源码文件完整：

```powershell
Get-ChildItem \文件路径\
```

应看到 `FPGA_constrs`、`FPGA_IP`、`FPGA_src`、`FPGA_tb`、`HostComputer`。

### 5.2 安装 Vivado

建议安装 Vivado 2019.2 或更新的完整版（需包含 Zynq-7000 器件支持和 IP 库）。
由于仓库只提供 `.xci`，IP 需要在 Vivado 中重新生成输出产品。

### 5.3 准备上位机运行环境

仓库自带便携 Python 运行时，可直接双击 `启动上位机.cmd` 启动。
若使用系统 Python，需要安装：

```powershell
pip install pyserial numpy matplotlib PyQt5
```

## 6. FPGA 工程复现步骤

1. 新建 Vivado 工程：

   - Project Type 选择 RTL Project。
   - Part 选择 `xc7z020clg400-2`。

2. 添加设计源码：

   - 将 `FPGA_src` 下所有 `.v`、`.sv`、`.vh`、`.mem` 添加为 Design Sources。
   - `rf_coefficients.vh` 是 `include` 文件，放在工程可搜索的源码路径即可。
   - `rf_cos_q15.mem` 是 NCO 的初始化文件，不要遗漏。

3. 添加约束：

   - 添加 `FPGA_constrs/sdr_top.xdc`。
   - 注意：该约束对应 `rf_board_top` 顶层，端口包含
     `clk`、`rst_n`、`uart_rx_pin`、`uart_tx_pin`、`ad_data`、`ad_otr`、
     `ad_clk`、`da_data`、`da_clk`。

4. 重建 IP：

   在 Sources 窗口用 “Add Sources -> Add or create design sources -> Add
   Directories” 将 `FPGA_IP` 下五个 `.xci` 加入工程，随后全选并执行
   **Generate Output Products**：

   ```text
   FPGA_IP/cmpy_0/cmpy_0.xci
   FPGA_IP/cmpy_1/cmpy_1.xci
   FPGA_IP/dds_compiler_0/dds_compiler_0.xci
   FPGA_IP/dds_compiler_1/dds_compiler_1.xci
   FPGA_IP/xfft_0/xfft_0.xci
   ```

   生成完成后确认 IP 输出在
   `<工程>.gen/sources_1/ip/<ip_name>` 下。

5. 设置综合顶层：

   - 将 `rf_board_top` 设为 Top Module。
   - 若只做回环仿真，则顶层改为 `sdr_top`，且不需要 `sdr_top.xdc` 的物理约束。

6. 运行综合、实现并生成比特流：

   ```text
   Run Synthesis -> Run Implementation -> Generate Bitstream
   ```

7. 下载验证：

   - 连接板卡 UART（115200 baud）和 JTAG。
   - 下载比特流后，用上位机或串口工具验证 `PING/PONG`。

## 7. 仿真复现

仓库提供两个测试台，均可直接在 Vivado Simulator（xsim）或兼容仿真器中运行。

### 7.1 单符号解调测试

仿真文件：`FPGA_tb/tb_demod_top.v`

它向 `demod_top` 注入一个正斜率 Chirp（期望 bit 1）和一个负斜率 Chirp
（期望 bit 0），验证 `bit_out`。

### 7.2 整机回环测试

仿真文件：`FPGA_tb/tb_sdr_loopback.v`

实例化 `sdr_top` 完成“发射 -> 解调 -> BER/CRC”闭环，连续 4 帧满足
`crc_ok == 1` 且 `err_count == 0` 即判定通过。

建议将 `sdr_top` 设为仿真顶层，添加 `FPGA_tb/*.v` 和 `FPGA_src/*` 后运行。

## 8. 上位机复现

### 8.1 一键启动（推荐）

在 Windows 下双击：

```text
\文件路径\HostComputer\启动上位机.cmd
```

该脚本会优先使用仓库内的 `runtime\python\python.exe`，并通过
`tools\portable_bootstrap.py` 配置 Qt 插件路径，随后进入 `chirp_upper_computer_v1_0.main()`。

### 8.2 使用系统 Python 启动

```powershell
cd \文件路径\HostComputer
python -B tools\portable_bootstrap.py
```

### 8.3 命令行验证串口通信

独立串口通信验证（不控制基带算法）：

```powershell
cd \文件路径\HostComputer
python -m fpga_link ports
python -m fpga_link --port COM5 ping
python -m fpga_link --port COM5 start
python -m fpga_link --port COM5 stop
python -m fpga_link --port COM5 reset
```

SDR 消息收发 / 阈值 / 诊断回环：

```powershell
python -m fpga_link.sdr_control --port COM5 --send "hello"
python -m fpga_link.sdr_control --port COM5 --receive --wait 5
python -m fpga_link.sdr_control --port COM5 --loopback on
python -m fpga_link.sdr_control --port COM5 --loopback off
python -m fpga_link.sdr_control --port COM5 --set-thresholds 512 256
```

### 8.4 GUI 页面说明

- **FPGA 通信**：连接串口后验证 `PING/PONG`，并发送控制请求。
- **AD/DA 采集**：本地测试、板内数字源、真实 ADC 或文件导入，统一查看波形、
  频谱、统计与原始码。
- **文本收发**：两台电脑各接一块板卡，发送 UTF-8 文本并持续接收解码，同时刷新
  ADC 片段。

文本收发需要当前 RF 固件使用外部 ADC 配置（见下方参数），且必须关闭板内诊断回环，
否则 `RfService` 会拒绝启动并提示“板内诊断回环不可当作天线接收”。

## 9. 串口通信协议

上位机与 FPGA 之间采用带 CRC 的定长帧，帧头 `0xAA 0x55`：

```text
AA 55 | TYPE(1) | SEQ(1) | LEN(2, 大端) | PAYLOAD(LEN) | CRC16(2)
```

CRC 采用 `binascii.crc_hqx(data, 0xFFFF)`（CRC-16/ARC）。

基础消息类型（`fpga_link/protocol.py`）：

| TYPE | 含义 |
| --- | --- |
| `0x01` | PING |
| `0x02` | PONG |
| `0x12` / `0x13` / `0x14` | START / STOP / RESET |
| `0x20` / `0x21` | ECHO / ECHO_REPLY |
| `0x30` / `0x31` / `0x32` | CONFIG_GET / CONFIG_REPLY / CONFIG_SET |
| `0x80` | ACK |
| `0xE0` | ERROR |

SDR 扩展命令（`fpga_link/sdr_control.py`，回复类型为 `TYPE | 0x80`）：

| 命令 | 作用 |
| --- | --- |
| `0x50` | LOAD 开始（序列号 + 长度） |
| `0x51` | 上传分块数据 |
| `0x52` | 发送启动 |
| `0x53` | 查询状态 |
| `0x54` | 读取接收结果分块 |
| `0x55` | 释放接收结果 |
| `0x56` | 中止 TX/RX |
| `0x57` | 查询/设置 profile 阈值 |
| `0x58` | 查询/设置诊断回环 |
| `0x59` | 引导 session 绑定 |

## 10. 关键参数

| 参数 | 值 | 来源 |
| --- | --- | --- |
| 系统时钟 | 50 MHz | `sdr_top.xdc` |
| FPGA 采样时钟 | 25 MHz | `rf_board_top` MMCM |
| 基带速率 | 2.5 MSa/s | `TX_SAMPLE_DIV = 10` |
| Chirp 点数 N | 4096 | `sdr_rf_top` / `sdr_control_top` |
| FFT 点数 | 4096 | `xfft_0` |
| 波特率 | 115200 | `rf_board_top` / 上位机 |
| RF 中心频率 | 7 MHz | `rf_service.py` profile 校验 |
| RF 带宽 | 1 MHz | `rf_service.py` profile 校验 |
| RF 采样率 | 25 MSa/s | `rf_service.py` / ADC |
| TX/RX 载波增量 | `1202590843` | `sdr_rf_top` 参数 |
| 数据位宽 | 16 bit（IQ） | `sdr_top` / 各模块 |
| ADC/DAC 位宽 | 8 bit | `rf_board_top` |

## 11. 常见问题

1. **综合报错找不到 IP 模块**：未执行 Generate Output Products，或 `.xci`
   加入工程后没有生成输出产品。

2. **`sdr_top.xdc` 报端口不存在**：该约束对应 `rf_board_top`。如果综合顶层错误地
   选成了 `sdr_top`，会出现 `uart_rx_pin`、`ad_data` 等端口不匹配，切换顶层即可。

3. **回环测试失败**：先确认仿真顶层为 `sdr_top`，且 `DDS_LAT`、`N`、`STEP` 等参数
   与测试台一致（`N=4096`、`STEP=0x1000`、`DDS_LAT=3`）。

4. **上位机提示“板内诊断回环已开启”**：在命令行执行
   `python -m fpga_link.sdr_control --port COMx --loopback off`，或用 GUI 的 FPGA
   通信页关闭诊断回环后再做文本收发。

5. **文本收发提示 RF 配置不匹配**：确认 FPGA 烧录的是 `rf_board_top` 对应的外部 RF
   固件，profile 需为 `rf_profile=1`、`center=7 MHz`、`bandwidth=1 MHz`、
   `rf_rate=25 MSa/s`、`base_rate=2.5 MSa/s`、`points=4096`。

6. **上位机源码显示为乱码**：本仓库部分 Python 源码使用 GBK 编码保存。若用编辑器
   查看出现乱码，请切换为 GBK/GB2312 编码，不要用 UTF-8 直接保存，以免破坏源码。

7. **串口打不开**：确认板卡枚举出的 COM 号正确（`python -m fpga_link ports`），并
   检查波特率为 115200。
