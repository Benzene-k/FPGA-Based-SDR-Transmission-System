module board_reset_epoch #(
        parameter   [31:0] SESSION_BASE = 32'had000100
)(
        input   wire    clk,
        input   wire    button_n,
        output  wire    core_rst_n,
        output  wire    [31:0]  session_id,
        output  wire    exhausted
);

(* ASYNC_REG="TRUE" *) reg [2:0]  reset_release = 0;
reg [7:0]   epoch = 0;
reg reset_seen = 1, epoch_exhausted = 0;

always  @(posedge clk or negedge button_n)
    if (!button_n) reset_release <= 0;
    else        reset_release <= {reset_release[1:0], 1'b1};

always  @(posedge clk) begin
    if (!reset_release[2] && !reset_seen) begin
        reset_seen <= 1;
        if (epoch == 255) epoch_exhausted <= 1;
        else        epoch <= epoch + 1'b1;
    end
    else if (reset_release[2]) reset_seen <= 0;
end

assign  core_rst_n = reset_release[2] && !epoch_exhausted;
assign  session_id = SESSION_BASE + {24'd0, epoch};
assign  exhausted = epoch_exhausted;

endmodule
