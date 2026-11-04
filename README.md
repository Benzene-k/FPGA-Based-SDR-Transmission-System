# Chirp SDR Communication System Reproduction

This document is based on the existing repository source code and explains how to
reproduce the build, simulation, and run flow of the FPGA + host-computer
communication system. The repository contains only source code, constraints, IP
configuration, and host-computer code; it does not include a Vivado project file
(`.xpr`), so the project must be rebuilt manually in Vivado.

## 1. Project Overview

The project is a Chirp (linear frequency-modulated) spread-spectrum communication
demonstration platform based on the **Zynq-7000 (`xc7z020clg400-2`)**:

- The FPGA performs Chirp baseband modulation/demodulation, digital
  up-conversion/down-conversion (DUC/DDC), an 8-bit ADC/DAC interface, and serial
  command parsing and response.
- The host computer is based on PyQt5 and provides three pages: serial
  communication verification, AD/DA acquisition analysis, and text send/receive.
- The modulation uses binary Chirp (positive/negative slope represents bit 1/0).
  The receiver uses dechirp + FFT + peak detection for symbol decision, and it
  computes BER and verifies CRC.

## 2. Directory Structure

```text
cxs_2026
├── FPGA_constrs
│   └── sdr_top.xdc            # constraints (actually for the rf_board_top top level)
├── FPGA_IP
│   ├── cmpy_0 / cmpy_1        # complex multipliers, used for dechirp
│   ├── dds_compiler_0 / dds_compiler_1  # DDS, used for Chirp reference signals
│   └── xfft_0                 # 4096-point FFT
├── FPGA_src                    # all RTL sources (.v/.sv/.vh/.mem)
├── FPGA_tb                     # simulation testbenches
│   ├── tb_demod_top.v
│   └── tb_sdr_loopback.v
└── HostComputer                # host computer
    ├── chirp_upper_computer_v0_11.py   # legacy GUI (inherited by v1.0)
    ├── chirp_upper_computer_v1_0.py    # new entry point (V1.5.0)
    ├── fpga_link/              # FPGA serial communication, SDR messages, RF service
    ├── adda/                   # AD/DA digital acquisition and display
    ├── tools/portable_bootstrap.py     # portable launch bootstrap
    ├── runtime/python/         # bundled portable Python + PyQt5
    └── 启动上位机.cmd          # Windows one-click launch script
```

## 3. FPGA System Architecture

The top-level module used for synthesis is `rf_board_top`, not `sdr_top`. The
module hierarchy is as follows:

```text
rf_board_top
├── MMCME2_BASE                # 50 MHz -> 25 MHz (0°/180°)
├── board_reset_epoch          # reset release and session_id generation
└── sdr_rf_top
    ├── rf_upconverter         # TX digital up-conversion (DUC)
    ├── rf_downconverter       # RX digital down-conversion (DDC)
    └── sdr_control_top
        ├── uart_rx / uart_tx_byte
        ├── unified_uart_adapter
        ├── sdr_uart_endpoint
        └── message_autosync
```

Baseband Chirp transmit/receive signal chain:

```text
TX: frame_tx -> chirp_mod -> chirp_gen(DDS) -> rf_upconverter -> DAC
RX: ADC -> rf_downconverter -> dechirp(cmpy*2) -> fft(xfft) -> peak_detect -> bit
```

IP core usage:

| IP | Used in | Purpose |
| --- | --- | --- |
| `dds_compiler_0` / `dds_compiler_1` | `chirp_gen.v` | Generate positive/negative-slope Chirp references |
| `cmpy_0` / `cmpy_1` | `dechirp.v` | Complex multiplication of the received signal and reference |
| `xfft_0` | `fft.v` | 4096-point FFT spectrum analysis |

Other key files:

- `rf_coefficients.vh`: filter coefficients used by `rf_interpolator.v` and
  `rf_decimator.v`.
- `rf_cos_q15.mem`: COS lookup table used by `rf_nco.v`.

The loopback simulation top level `sdr_top.v` is a standalone internal loopback
test that connects `tx_i/tx_q` directly to `rx_i/rx_q`. After demodulation it
computes BER and CRC and outputs the result over UART, which is used for pure logic
verification and does not depend on the ADC/DAC hardware.

## 4. Hardware and Software Environment

| Item | Requirement |
| --- | --- |
| FPGA device | `xc7z020clg400-2` (Zynq-7000) |
| System clock | 50 MHz (constraint `create_clock -period 20.000`) |
| Sampling clock | 25 MHz (after MMCM division) |
| Serial port | 115200 baud, 8N1 |
| Data interface | 8-bit ADC / 8-bit DAC |
| Vivado | 2019.2 or later (IP: `xfft 9.1`, `dds_compiler 6.0`, `cmpy 6.0`) |
| Host computer | Bundled Python runtime, or system Python 3 + PyQt5 |

## 5. Preparation

