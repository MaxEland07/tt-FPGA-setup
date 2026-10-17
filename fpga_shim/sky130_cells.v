// FPGA stand-ins for the Sky130 standard cells that some Tiny Tapeout designs instantiate by name
// (ring oscillators, delay chains). Each cell becomes one iCE40 lookup table, kept as written so
// synthesis does not merge or remove it. ttfpga.py adds this file when a design uses sky130 cells.
//
// SB_LUT4 LUT_INIT bit n is the output when {I3,I2,I1,I0} = n.
`default_nettype none

module sky130_fd_sc_hd__inv_1 (input wire A, output wire Y);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'h5555)) lut (.O(Y), .I0(A), .I1(1'b0), .I2(1'b0), .I3(1'b0));
endmodule

module sky130_fd_sc_hd__inv_2 (input wire A, output wire Y);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'h5555)) lut (.O(Y), .I0(A), .I1(1'b0), .I2(1'b0), .I3(1'b0));
endmodule

module sky130_fd_sc_hd__inv_4 (input wire A, output wire Y);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'h5555)) lut (.O(Y), .I0(A), .I1(1'b0), .I2(1'b0), .I3(1'b0));
endmodule

module sky130_fd_sc_hd__buf_1 (input wire A, output wire X);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'hAAAA)) lut (.O(X), .I0(A), .I1(1'b0), .I2(1'b0), .I3(1'b0));
endmodule

module sky130_fd_sc_hd__buf_2 (input wire A, output wire X);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'hAAAA)) lut (.O(X), .I0(A), .I1(1'b0), .I2(1'b0), .I3(1'b0));
endmodule

module sky130_fd_sc_hd__nand2_1 (input wire A, input wire B, output wire Y);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'h7777)) lut (.O(Y), .I0(A), .I1(B), .I2(1'b0), .I3(1'b0));
endmodule

module sky130_fd_sc_hd__nand2_2 (input wire A, input wire B, output wire Y);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'h7777)) lut (.O(Y), .I0(A), .I1(B), .I2(1'b0), .I3(1'b0));
endmodule

module sky130_fd_sc_hd__nor2_1 (input wire A, input wire B, output wire Y);
    (* keep *) SB_LUT4 #(.LUT_INIT(16'h1111)) lut (.O(Y), .I0(A), .I1(B), .I2(1'b0), .I3(1'b0));
endmodule
