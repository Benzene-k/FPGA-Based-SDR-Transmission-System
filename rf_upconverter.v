module rf_upconverter #(
        parameter   [31:0] CARRIER_INCREMENT = 32'd1202590843,
        parameter   GAIN_SHIFT = 1
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    abort,
        input   wire    signed [15:0]   i_in,
        input   wire    signed [15:0]   q_in,
        input   wire    in_valid,
        output  reg     [7:0]   dac_data,
        output  wire    drain_busy,
        output  wire    flow_fault
);

wire    signed [15:0]   fi;
wire    signed [15:0]   fq;
wire    signed [15:0]   co;
wire    signed [15:0]   si;

rf_interpolator u_interpolator(
        .clk(clk),
        .rst_n(rst_n),
        .abort(abort),
        .i_in(i_in),
        .q_in(q_in),
        .in_valid(in_valid),
        .i_out(fi),
        .q_out(fq),
        .flow_fault(flow_fault)
);

rf_nco #(.INCREMENT(CARRIER_INCREMENT)) u_carrier(
        .clk(clk),
        .rst_n(rst_n),
        .cos_out(co),
        .sin_out(si)
);

wire    signed [31:0]   pi = fi * co;
wire    signed [31:0]   pq = fq * si;
wire    signed [32:0]   real_product = {pi[31], pi} - {pq[31], pq};
wire    signed [32:0]   scaled = real_product >>> (15 + GAIN_SHIFT);

reg [8:0]  tail;
reg signed [15:0]  clipped;

assign  drain_busy = tail != 0;

always  @* begin
    if (scaled > 32767) clipped = 32767;
    else if (scaled < -32768) clipped = -32768;
    else clipped = scaled[15:0];
end

always  @(posedge clk) begin
    if (!rst_n || abort) begin
        dac_data <= 128;
        tail <= 0;
    end
    else begin
        if (in_valid) tail <= 221;
        else if (tail != 0) tail <= tail - 1'b1;
        if (tail == 0 || flow_fault) dac_data <= 128;
        else dac_data <= {clipped[15]^1'b1, clipped[14:8]};
    end
end

endmodule