### 5.1 Obtain the Source Code

Confirm that the repository contains the following five subdirectories and that
the source files are complete:

```powershell
Get-ChildItem \path\to\project\
```

You should see `FPGA_constrs`, `FPGA_IP`, `FPGA_src`, `FPGA_tb`, and
`HostComputer`.

### 5.2 Install Vivado

Install the full version of Vivado 2019.2 or later (including Zynq-7000 device
support and the IP library). Because the repository only provides `.xci` files,
the IP cores must be re-generated inside Vivado.

### 5.3 Prepare the Host-Computer Runtime

The repository bundles a portable Python runtime, so you can launch the host
computer by double-clicking `启动上位机.cmd`. If you use a system Python instead,
install the following dependencies:

```powershell
pip install pyserial numpy matplotlib PyQt5
```

## 6. FPGA Project Reproduction Steps

1. Create a new Vivado project:

   - Set Project Type to RTL Project.
   - Set Part to `xc7z020clg400-2`.

2. Add design sources:

   - Add all `.v`, `.sv`, `.vh`, and `.mem` files under `FPGA_src` as Design
     Sources.
   - `rf_coefficients.vh` is an `include` file; place it on a source path that the
     project can search.
   - `rf_cos_q15.mem` is the NCO initialization file; do not omit it.

3. Add constraints:

   - Add `FPGA_constrs/sdr_top.xdc`.
   - Note: this constraint file corresponds to the `rf_board_top` top level and
     contains the ports `clk`, `rst_n`, `uart_rx_pin`, `uart_tx_pin`, `ad_data`,
     `ad_otr`, `ad_clk`, `da_data`, and `da_clk`.

4. Rebuild the IP cores:

   In the Sources window use "Add Sources -> Add or create design sources -> Add
   Directories" to add the five `.xci` files under `FPGA_IP` to the project, then
   select them all and run **Generate Output Products**:

   ```text
   FPGA_IP/cmpy_0/cmpy_0.xci
   FPGA_IP/cmpy_1/cmpy_1.xci
   FPGA_IP/dds_compiler_0/dds_compiler_0.xci
   FPGA_IP/dds_compiler_1/dds_compiler_1.xci
   FPGA_IP/xfft_0/xfft_0.xci
   ```

   After generation completes, confirm that the IP outputs are under
   `<project>.gen/sources_1/ip/<ip_name>`.

5. Set the synthesis top level:

   - Set `rf_board_top` as the Top Module.
   - If you only run loopback simulation, change the top level to `sdr_top`; the
     physical constraints in `sdr_top.xdc` are not needed in that case.

6. Run synthesis, implementation, and bitstream generation:

   ```text
   Run Synthesis -> Run Implementation -> Generate Bitstream
   ```

7. Download and verify:

   - Connect the board UART (115200 baud) and JTAG.
   - After downloading the bitstream, verify `PING/PONG` using the host computer or
     a serial tool.

## 7. Simulation Reproduction

The repository provides two testbenches; both can be run directly in the Vivado
Simulator (xsim) or a compatible simulator.

### 7.1 Single-Symbol Demodulation Test

Testbench file: `FPGA_tb/tb_demod_top.v`

It injects a positive-slope Chirp (expected bit 1) and a negative-slope Chirp
(expected bit 0) into `demod_top` and verifies `bit_out`.

### 7.2 Full Loopback Test

Testbench file: `FPGA_tb/tb_sdr_loopback.v`

It instantiates `sdr_top` to run the "transmit -> demodulate -> BER/CRC" loopback.
The test passes when four consecutive frames satisfy `crc_ok == 1` and
`err_count == 0`.

It is recommended to set `sdr_top` as the simulation top level and add
`FPGA_tb/*.v` and `FPGA_src/*` before running.

## 8. Host-Computer Reproduction

### 8.1 One-Click Launch (Recommended)

On Windows, double-click:

```text
\path\to\project\HostComputer\启动上位机.cmd
```

The script first prefers the bundled `runtime\python\python.exe`, configures the Qt
plugin path through `tools\portable_bootstrap.py`, and then enters
`chirp_upper_computer_v1_0.main()`.

### 8.2 Launch with System Python

```powershell
cd \path\to\project\HostComputer
python -B tools\portable_bootstrap.py
```

### 8.3 Command-Line Serial Communication Verification

Standalone serial communication verification (does not control the baseband
algorithm):

```powershell
cd \path\to\project\HostComputer
python -m fpga_link ports
python -m fpga_link --port COM5 ping
python -m fpga_link --port COM5 start
python -m fpga_link --port COM5 stop
python -m fpga_link --port COM5 reset
```

SDR message send/receive, thresholds, and diagnostic loopback:

```powershell
python -m fpga_link.sdr_control --port COM5 --send "hello"
python -m fpga_link.sdr_control --port COM5 --receive --wait 5
python -m fpga_link.sdr_control --port COM5 --loopback on
python -m fpga_link.sdr_control --port COM5 --loopback off
python -m fpga_link.sdr_control --port COM5 --set-thresholds 512 256
```

