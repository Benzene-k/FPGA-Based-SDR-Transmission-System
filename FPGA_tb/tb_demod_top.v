`timescale 1ns/1ps

module tb_demod_top;

    parameter N       = 4096;
    parameter W       = 16;
    parameter STEP    = 32'h0000_1000;
    parameter PHASE_W = 28;

    reg               clk = 0;
    reg               rst_n = 0;
    reg               sym_start = 0;
    reg  signed [W-1:0] rx_i = 0;
    reg  signed [W-1:0] rx_q = 0;
    reg               rx_valid = 0;
    wire              bit_out;
    wire              bit_valid;

    demod_top #(
        .N(N), .W(W), .DDS_LAT(3), .STEP(STEP)
    ) dut (
        .clk       (clk),
        .rst_n     (rst_n),
        .sym_start (sym_start),
        .rx_i      (rx_i),
        .rx_q      (rx_q),
        .rx_valid  (rx_valid),
        .bit_out   (bit_out),
        .bit_valid (bit_valid)
    );

    always #5 clk = ~clk;

    real K;
    real phase;
    real inc;
    real angle;
    integer n;
    reg [7:0] cos8;
    reg [7:0] sin8;
    reg [7:0] neg_sin8;
    integer errors;
    integer wait_cnt;

    task send_symbol;
        input is_bit1;
        integer is_bit1;
        begin
            @(negedge clk);
            sym_start = 1'b1;
            rx_valid  = 1'b1;
            phase     = 0.0;
            inc       = 0.0;
            @(negedge clk);
            sym_start = 1'b0;

            for (n = 0; n < N; n = n + 1) begin
                phase = phase + inc;
                inc   = inc   + STEP;
                angle = K * phase;
                cos8  = $rtoi(127.0 * $cos(angle));
                sin8  = $rtoi(127.0 * $sin(angle));
                neg_sin8 = -sin8;
                rx_i = {{8{cos8[7]}}, cos8};
                if (is_bit1)
                    rx_q = {{8{sin8[7]}}, sin8};
                else
                    rx_q = {{8{neg_sin8[7]}}, neg_sin8};
                @(negedge clk);
            end
            rx_valid = 1'b0;
        end
    endtask

    task wait_result;
        output ok;
        begin
            wait_cnt = 0;
            while (!bit_valid && wait_cnt < 100000) begin
                @(negedge clk);
                wait_cnt = wait_cnt + 1;
            end
            ok = bit_valid;
        end
    endtask

    reg result_ok;

    initial begin
        K      = 2.0 * 3.14159265358979 / (2.0 ** PHASE_W);
        errors = 0;

        rst_n     = 0;
        rx_valid  = 0;
        sym_start = 0;
        repeat (20) @(negedge clk);
        rst_n = 1;
        repeat (10) @(negedge clk);

        $display("=== Test bit 1 (positive chirp) ===");
        send_symbol(1);
        wait_result(result_ok);
        if (result_ok) begin
            if (bit_out === 1'b1)
                $display("PASS: bit_out = 1");
            else begin
                $display("FAIL: bit_out = %b, expected 1", bit_out);
                errors = errors + 1;
            end
        end else begin
            $display("FAIL: Timeout waiting for bit_valid");
            errors = errors + 1;
        end

        repeat (50) @(negedge clk);

        $display("=== Test bit 0 (negative chirp) ===");
        send_symbol(0);
        wait_result(result_ok);
        if (result_ok) begin
            if (bit_out === 1'b0)
                $display("PASS: bit_out = 0");
            else begin
                $display("FAIL: bit_out = %b, expected 0", bit_out);
                errors = errors + 1;
            end
        end else begin
            $display("FAIL: Timeout waiting for bit_valid");
            errors = errors + 1;
        end

        repeat (50) @(negedge clk);

        if (errors == 0)
            $display("\n=== ALL TESTS PASSED ===");
        else
            $display("\n=== %0d TESTS FAILED ===", errors);

        $finish;
    end

    initial begin
        #50000000;
        $display("ERROR: Simulation global timeout");
        $finish;
    end

endmodule
