module rf_nco #(
        parameter   [31:0] INCREMENT = 32'd1202590843,
        parameter   COS_FILE = "rf_cos_q15.mem"
)(
        input   wire    clk,
        input   wire    rst_n,
        output  reg     signed [15:0]   cos_out,
        output  reg     signed [15:0]   sin_out
);

reg [31:0]  phase;

(* rom_style = "block" *) reg signed [15:0]  cosine[0:1023];

wire    [9:0]   ci = phase[31:22];
wire    [9:0]   si = ci - 10'd256;

initial $readmemh(COS_FILE, cosine);

always  @(posedge clk) begin
    if (!rst_n) begin
        phase <= 0;
        cos_out <= 32767;
        sin_out <= 0;
    end
    else begin
        phase <= phase + INCREMENT;
        cos_out <= cosine[ci];
        sin_out <= cosine[si];
    end
end

endmodule
