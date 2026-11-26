# Optional Fuzzing

Fuzz code that parses untrusted bytes or crosses a native boundary (C/C++ libraries, native bindings, decoders). Run a fuzzer only when it is installed; otherwise write table-driven edge-case tests and say fuzzing was not run.

| Tool | Use when | Command |
| :--- | :--- | :--- |
| libFuzzer | C/C++ target with a function taking `(const uint8_t*, size_t)` | `clang++ -g -fsanitize=fuzzer,address harness.cc -o fuzz && ./fuzz -max_total_time=300 corpus/` |
| AFL++ | Program that reads input from a file or stdin | `afl-fuzz -i seeds -o out -- ./target @@` |
| honggfuzz | Same as AFL++, when its persistent mode is easier to wire | `honggfuzz -i seeds -- ./target ___FILE___` |

Every crash becomes a regression test with the crashing input saved as a fixture, written before the fix.
