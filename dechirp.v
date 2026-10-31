module dechirp #(
        parameter   W       = 16,
        parameter   DDS_LAT = 3
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    in_valid,
        input   wire    signed [W-1:0]   rx_i,
        input   wire    signed [W-1:0]   rx_q,
        input   wire    signed [W-1:0]   ref_i,
        input   wire    signed [W-1:0]   ref_q,
        input   wire    ref_valid,
        output  wire    signed [W-1:0]   a_i,
        output  wire    signed [W-1:0]   a_q,
        output  wire    signed [W-1:0]   b_i,
        output  wire    signed [W-1:0]   b_q,
        output  wire    out_valid,
        output  reg     flow_fault
);

reg signed [W-1:0]  sri [0:DDS_LAT-1];
reg signed [W-1:0]  srq [0:DDS_LAT-1];
integer i;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        for (i = 0; i < DDS_LAT; i = i + 1) begin
            sri[i] <= {W{1'b0}};
            srq[i] <= {W{1'b0}};
        end
    end
    else begin
        sri[0] <= rx_i;
        srq[0] <= rx_q;
        for (i = 1; i < DDS_LAT; i = i + 1) begin
            sri[i] <= sri[i-1];
            srq[i] <= srq[i-1];
        end
    end
end

wire    signed [W-1:0]   rxd_i = sri[DDS_LAT-1];
wire    signed [W-1:0]   rxd_q = srq[DDS_LAT-1];

wire    [2*W-1:0]   d0;
wire    [2*W-1:0]   d1;
wire    v0;
wire    v1;
wire    ready_a0, ready_b0, ready_a1, ready_b1;
wire    invalid_stream = (ref_valid && !(ready_a0 && ready_b0 && ready_a1 && ready_b1)) || (v0 ^ v1);

always  @(posedge clk)
    if (!rst_n)              flow_fault <= 0;
    else if (invalid_stream) flow_fault <= 1;

assign  a_i = d0[W-1:0];
assign  a_q = d0[2*W-1:W];
assign  b_i = d1[W-1:0];
assign  b_q = d1[2*W-1:W];
assign  out_valid = v0 && v1 && !flow_fault && !invalid_stream;

cmpy_0 u_cmpy_a(
        .aclk(clk),
        .aresetn(rst_n),
        .s_axis_a_tdata({rxd_q, rxd_i}),
        .s_axis_a_tvalid(ref_valid),
        .s_axis_a_tready(ready_a0),
        .s_axis_b_tdata({-ref_q, ref_i}),
        .s_axis_b_tvalid(ref_valid),
        .s_axis_b_tready(ready_b0),
        .m_axis_dout_tdata(d0),
        .m_axis_dout_tvalid(v0),
        .m_axis_dout_tready(1'b1)
);

cmpy_1 u_cmpy_b(
        .aclk(clk),
        .aresetn(rst_n),
        .s_axis_a_tdata({rxd_q, rxd_i}),
        .s_axis_a_tvalid(ref_valid),
        .s_axis_a_tready(ready_a1),
        .s_axis_b_tdata({ref_q, ref_i}),
        .s_axis_b_tvalid(ref_valid),
        .s_axis_b_tready(ready_b1),
        .m_axis_dout_tdata(d1),
        .m_axis_dout_tvalid(v1),
        .m_axis_dout_tready(1'b1)
);

endmodule
