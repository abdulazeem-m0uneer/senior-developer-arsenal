# CodeGraph Architecture & Reference Guide

CodeGraph builds an AST-level symbol and relationship graph using Tree-sitter, indexed locally into SQLite with Full-Text Search (FTS5).

## Core Concepts
- **AST Parsing**: Parses source files into syntax trees without invoking compilers.
- **Node Entities**: Functions, Classes, Methods, Interfaces, Enums, Endpoints, Structs.
- **Edge Relationships**:
  - `CALLS`: Function A calls Function B.
  - `IMPORTS`: Module A imports Module B.
  - `IMPLEMENTS`: Class A implements Interface B.
  - `EXTENDS`: Class A derives from Class B.

## Why CodeGraph Can Reduce Token Spend
- **Standard Exploration**: Agent greps for a keyword -> gets many file matches -> opens several full files to find the callers.
- **CodeGraph**: Agent asks the graph who calls `ProcessPayment` (`codegraph_explore`, or `codegraph_callers` on older servers) -> gets the callers with files and line numbers, without opening the files.
- **Not measured here**: this repository has no benchmark of the saving. It depends on the codebase and the question; treat any percentage as the upstream project's claim, not a result of the arsenal.
