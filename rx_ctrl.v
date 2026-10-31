module rx_ctrl (
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [7:0]   tx_frame_seq,
        input   wire    crc_ok,
        input   wire    ber_valid,
        input   wire    [15:0]  err_count,
        input   wire    [15:0]  bit_count,
        input   wire    uart_ready,
        output  reg     [7:0]   uart_data,
        output  reg     uart_send
);

localparam  [3:0] S_IDLE = 4'd0;
localparam  [3:0] S_B0   = 4'd1;
localparam  [3:0] S_B1   = 4'd2;
localparam  [3:0] S_B2   = 4'd3;
localparam  [3:0] S_B3   = 4'd4;
localparam  [3:0] S_B4   = 4'd5;
localparam  [3:0] S_B5   = 4'd6;
localparam  [3:0] S_B6   = 4'd7;
localparam  [3:0] S_B7   = 4'd8;

reg [3:0]  state;
reg [7:0]  seq_r;
reg [15:0] err_r;
reg [15:0] bit_r;
reg [7:0]  status_byte;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state       <= S_IDLE;
        uart_data   <= 8'd0;
        uart_send   <= 1'b0;
        seq_r       <= 8'd0;
        err_r       <= 16'd0;
        bit_r       <= 16'd0;
        status_byte <= 8'd0;
    end
    else begin
        uart_send <= 1'b0;

        case (state)
            S_IDLE: begin
                if (ber_valid) begin
                    seq_r       <= tx_frame_seq;
                    err_r       <= err_count;
                    bit_r       <= bit_count;
                    status_byte <= {7'd0, crc_ok};
                    state       <= S_B0;
                end
            end

            S_B0: begin
                if (uart_ready) begin
                    uart_data <= 8'hAA;
                    uart_send <= 1'b1;
                    state     <= S_B1;
                end
            end

            S_B1: begin
                if (uart_ready) begin
                    uart_data <= seq_r;
                    uart_send <= 1'b1;
                    state     <= S_B2;
                end
            end

            S_B2: begin
                if (uart_ready) begin
                    uart_data <= bit_r[15:8];
                    uart_send <= 1'b1;
                    state     <= S_B3;
                end
            end

            S_B3: begin
                if (uart_ready) begin
                    uart_data <= bit_r[7:0];
                    uart_send <= 1'b1;
                    state     <= S_B4;
                end
            end

            S_B4: begin
                if (uart_ready) begin
                    uart_data <= err_r[15:8];
                    uart_send <= 1'b1;
                    state     <= S_B5;
                end
            end

            S_B5: begin
                if (uart_ready) begin
                    uart_data <= err_r[7:0];
                    uart_send <= 1'b1;
                    state     <= S_B6;
                end
            end

            S_B6: begin
                if (uart_ready) begin
                    uart_data <= status_byte;
                    uart_send <= 1'b1;
                    state     <= S_B7;
                end
            end

            S_B7: begin
                if (uart_ready) begin
                    uart_data <= 8'h55;
                    uart_send <= 1'b1;
                    state     <= S_IDLE;
                end
            end

            default: state <= S_IDLE;
        endcase
    end
end

endmodule