### 8.4 GUI Page Description

- **FPGA Communication**: after connecting the serial port, verify `PING/PONG` and
  send control requests.
- **AD/DA Acquisition**: local test, on-board digital source, real ADC, or file
  import; view waveforms, spectrum, statistics, and raw data in one place.
- **Text Send/Receive**: two computers each connect to one board, send UTF-8 text,
  continuously receive and decode it, and refresh the ADC segment at the same time.

Text send/receive requires the current RF firmware to use the external ADC
configuration (see parameters below) and the on-board diagnostic loopback to be
turned off; otherwise `RfService` refuses to start and reports that the on-board
diagnostic loopback cannot be treated as antenna reception.

## 9. Serial Communication Protocol

The host computer and FPGA use fixed-length frames with CRC and a `0xAA 0x55`
header:

```text
AA 55 | TYPE(1) | SEQ(1) | LEN(2, big-endian) | PAYLOAD(LEN) | CRC16(2)
```

CRC uses `binascii.crc_hqx(data, 0xFFFF)` (CRC-16/ARC).

Basic message types (`fpga_link/protocol.py`):

| TYPE | Meaning |
| --- | --- |
| `0x01` | PING |
| `0x02` | PONG |
| `0x12` / `0x13` / `0x14` | START / STOP / RESET |
| `0x20` / `0x21` | ECHO / ECHO_REPLY |
| `0x30` / `0x31` / `0x32` | CONFIG_GET / CONFIG_REPLY / CONFIG_SET |
| `0x80` | ACK |
| `0xE0` | ERROR |

SDR extension commands (`fpga_link/sdr_control.py`, reply type is `TYPE | 0x80`):

| Command | Purpose |
| --- | --- |
| `0x50` | Begin LOAD (sequence number + length) |
| `0x51` | Upload chunked data |
| `0x52` | Start transmission |
| `0x53` | Query status |
| `0x54` | Read received-result block |
| `0x55` | Release received result |
| `0x56` | Abort TX/RX |
| `0x57` | Query/set profile thresholds |
| `0x58` | Query/set diagnostic loopback |
| `0x59` | Bind boot session |

## 10. Key Parameters

| Parameter | Value | Source |
| --- | --- | --- |
| System clock | 50 MHz | `sdr_top.xdc` |
| FPGA sampling clock | 25 MHz | `rf_board_top` MMCM |
| Baseband rate | 2.5 MSa/s | `TX_SAMPLE_DIV = 10` |
| Chirp points N | 4096 | `sdr_rf_top` / `sdr_control_top` |
| FFT points | 4096 | `xfft_0` |
| Baud rate | 115200 | `rf_board_top` / host computer |
| RF center frequency | 7 MHz | `rf_service.py` profile check |
| RF bandwidth | 1 MHz | `rf_service.py` profile check |
| RF sampling rate | 25 MSa/s | `rf_service.py` / ADC |
| TX/RX carrier increment | `1202590843` | `sdr_rf_top` parameter |
| Data width | 16-bit (IQ) | `sdr_top` / various modules |
| ADC/DAC width | 8-bit | `rf_board_top` |

## 11. Common Issues

1. **Synthesis reports a missing IP module**: Generate Output Products was not run,
   or the `.xci` files were added to the project without generating output products.

2. **`sdr_top.xdc` reports a missing port**: this constraint corresponds to
   `rf_board_top`. If the synthesis top level was incorrectly set to `sdr_top`,
   ports such as `uart_rx_pin` and `ad_data` will mismatch; switch the top level.

3. **Loopback test fails**: confirm the simulation top level is `sdr_top` and that
   parameters such as `DDS_LAT`, `N`, and `STEP` match the testbench
   (`N=4096`, `STEP=0x1000`, `DDS_LAT=3`).

4. **Host computer reports "on-board diagnostic loopback is enabled"**: run
   `python -m fpga_link.sdr_control --port COMx --loopback off` on the command line,
   or turn off the diagnostic loopback on the GUI FPGA Communication page before
   text send/receive.

5. **Text send/receive reports an RF configuration mismatch**: confirm the FPGA is
   programmed with the external RF firmware corresponding to `rf_board_top`, and
   the profile is `rf_profile=1`, `center=7 MHz`, `bandwidth=1 MHz`,
   `rf_rate=25 MSa/s`, `base_rate=2.5 MSa/s`, `points=4096`.

6. **Host-computer source code appears garbled**: some Python source files in this
   repository are saved with GBK encoding. If an editor shows garbled text, switch
   to GBK/GB2312 encoding, and do not save them as UTF-8, which would corrupt the
   source.

7. **Serial port cannot be opened**: confirm the COM number enumerated by the board
   (`python -m fpga_link ports`) and check that the baud rate is 115200.
