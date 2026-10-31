module frame_sync #(
        parameter   [7:0] SYNC_WORD = 8'hA7
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    bit_in,
        input   wire    bit_valid,
        output  reg     sync_found,
        output  reg     [5:0]   bit_idx
);

reg [7:0]  shift;
reg        armed;
reg [5:0]  idx;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        shift      <= 8'h0;
        armed      <= 1'b1;
        idx        <= 6'd0;
        sync_found <= 1'b0;
        bit_idx    <= 6'd0;
    end
    else begin
        sync_found <= 1'b0;
        if (bit_valid) begin
            shift <= {shift[6:0], bit_in};
            if (armed) begin
                if (shift == SYNC_WORD) begin
                    sync_found <= 1'b1;
                    armed      <= 1'b0;
                    idx        <= 6'd0;
                end
            end
            else begin
                bit_idx <= idx;
                if (idx == 6'd49) begin
                    armed <= 1'b1;
                    idx   <= 6'd0;
                end
                else begin
                    idx <= idx + 6'd1;
                end
            end
        end
    end
end

endmodule
