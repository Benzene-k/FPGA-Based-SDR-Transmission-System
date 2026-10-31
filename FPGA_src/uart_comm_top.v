module uart_comm_top #(
        parameter   CLK_FREQ = 50_000_000,
        parameter   BAUD = 115_200,
        parameter   FRAME_TIMEOUT_CYCLES = CLK_FREQ / 10
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    uart_rx_pin,
        output  wire    uart_tx_pin,
        output  wire    cmd_start,
        output  wire    cmd_stop,
        output  wire    cmd_reset,
        output  wire    requested_running,
        output  wire    [15:0]  crc_error_count,
        output  wire    [15:0]  framing_error_count,
        output  wire    [15:0]  length_error_count,
        output  wire    [15:0]  timeout_count
);

wire    [7:0]   rx_byte, tx_byte;
wire    rx_valid, rx_framing_error, tx_valid, tx_ready;
reg [15:0]  framing_errors;

assign  framing_error_count = framing_errors;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) framing_errors <= 0;
    else if (rx_framing_error) framing_errors <= framing_errors + 1'b1;
end

uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD(BAUD))   receiver(
        .clk(clk),
        .rst_n(rst_n),
        .rx(uart_rx_pin),
        .data(rx_byte),
        .valid(rx_valid),
        .framing_error(rx_framing_error)
);

uart_tx_byte #(.CLK_FREQ(CLK_FREQ), .BAUD(BAUD))   transmitter(
        .clk(clk),
        .rst_n(rst_n),
        .data(tx_byte),
        .valid(tx_valid),
        .ready(tx_ready),
        .tx(uart_tx_pin)
);

uart_protocol #(.FRAME_TIMEOUT_CYCLES(FRAME_TIMEOUT_CYCLES))   protocol(
        .clk(clk),
        .rst_n(rst_n),
        .rx_data(rx_byte),
        .rx_valid(rx_valid),
        .rx_framing_error(rx_framing_error),
        .tx_data(tx_byte),
        .tx_valid(tx_valid),
        .tx_ready(tx_ready),
        .cmd_start(cmd_start),
        .cmd_stop(cmd_stop),
        .cmd_reset(cmd_reset),
        .requested_running(requested_running),
        .crc_error_count(crc_error_count),
        .length_error_count(length_error_count),
        .timeout_count(timeout_count)
);

endmodule
