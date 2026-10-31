module sdr_rf_top #(
        parameter   BAUD = 115200,
        parameter   [31:0]  TX_CARRIER_INCREMENT = 32'd1202590843,
        parameter   [31:0]  RX_CARRIER_INCREMENT = 32'd1202590843
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [31:0]  session_id,
        input   wire    uart_rx_pin,
        output  wire    uart_tx_pin,
        input   wire    [7:0]   adc_data,
        output  wire    [7:0]   dac_data,
        output  wire    tx_busy,
        output  wire    rx_packet_ready,
        output  wire    sync_locked,
        output  wire    flow_fault
);

wire    signed [15:0]   ti;
wire    signed [15:0]   tq;
wire    signed [15:0]   ri;
wire    signed [15:0]   rq;
wire    tv;
wire    rv;
wire    drain;
wire    tx_fault;
wire    ta;
wire    ra;
wire    diagnostic_loopback;
wire    [7:0]   tx_code;

assign  dac_data = diagnostic_loopback ? 8'd128 : tx_code;

rf_upconverter #(.CARRIER_INCREMENT(TX_CARRIER_INCREMENT)) u_duc(
        .clk(clk),
        .rst_n(rst_n),
        .abort(ta),
        .i_in(ti),
        .q_in(tq),
        .in_valid(tv),
        .dac_data(tx_code),
        .drain_busy(drain),
        .flow_fault(tx_fault)
);

rf_downconverter #(.CARRIER_INCREMENT(RX_CARRIER_INCREMENT)) u_ddc(
        .clk(clk),
        .rst_n(rst_n && !ra),
        .adc_data(diagnostic_loopback ? tx_code : adc_data),
        .i_out(ri),
        .q_out(rq),
        .out_valid(rv)
);

sdr_control_top #(.CLK_FREQ(25000000), .BAUD(BAUD), .N(4096), .INC0(32'hfccccccd), .STEP(32'd26214), .GAP_CYCLES(640), .TX_SAMPLE_DIV(10), .EXTERNAL_RF(1), .QUIET_SAMPLES(8), .HIGH_LEVEL(512), .LOW_LEVEL(256)) u_control(
        .clk(clk),
        .rst_n(rst_n),
        .session_id(session_id),
        .uart_rx_pin(uart_rx_pin),
        .uart_tx_pin(uart_tx_pin),
        .rx_i(ri),
        .rx_q(rq),
        .rx_sample_valid(rv),
        .tx_i(ti),
        .tx_q(tq),
        .tx_sample_valid(tv),
        .tx_busy(tx_busy),
        .rx_packet_ready(rx_packet_ready),
        .sync_locked(sync_locked),
        .rx_flow_fault(flow_fault),
        .rf_drain_busy(drain),
        .rf_fault(tx_fault),
        .external_adc_debug(adc_data),
        .tx_abort_strobe(ta),
        .rx_abort_strobe(ra),
        .diagnostic_loopback(diagnostic_loopback)
);

endmodule
