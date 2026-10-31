module rf_interpolator(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    abort,
        input   wire    signed [15:0]   i_in,
        input   wire    signed [15:0]   q_in,
        input   wire    in_valid,
        output  reg     signed [15:0]   i_out,
        output  reg     signed [15:0]   q_out,
        output  reg     flow_fault
);

`include "rf_coefficients.vh"

reg [3:0]  phase;
reg pending_valid;
reg signed [15:0]  pending_i;
reg signed [15:0]  pending_q;
reg signed [15:0]  history_i[0:20];
reg signed [15:0]  history_q[0:20];

wire    signed [15:0]   incoming_i = pending_valid ? pending_i : (in_valid ? i_in : 16'sd0);
wire    signed [15:0]   incoming_q = pending_valid ? pending_q : (in_valid ? q_in : 16'sd0);
wire    signed [43:0]   tree_i[1:63];
wire    signed [43:0]   tree_q[1:63];

genvar g;

generate
for (g = 0; g < 32; g = g + 1) begin: leaves
    if (g < 21) begin: tap
        wire    signed [17:0]   c = int_coefficient(10*g+phase);
        wire    signed [15:0]   xi;
        wire    signed [15:0]   xq;
        if (g == 0) begin
            assign xi = phase == 0 ? incoming_i : history_i[0];
            assign xq = phase == 0 ? incoming_q : history_q[0];
        end
        else begin
            assign xi = phase == 0 ? history_i[g-1] : history_i[g];
            assign xq = phase == 0 ? history_q[g-1] : history_q[g];
        end
        wire    signed [33:0]   pi = c * xi;
        wire    signed [33:0]   pq = c * xq;
        assign tree_i[32+g] = {{10{pi[33]}}, pi};
        assign tree_q[32+g] = {{10{pq[33]}}, pq};
    end
    else begin
        assign tree_i[32+g] = 0;
        assign tree_q[32+g] = 0;
    end
end
for (g = 1; g < 32; g = g + 1) begin: sums
    (* use_dsp = "no" *) wire signed [43:0] sum_i = tree_i[2*g] + tree_i[2*g+1];
    (* use_dsp = "no" *) wire signed [43:0] sum_q = tree_q[2*g] + tree_q[2*g+1];
    assign tree_i[g] = sum_i;
    assign tree_q[g] = sum_q;
end
endgenerate

function signed [15:0] quantize;
    input signed [43:0] value;
    reg signed [43:0]  shifted;
    begin
        shifted = value >>> 17;
        if (shifted > 32767) quantize = 32767;
        else if (shifted < -32768) quantize = -32768;
        else quantize = shifted[15:0];
    end
endfunction

integer k;

always  @(posedge clk) begin
    if (!rst_n || abort) begin
        phase <= 0;
        pending_valid <= 0;
        pending_i <= 0;
        pending_q <= 0;
        i_out <= 0;
        q_out <= 0;
        flow_fault <= 0;
        for (k = 0; k < 21; k = k + 1) begin
            history_i[k] <= 0;
            history_q[k] <= 0;
        end
    end
    else begin
        phase <= phase == 9 ? 0 : phase + 1'b1;
        i_out <= quantize(tree_i[1]);
        q_out <= quantize(tree_q[1]);
        if (phase == 0) begin
            for (k = 20; k > 0; k = k - 1) begin
                history_i[k] <= history_i[k-1];
                history_q[k] <= history_q[k-1];
            end
            history_i[0] <= incoming_i;
            history_q[0] <= incoming_q;
            pending_valid <= pending_valid && in_valid;
            if (in_valid) begin
                pending_i <= i_in;
                pending_q <= q_in;
            end
        end
        else if (in_valid) begin
            if (pending_valid) flow_fault <= 1;
            else begin
                pending_i <= i_in;
                pending_q <= q_in;
                pending_valid <= 1;
            end
        end
    end
end

endmodule
