module peak_detect #(
        parameter   W = 16
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    signed [W-1:0]  din_i,
        input   wire    signed [W-1:0]  din_q,
        input   wire    din_valid,
        input   wire    din_last,
        output  wire    signed [2*W:0]  peak,
        output  reg     peak_valid
);

wire    signed [2*W-1:0]  ii = din_i * din_i;
wire    signed [2*W-1:0]  qq = din_q * din_q;
wire    signed [2*W:0]    sq = ii + qq;

reg signed [2*W:0] max_sq;
reg signed [2*W:0] peak_r;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        max_sq     <= {(2*W+1){1'b0}};
        peak_r     <= {(2*W+1){1'b0}};
        peak_valid <= 1'b0;
    end
    else begin
        peak_valid <= 1'b0;
        if (din_valid) begin
            if (din_last) begin
                peak_r     <= (sq > max_sq) ? sq : max_sq;
                peak_valid <= 1'b1;
                max_sq     <= {(2*W+1){1'b0}};
            end
            else if (sq > max_sq) begin
                max_sq <= sq;
            end
        end
    end
end

assign  peak = peak_r;

endmodule
