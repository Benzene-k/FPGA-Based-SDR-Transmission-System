module fft #(
        parameter   W = 16
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    signed [W-1:0]   din_i,
        input   wire    signed [W-1:0]   din_q,
        input   wire    din_valid,
        input   wire    din_last,
        output  wire    din_ready,
        output  wire    signed [W-1:0]   dout_i,
        output  wire    signed [W-1:0]   dout_q,
        output  wire    [15:0]   dout_index,
        output  wire    dout_valid,
        output  wire    dout_last,
        output  wire    frame_fault
);

wire    [2*W-1:0]   din_tdata  = {din_q, din_i};
wire    [2*W-1:0]   dout_tdata;
wire    unexpected_last, missing_last;
assign  frame_fault = unexpected_last || missing_last;

xfft_0 u_fft(
        .aclk(clk),
        .aresetn(rst_n),
        .s_axis_config_tdata(16'h1555),
        .s_axis_config_tvalid(1'b1),
        .s_axis_config_tready(),
        .s_axis_data_tdata(din_tdata),
        .s_axis_data_tvalid(din_valid),
        .s_axis_data_tready(din_ready),
        .s_axis_data_tlast(din_last),
        .m_axis_data_tdata(dout_tdata),
        .m_axis_data_tuser(dout_index),
        .m_axis_data_tvalid(dout_valid),
        .m_axis_data_tready(1'b1),
        .m_axis_data_tlast(dout_last),
        .event_frame_started(),
        .event_tlast_unexpected(unexpected_last),
        .event_tlast_missing(missing_last),
        .event_status_channel_halt(),
        .event_data_in_channel_halt(),
        .event_data_out_channel_halt()
);

assign  dout_i = dout_tdata[W-1:0];
assign  dout_q = dout_tdata[2*W-1:W];

endmodule
