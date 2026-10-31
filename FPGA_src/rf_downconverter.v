module rf_downconverter #(
        parameter   [31:0] CARRIER_INCREMENT = 32'd1202590843
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [7:0]   adc_data,
        output  wire    signed [15:0]   i_out,
        output  wire    signed [15:0]   q_out,
        output  wire    out_valid
);

wire    signed [15:0]   centered = {adc_data[7]^1'b1, adc_data[6:0], 8'b0};
wire    signed [15:0]   co;
wire    signed [15:0]   si;

rf_nco #(.INCREMENT(CARRIER_INCREMENT)) u_carrier(
        .clk(clk),
        .rst_n(rst_n),
        .cos_out(co),
        .sin_out(si)
);

wire    signed [31:0]   pi = centered * co;
wire    signed [31:0]   pq = centered * si;

reg signed [17:0]  mixed_i;
reg signed [17:0]  mixed_q;

always  @(posedge clk) begin
    if (!rst_n) begin
        mixed_i <= 0;
        mixed_q <= 0;
    end
    else begin
        mixed_i <= pi >>> 14;
        mixed_q <= (-pq) >>> 14;
    end
end

rf_decimator u_decimator(
        .clk(clk),
        .rst_n(rst_n),
        .i_in(mixed_i),
        .q_in(mixed_q),
        .i_out(i_out),
        .q_out(q_out),
        .out_valid(out_valid)
);

endmodule
