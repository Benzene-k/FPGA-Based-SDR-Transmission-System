`timescale 1ns/1ps

module tb_sdr_loopback;

    parameter N       = 4096;
    parameter W       = 16;
    parameter STEP    = 32'h0000_1000;
    parameter DDS_LAT = 3;

    reg        clk = 0;
    reg        rst_n = 0;
    reg        ext_start = 0;
    wire       uart_tx_pin;
    wire [3:0] led;

    sdr_top #(
        .N(N), .W(W), .DDS_LAT(DDS_LAT), .STEP(STEP)
    ) dut (
        .clk        (clk),
        .rst_n      (rst_n),
        .ext_start  (ext_start),
        .uart_tx_pin(uart_tx_pin),
        .led        (led)
    );

    always #5 clk = ~clk;

    reg [15:0] err_sum;
    reg [15:0] bit_sum;
    reg [3:0]  pass_cnt;
    reg [3:0]  fail_cnt;
    reg [7:0]  seq_last;
    reg        ber_valid_d;

    always @(posedge clk) ber_valid_d <= dut.ber_valid;

    wire ber_rise = dut.ber_valid & ~ber_valid_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pass_cnt <= 4'd0;
            fail_cnt <= 4'd0;
            err_sum  <= 16'd0;
            bit_sum  <= 16'd0;
            seq_last <= 8'd0;
        end else begin
            if (ber_rise) begin
                seq_last <= dut.tx_frame_seq;
                err_sum  <= dut.err_count;
                bit_sum  <= dut.bit_count;
                if (dut.crc_ok && dut.err_count == 16'd0) begin
                    pass_cnt <= pass_cnt + 4'd1;
                end else begin
                    fail_cnt <= fail_cnt + 4'd1;
                end
            end
        end
    end

    integer i;

    initial begin
        rst_n     = 0;
        ext_start = 0;
        repeat (20) @(negedge clk);
        rst_n = 1;
        repeat (10) @(negedge clk);

        ext_start = 1;
        @(negedge clk);
        ext_start = 0;

        i = 0;
        while (pass_cnt < 4 && fail_cnt < 4 && i < 200_000_000) begin
            @(posedge clk);
            i = i + 1;
        end

        $display("=== Loopback Test Result ===");
        $display("Pass frames: %0d", pass_cnt);
        $display("Fail frames: %0d", fail_cnt);
        $display("Last frame: seq=%0d bit_count=%0d err_count=%0d crc_ok=%b",
                 seq_last, bit_sum, err_sum, dut.crc_ok);

        if (pass_cnt >= 4)
            $display("=== ALL TESTS PASSED ===");
        else
            $display("=== TESTS FAILED ===");

        $finish;
    end

    initial begin
        #200_000_000;
        $display("ERROR: Global timeout reached");
        $finish;
    end

endmodule
