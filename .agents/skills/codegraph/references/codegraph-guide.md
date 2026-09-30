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

## Why CodeGraph Drastically Reduces Token Spend
- **Standard Exploration**: Agent greps for keyword -> gets 45 file matches -> opens 10 full files -> consumes 20,000+ tokens.
- **CodeGraph**: Agent calls `codegraph_callers("ProcessPayment")` -> gets exact 4-line JSON tree of caller files and line numbers -> consumes < 250 tokens.
- **Net Token Reduction**: Up to **85-90% token reduction** on code navigation and refactoring impact assessment.
