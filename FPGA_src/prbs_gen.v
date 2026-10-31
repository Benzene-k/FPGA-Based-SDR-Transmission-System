module prbs_gen #(
        parameter   SEED = 15'h7FFF
)(
        input   wire        clk,
        input   wire        rst_n,
        input   wire        en,
        input   wire        load,
        input   wire        [14:0]   seed_val,
        output  wire        bit_out
);

reg [14:0]  sr;

wire    fb = sr[14] ^ sr[13];

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n)        sr <= SEED;
    else if (load)     sr <= (seed_val == 15'h0) ? SEED : seed_val;
    else if (en)       sr <= {sr[13:0], fb};
end

assign  bit_out = sr[14];

endmodule
