module ber_counter #(
        parameter   SEED = 15'h7FFF
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    sync_found,
        input   wire    bit_in,
        input   wire    bit_valid,
        output  reg     [15:0]   err_count,
        output  reg     [15:0]   bit_count,
        output  reg     result_valid
);

reg [5:0]  idx;
reg [15:0] err_acc;
reg [15:0] cnt_acc;

wire    prbs_bit;
wire    prbs_en = (idx >= 6'd2 && idx <= 6'd33);

prbs_gen #(.SEED(SEED)) u_prbs(
        .clk(clk),
        .rst_n(rst_n),
        .en(prbs_en),
        .load(sync_found),
        .seed_val(SEED),
        .bit_out(prbs_bit)
);

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        idx          <= 6'd0;
        err_acc      <= 16'd0;
        cnt_acc      <= 16'd0;
        err_count    <= 16'd0;
        bit_count    <= 16'd0;
        result_valid <= 1'b0;
    end
    else begin
        result_valid <= 1'b0;

        if (sync_found) begin
            idx     <= 6'd0;
            err_acc <= 16'd0;
            cnt_acc <= 16'd0;
        end
        else if (bit_valid) begin
            if (idx >= 6'd2 && idx <= 6'd33) begin
                cnt_acc <= cnt_acc + 16'd1;
                if (bit_in != prbs_bit) err_acc <= err_acc + 16'd1;
            end
            if (idx == 6'd49) begin
                err_count    <= err_acc;
                bit_count    <= cnt_acc;
                result_valid <= 1'b1;
                idx          <= 6'd0;
            end
            else begin
                idx <= idx + 6'd1;
            end
        end
    end
end

endmodule
