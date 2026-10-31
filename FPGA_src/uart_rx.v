module uart_rx #(
        parameter   CLK_FREQ = 50_000_000,
        parameter   BAUD = 115_200
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    rx,
        output  reg     [7:0]   data,
        output  reg     valid,
        output  reg     framing_error
);

localparam  BIT_CYCLES = CLK_FREQ / BAUD;
localparam  CW = $clog2(BIT_CYCLES);
localparam  IDLE = 0, START = 1, DATA = 2, STOP = 3, WAIT_HIGH = 4;

(* ASYNC_REG="TRUE" *) reg rx_meta, rx_sync;
reg [2:0]   state, bit_index;
reg [CW-1:0]    timer;
reg [7:0]   shift;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        rx_meta <= 1'b1;
        rx_sync <= 1'b1;
    end
    else begin
        rx_meta <= rx;
        rx_sync <= rx_meta;
    end
end

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= IDLE;
        timer <= 0;
        bit_index <= 0;
        shift <= 0;
        data <= 0;
        valid <= 0;
        framing_error <= 0;
    end
    else begin
        valid <= 0;
        framing_error <= 0;
        case (state)
            IDLE: begin
                timer <= 0;
                if (!rx_sync) state <= START;
            end
            START: begin
                if (timer == BIT_CYCLES / 2 - 1) begin
                    timer <= 0;
                    if (!rx_sync) begin
                        bit_index <= 0;
                        state <= DATA;
                    end
                    else        state <= IDLE;
                end
                else        timer <= timer + 1'b1;
            end
            DATA: begin
                if (timer == BIT_CYCLES - 1) begin
                    timer <= 0;
                    shift[bit_index] <= rx_sync;
                    if (bit_index == 7) state <= STOP;
                    else        bit_index <= bit_index + 1'b1;
                end
                else        timer <= timer + 1'b1;
            end
            STOP: begin
                if (timer == BIT_CYCLES - 1) begin
                    timer <= 0;
                    if (rx_sync) begin
                        data <= shift;
                        valid <= 1;
                        state <= IDLE;
                    end
                    else begin
                        framing_error <= 1;
                        state <= WAIT_HIGH;
                    end
                end
                else        timer <= timer + 1'b1;
            end
            WAIT_HIGH: if (rx_sync) state <= IDLE;
            default: state <= IDLE;
        endcase
    end
end

endmodule
