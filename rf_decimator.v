module rf_decimator(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    signed [17:0]   i_in,
        input   wire    signed [17:0]   q_in,
        output  reg     signed [15:0]   i_out,
        output  reg     signed [15:0]   q_out,
        output  reg     out_valid
);

`include "rf_coefficients.vh"

reg signed [17:0]  history_i[0:209];
reg signed [17:0]  history_q[0:209];
reg [3:0]  phase;
reg [7:0]  filled;
reg signed [43:0]  acc_i;
reg signed [43:0]  acc_q;
wire    signed [43:0]   tree_i[1:63];
wire    signed [43:0]   tree_q[1:63];

genvar g;

generate
for (g = 0; g < 32; g = g + 1) begin: leaves
    if (g < 21) begin: tap
        wire    signed [17:0]   c = dec_coefficient(10*g+phase);
        wire    signed [17:0]   xi = (10*g+phase < 201) ? history_i[10*g+2*phase] : 18'sd0;
        wire    signed [17:0]   xq = (10*g+phase < 201) ? history_q[10*g+2*phase] : 18'sd0;
        wire    signed [35:0]   pi = c * xi;
        wire    signed [35:0]   pq = c * xq;
        assign tree_i[32+g] = {{8{pi[35]}}, pi};
        assign tree_q[32+g] = {{8{pq[35]}}, pq};
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

wire    signed [43:0]   total_i = acc_i + tree_i[1];
wire    signed [43:0]   total_q = acc_q + tree_q[1];

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
    if (rst_n) begin
        for (k = 209; k > 0; k = k - 1) begin
            history_i[k] <= history_i[k-1];
            history_q[k] <= history_q[k-1];
        end
        history_i[0] <= i_in;
        history_q[0] <= q_in;
    end
end

always  @(posedge clk) begin
    if (!rst_n) begin
        phase <= 0;
        filled <= 0;
        acc_i <= 0;
        acc_q <= 0;
        i_out <= 0;
        q_out <= 0;
        out_valid <= 0;
    end
    else begin
        phase <= phase == 9 ? 0 : phase + 1'b1;
        if (filled < 210) filled <= filled + 1'b1;
        out_valid <= 0;
        if (phase == 0) begin
            acc_i <= tree_i[1];
            acc_q <= tree_q[1];
        end
        else begin
            acc_i <= total_i;
            acc_q <= total_q;
            if (phase == 9 && filled >= 210) begin
                i_out <= quantize(total_i);
                q_out <= quantize(total_q);
                out_valid <= 1;
            end
        end
    end
end

endmodule
