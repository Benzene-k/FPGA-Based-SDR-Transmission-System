module rf_board_top #(
        parameter   [31:0]  SESSION_BASE = 32'hadffff00
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    uart_rx_pin,
        output  wire    uart_tx_pin,
        input   wire    [7:0]   ad_data,
        input   wire    ad_otr,
        output  wire    ad_clk,
        output  wire    [7:0]   da_data,
        output  wire    da_clk
);

wire    core_clk;
wire    dac_launch_clk;
wire    locked;
wire    feedback;
wire    feedback_buf;
wire    raw0;
wire    raw180;
wire    input_buf;

BUFG input_clock(
        .I(clk),
        .O(input_buf)
);

MMCME2_BASE #(.CLKIN1_PERIOD(20.0), .CLKFBOUT_MULT_F(12.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(24.0), .CLKOUT1_DIVIDE(24), .CLKOUT1_PHASE(180.0), .STARTUP_WAIT("FALSE")) u_clocking(
        .CLKIN1(input_buf),
        .CLKFBIN(feedback_buf),
        .RST(!rst_n),
        .PWRDWN(1'b0),
        .CLKFBOUT(feedback),
        .CLKOUT0(raw0),
        .CLKOUT1(raw180),
        .LOCKED(locked),
        .CLKFBOUTB(),
        .CLKOUT0B(),
        .CLKOUT1B(),
        .CLKOUT2(),
        .CLKOUT2B(),
        .CLKOUT3(),
        .CLKOUT3B(),
        .CLKOUT4(),
        .CLKOUT5(),
        .CLKOUT6()
);

BUFG feedback_clock(
        .I(feedback),
        .O(feedback_buf)
);

BUFG sample_clock(
        .I(raw0),
        .O(core_clk)
);

BUFG dac_data_clock(
        .I(raw180),
        .O(dac_launch_clk)
);

ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .INIT(1'b0), .SRTYPE("SYNC")) u_ad_forward(
        .C(core_clk),
        .CE(1'b1),
        .D1(1'b1),
        .D2(1'b0),
        .R(1'b0),
        .S(1'b0),
        .Q(ad_clk)
);

ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .INIT(1'b0), .SRTYPE("SYNC")) u_da_forward(
        .C(core_clk),
        .CE(1'b1),
        .D1(1'b1),
        .D2(1'b0),
        .R(1'b0),
        .S(1'b0),
        .Q(da_clk)
);

wire    epoch_ready;
wire    exhausted;
wire    [31:0]  session_id;

board_reset_epoch #(.SESSION_BASE(SESSION_BASE)) u_epoch(
        .clk(core_clk),
        .button_n(rst_n && locked),
        .core_rst_n(epoch_ready),
        .session_id(session_id),
        .exhausted(exhausted)
);

(* DONT_TOUCH="TRUE" *) reg    core_ready = 0;

always  @(posedge core_clk) begin
    core_ready <= epoch_ready;
end

(* IOB="TRUE" *) reg [7:0]  sampled_data;

always  @(posedge core_clk) begin
    sampled_data <= ad_data;
end

wire    [7:0]   rf_code;

sdr_rf_top u_radio(
        .clk(core_clk),
        .rst_n(core_ready),
        .session_id(session_id),
        .uart_rx_pin(uart_rx_pin),
        .uart_tx_pin(uart_tx_pin),
        .adc_data(sampled_data),
        .dac_data(rf_code),
        .tx_busy(),
        .rx_packet_ready(),
        .sync_locked(),
        .flow_fault()
);

(* IOB="TRUE" *) reg [7:0]  dac_pad_data = 8'd128;

always  @(posedge dac_launch_clk) begin
    if (!core_ready) dac_pad_data <= 128;
    else        dac_pad_data <= rf_code;
end

assign  da_data = dac_pad_data;

endmodule
