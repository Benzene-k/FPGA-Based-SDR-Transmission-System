module sdr_control_top #(
        parameter   CLK_FREQ = 50000000,
        parameter   BAUD = 115200,
        parameter   N = 4096,
        parameter   INC0 = 32'h0,
        parameter   STEP = 32'h1000,
        parameter   GAP_CYCLES = 64,
        parameter   TX_SAMPLE_DIV = 1,
        parameter   EXTERNAL_RF = 0,
        parameter   QUIET_SAMPLES = 8,
        parameter   HIGH_LEVEL = 1024,
        parameter   LOW_LEVEL = 512,
        parameter   MAX_GAP_SAMPLES = 8192,
        parameter   [32:0]  MIN_PEAK = 1,
        parameter   [32:0]  MIN_MARGIN = 1
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [31:0]  session_id,
        input   wire    uart_rx_pin,
        output  wire    uart_tx_pin,
        input   wire    signed [15:0]   rx_i,
        input   wire    signed [15:0]   rx_q,
        input   wire    rx_sample_valid,
        output  wire    signed [15:0]   tx_i,
        output  wire    signed [15:0]   tx_q,
        output  wire    tx_sample_valid,
        output  wire    tx_busy,
        output  wire    rx_packet_ready,
        output  wire    sync_locked,
        output  wire    rx_flow_fault,
        input   wire    rf_drain_busy,
        input   wire    rf_fault,
        input   wire    [7:0]   external_adc_debug,
        output  wire    tx_abort_strobe,
        output  wire    rx_abort_strobe,
        output  wire    diagnostic_loopback
);

wire    [7:0]   rx_byte;
wire    [7:0]   tx_byte;
wire    [7:0]   mrx;
wire    [7:0]   mtx;
wire    rxv;
wire    framing;
wire    txv;
wire    txr;
wire    mrv;
wire    mtv;
wire    mtr;

uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD(BAUD)) u_uart_rx(
        .clk(clk),
        .rst_n(rst_n),
        .rx(uart_rx_pin),
        .data(rx_byte),
        .valid(rxv),
        .framing_error(framing)
);

uart_tx_byte #(.CLK_FREQ(CLK_FREQ), .BAUD(BAUD)) u_uart_tx(
        .clk(clk),
        .rst_n(rst_n),
        .data(tx_byte),
        .valid(txv),
        .ready(txr),
        .tx(uart_tx_pin)
);

unified_uart_adapter #(.ENABLE_MESSAGE(1), .ENABLE_EXTERNAL(EXTERNAL_RF), .CAPTURE_RATE(CLK_FREQ)) u_router(
        .clk(clk),
        .cap_clk(clk),
        .rst_n(rst_n),
        .session_id(session_id),
        .external_data(EXTERNAL_RF ? external_adc_debug : 8'd0),
        .rx_data(rx_byte),
        .rx_valid(rxv),
        .rx_framing_error(framing),
        .tx_data(tx_byte),
        .tx_valid(txv),
        .tx_ready(txr),
        .message_rx_data(mrx),
        .message_rx_valid(mrv),
        .message_tx_data(mtx),
        .message_tx_valid(mtv),
        .message_tx_ready(mtr),
        .cmd_start(),
        .cmd_stop(),
        .cmd_reset(),
        .requested_running(),
        .crc_errors(),
        .length_errors(),
        .timeouts()
);

wire    ls;
wire    lv;
wire    lr;
wire    mr;
wire    send;
wire    ta;
wire    ra;
wire    release_rx;
wire    td;
wire    te;
wire    re;
wire    pv;
wire    rv;
wire    overrun;
wire    ss;
wire    sl;
wire    core_tx_busy;
wire    core_flow_fault;

assign  tx_busy = core_tx_busy || (EXTERNAL_RF && rf_drain_busy);
assign  rx_flow_fault = core_flow_fault || (EXTERNAL_RF && rf_fault);
assign  tx_abort_strobe = ta;
assign  rx_abort_strobe = ra;

wire    [7:0]   ld;
wire    [7:0]   addr;
wire    [7:0]   rd;
wire    [15:0]  seq;
wire    [15:0]  len;
wire    [15:0]  pseq;
wire    [15:0]  plen;
wire    [2:0]   tec;
wire    [2:0]   rec;
wire    [31:0]  peak_config;
wire    [31:0]  margin_config;

sdr_uart_endpoint #(.PROFILE_RF(EXTERNAL_RF), .PROFILE_N(N), .DEFAULT_PEAK(MIN_PEAK[31:0]), .DEFAULT_MARGIN(MIN_MARGIN[31:0])) u_endpoint(
        .clk(clk),
        .rst_n(rst_n),
        .session_id(session_id),
        .rx_data(mrx),
        .rx_valid(mrv),
        .tx_data(mtx),
        .tx_valid(mtv),
        .tx_ready(mtr),
        .load_start(ls),
        .load_seq(seq),
        .load_length(len),
        .load_valid(lv),
        .load_data(ld),
        .load_ready(lr),
        .message_ready(mr),
        .tx_start(send),
        .tx_abort(ta),
        .tx_busy(tx_busy),
        .tx_done(td),
        .tx_error(te),
        .tx_error_code(tec),
        .rx_abort(ra),
        .release_packet(release_rx),
        .read_addr(addr),
        .read_data(rd),
        .read_valid(rv),
        .packet_ready(rx_packet_ready),
        .packet_valid(pv),
        .packet_seq(pseq),
        .packet_length(plen),
        .rx_error(re),
        .rx_error_code(rec),
        .sync_locked(sync_locked),
        .rx_flow_fault(rx_flow_fault),
        .peak_config(peak_config),
        .margin_config(margin_config),
        .diagnostic_loopback(diagnostic_loopback)
);

message_autosync #(.N(N), .INC0(INC0), .STEP(STEP), .GAP_CYCLES(GAP_CYCLES), .TX_SAMPLE_DIV(TX_SAMPLE_DIV), .USE_RUNTIME_LIMITS(1), .QUIET_SAMPLES(QUIET_SAMPLES), .HIGH_LEVEL(HIGH_LEVEL), .LOW_LEVEL(LOW_LEVEL), .MAX_GAP_SAMPLES(MAX_GAP_SAMPLES), .MIN_PEAK(MIN_PEAK), .MIN_MARGIN(MIN_MARGIN)) u_baseband(
        .clk(clk),
        .rst_n(rst_n),
        .load_start(ls),
        .load_seq(seq),
        .load_length(len),
        .load_valid(lv),
        .load_data(ld),
        .load_ready(lr),
        .message_ready(mr),
        .tx_start(send),
        .tx_abort(ta),
        .tx_busy(core_tx_busy),
        .tx_done(td),
        .tx_error(te),
        .tx_error_code(tec),
        .tx_symbol_start(ss),
        .tx_i(tx_i),
        .tx_q(tx_q),
        .tx_valid(tx_sample_valid),
        .rx_i(rx_i),
        .rx_q(rx_q),
        .rx_valid(rx_sample_valid),
        .rx_abort(ra),
        .release_packet(release_rx),
        .read_addr(addr),
        .read_data(rd),
        .read_valid(rv),
        .packet_ready(rx_packet_ready),
        .packet_valid(pv),
        .packet_seq(pseq),
        .packet_length(plen),
        .rx_error(re),
        .rx_error_code(rec),
        .overrun(overrun),
        .rx_flow_fault(core_flow_fault),
        .sync_locked(sync_locked),
        .sync_lost(sl),
        .configured_peak({1'b0,peak_config}),
        .configured_margin({1'b0,margin_config})
);

endmodule
