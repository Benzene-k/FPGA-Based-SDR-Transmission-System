module chirp_mod #(
        parameter   N    = 4096,
        parameter   INC0 = 32'h0000_0000,
        parameter   STEP = 32'h0000_1000
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    sym_start,
        input   wire    enable,
        input   wire    tx_bit,
        output  wire    signed [15:0]  tx_i,
        output  wire    signed [15:0]  tx_q,
        output  wire    tx_valid,
        output  wire    sym_done
);

wire    signed [15:0]  ref_i;
wire    signed [15:0]  ref_q;
wire    ref_valid;
wire    chirp_done;

reg sym_start_d;
wire    sym_pulse = sym_start & ~sym_start_d;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) sym_start_d <= 1'b0;
    else        sym_start_d <= sym_start;
end

chirp_gen #(.N(N), .INC0(INC0), .STEP(STEP), .USE_DDS1(1)) u_chirp(
        .clk(clk),
        .rst_n(rst_n),
        .load(sym_pulse),
        .enable(enable),
        .ref_i(ref_i),
        .ref_q(ref_q),
        .ref_valid(ref_valid),
        .done(chirp_done)
);

assign  tx_i     = ref_i;
assign  tx_q     = tx_bit ? ref_q : -ref_q;
assign  tx_valid = ref_valid;
assign  sym_done = chirp_done;

endmodule
