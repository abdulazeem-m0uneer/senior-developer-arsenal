#!/usr/bin/env python3
"""A JavaScript replacement text that holds a `$` token that does not mean what it says, for guard_lessons' opt-in
`replace-dollar` rule.

Usage: text = guard_replace_dollar.problem(command, entry)   # Bash: None, or the refusal text
Never raises: any error passes the command.
In `String.prototype.replace` and `replaceAll`, the replacement text is not literal: `$`` inserts the text before the
match, `$'` the text after it and `$$` becomes one `$`. A shell regex end anchor before a quote (`'^\\s*$'`) or bash
ANSI-C text (`$'\\n'`) inside a replacement silently corrupts the file being edited.
Judged: the JavaScript a Bash command runs, never the raw shell text: `node -e` / `--eval` / `-p` / `--print` code (also
inside sh -c and eval), a here-string or here-document fed to node, and a here-document written to a .js, .mjs or
.cjs file that the same command runs with node. A `.replace(` or `.replaceAll(` call is refused when
- its second argument is string literals joined by `+` (template literals without `${}` too) whose text holds `$``,
  `$'` or `$$`; or
- its second argument is a variable or an expression (not a literal, not a function) and any string literal of the
  script holds one of them: the replacement is built somewhere else (`rep(a, b)`).
Passes: a function replacement, `split(a).join(b)`, `$&` (also the `'\\\\$&'` regex-escape idiom), `$1` to `$9` and
`$<name>`, a literal that is not a replacement when every replacement of the script is a token-free literal, Python and
other programs. Comments and regex literals are skipped. The shell is read first: in double quotes and in an unquoted
here-document bash turns `$$` into its pid and `\\$` into `$` before node starts, so only single-quoted words and
quoted here-documents (`<<'EOF'`) carry a `$$` to node. Not seen: a replacement read from a file at runtime, code
built from variables, node scripts that are not in the command, a script file that a here-document writes and that
`npx tsx`, `bun` or `deno` runs, a file written by one command and run by another. A command over MAX_CHARS passes.
Known false refusal: a `.replace` of a non-string (`router.replace`, `history.replace`, `location.replace`) with a
variable second argument is refused when any literal of the script holds `$``, `$'` or `$$`.
Standard library only.
"""
import os
import re
import shlex

import guard_destructive as shell

MAX_CHARS = 100_000
MAX_NESTING = 20
NODE = frozenset(("node", "nodejs"))
METHODS = frozenset(("replace", "replaceAll"))
EVAL_FLAG = re.compile(r"^-(?:e|p|pe|ep)$|^--(?:eval|print)$")
EVAL_INLINE = re.compile(r"^--(?:eval|print)=(.*)$", re.S)
SHELL_C_FLAG = re.compile(r"^-[a-z]*c$")
JS_FILE = re.compile(r"\.[mc]?js$")
CALL = re.compile(r"\breplace(?:All)?\s*\(")
IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
NUMBER = re.compile(r"\d[\w.]*")
OPEN, CLOSE = frozenset(("(", "[", "{", "${")), frozenset((")", "]", "}"))
REGEX_AFTER_WORD = frozenset(("return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw",
                              "yield", "await", "instanceof"))
TAKES_VALUE = frozenset(("-r", "--require", "--import"))
REGEX_AFTER_PUNCT = frozenset("(,=:[!&|?{};+-*%<>~^") | {"=>", "${"}
SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
ESCAPE = re.compile(r"\\(?:x([0-9a-fA-F]{2})|u\{([0-9a-fA-F]+)\}|u([0-9a-fA-F]{4})|(\r\n|.))", re.S)
MEANING = {"$`": "inserts all the text before the match", "$'": "inserts all the text after the match",
           "$$": "becomes one `$`"}
REASON = ("A JavaScript replace text holding `{token}` {meaning}, not the characters you wrote: {where}. Pass a "
          "function ((m) => text), use s.split(a).join(b), or change the file with the Edit tool.")


class Stop(Exception):
    """The script cannot be read to the end (unbalanced quote, nesting too deep): it passes."""


def bad_token(value):
    """The first of `$``, `$'` and `$$` that a replacement of this text would act on, reading left to right; `$&`,
    `$1` to `$9` and `$<name>` are skipped whole, so `$$&` is `$$`, then a literal `&`."""
    index = 0
    while index < len(value):
        pair = value[index:index + 2]
        if pair in MEANING:
            return pair
        index += 2 if pair[:1] == "$" and pair[1:] and (pair[1] in "&<" or pair[1].isdigit()) else 1
    return None


def unescape(raw):
    """A JavaScript string body with its escapes decoded."""
    def decode(match):
        hex2, braced, hex4, other = match.groups()
        if hex2 or braced or hex4:
            return chr(min(int(hex2 or braced or hex4, 16), 0x10FFFF))
        return "" if other in ("\n", "\r\n") else SIMPLE_ESCAPES.get(other, other)
    return ESCAPE.sub(decode, raw)


def read_quoted(src, start):
    """(decoded text, index after the closing quote) of the '...' or "..." string that opens at start."""
    quote, index = src[start], start + 1
    while index < len(src) and src[index] != quote:
        if src[index] == "\n":
            raise Stop
        index += 2 if src[index] == "\\" else 1
    if index >= len(src):
        raise Stop
    return unescape(src[start + 1:index]), index + 1


def read_regex(src, start):
    """The index after the regular expression literal (and its flags) that opens at start."""
    index, in_class = start + 1, False
    while index < len(src) and (in_class or src[index] != "/"):
        if src[index] == "\n":
            raise Stop
        if src[index] == "\\":
            index += 1
        elif src[index] == "[":
            in_class = True
        elif src[index] == "]":
            in_class = False
        index += 1
    if index >= len(src):
        raise Stop
    index += 1
    while index < len(src) and (src[index].isalnum() or src[index] == "_"):
        index += 1
    return index


def regex_allowed(tokens):
    if not tokens:
        return True
    kind, value = tokens[-1]
    if value in ("+", "-") and len(tokens) > 1 and tokens[-2] == tokens[-1]:  # `i++ / 2` divides
        return False
    return value in REGEX_AFTER_PUNCT if kind == "p" else kind == "id" and value in REGEX_AFTER_WORD


def read_template(src, start, depth):
    """(tokens, index after the closing backtick): one str token, or the static parts and the code between `${ }`."""
    tokens, text, index = [], [], start + 1
    interpolated = False
    while index < len(src) and src[index] != "`":
        if src[index] == "\\":
            text.append(src[index:index + 2])
            index += 2
        elif src.startswith("${", index):
            interpolated = True
            tokens += [("part", unescape("".join(text))), ("p", "${")]
            inner, index = lex(src, index + 2, depth + 1, True)
            tokens += inner + [("p", "}")]
            text = []
        else:
            text.append(src[index])
            index += 1
    if index >= len(src):
        raise Stop
    tokens.append(("part" if interpolated else "str", unescape("".join(text))))
    return tokens, index + 1


def lex(src, index=0, depth=0, nested=False):
    """([(kind, value)], end index): kinds str (a plain string), part (a template's static text), p (punctuation),
    id, num; regex literals and comments are left out. A nested lex ends at the `}` that closes a `${`."""
    if depth > MAX_NESTING:
        raise Stop
    tokens, braces = [], 0
    while index < len(src):
        char = src[index]
        if char.isspace():
            index += 1
        elif src.startswith("//", index):
            end = src.find("\n", index)
            index = len(src) if end < 0 else end
        elif src.startswith("/*", index):
            end = src.find("*/", index + 2)
            index = len(src) if end < 0 else end + 2
        elif char in "'\"":
            text, index = read_quoted(src, index)
            tokens.append(("str", text))
        elif char == "`":
            found, index = read_template(src, index, depth)
            tokens += found
        elif char == "/" and regex_allowed(tokens):
            index = read_regex(src, index)
            tokens.append(("id", "/regex/"))
        elif IDENTIFIER.match(src, index):
            word = IDENTIFIER.match(src, index).group()
            tokens.append(("id", word))
            index += len(word)
        elif NUMBER.match(src, index):
            index = NUMBER.match(src, index).end()
            tokens.append(("num", ""))
        elif src.startswith("=>", index):
            tokens.append(("p", "=>"))
            index += 2
        else:
            if nested and char == "}" and braces == 0:
                return tokens, index + 1
            braces += (char == "{") - (char == "}")
            tokens.append(("p", char))
            index += 1
    if nested:
        raise Stop
    return tokens, index


def arguments(tokens, start):
    """The argument token lists of the call whose `(` is just before start; the call must close."""
    args, current, depth = [], [], 0
    for index in range(start, len(tokens)):
        token = tokens[index]
        kind, value = token
        if kind == "p" and depth == 0 and value in (",", ")"):
            args.append(current)
            if value == ")":
                return args
            current = []
            continue
        if kind == "p":
            depth += (value in OPEN) - (value in CLOSE)
        current.append(token)
    raise Stop


def is_function(arg):
    depth = 0
    for kind, value in arg:
        if kind == "p":
            if value == "=>" and depth == 0:
                return True
            depth += (value in OPEN) - (value in CLOSE)
    return bool(arg) and arg[0] in (("id", "function"), ("id", "async"))


def joined_literals(arg):
    """The text of an argument made only of plain string literals joined by `+`, else None."""
    if arg and len(arg) % 2 == 1 and all(kind == "str" for kind, _ in arg[::2]) and all(
            token == ("p", "+") for token in arg[1::2]):
        return "".join(value for _, value in arg[::2])
    return None


def js_problem(src):
    """The refusal text for a JavaScript source, or None."""
    tokens, _ = lex(src)
    dynamic = False
    for at, token in enumerate(tokens):
        if token != ("p", ".") or not (tokens[at + 1:at + 2] and tokens[at + 1][0] == "id"
                                       and tokens[at + 1][1] in METHODS and tokens[at + 2:at + 3] == [("p", "(")]):
            continue
        args = arguments(tokens, at + 3)
        if len(args) < 2 or is_function(args[1]):
            continue
        literal = joined_literals(args[1])
        if literal is not None:
            found = bad_token(literal)
            if found:
                return REASON.format(token=found, meaning=MEANING[found], where="it is in this replacement")
        else:
            dynamic = True
    if dynamic:
        for kind, value in tokens:
            found = bad_token(value) if kind in ("str", "part") else None
            if found:
                return REASON.format(token=found, meaning=MEANING[found], where="this script holds it in a string "
                                     "and passes a variable or an expression as a replacement")
    return None


def bash_expand(text, quotes=True):
    """The text as bash hands it on: outside single quotes `\\$` is `$` and the process id `$$` is digits, so a `$$`
    that reaches node is one the shell did not expand. quotes=False reads a here-document body, which has no quotes."""
    out, quote, index = [], None, 0
    while index < len(text):
        char, pair = text[index], text[index:index + 2]
        if quote == "'":
            quote = None if char == "'" else quote
            out.append(char)
            index += 1
        elif pair == "\\$":
            out.append("$")
            index += 2
        elif char == "\\":
            out.append(pair)
            index += 2
        elif pair == "$$":
            out.append("0")
            index += 2
        else:
            if quotes and char in "'\"" and quote in (None, char):
                quote = None if quote else char
            out.append(char)
            index += 1
    return "".join(out)


def drop_comments(text):
    """The text without shell comments: from an unquoted `#` that starts a word to the end of its line. Quotes are
    tracked across lines, so a `#` inside a quoted script stays."""
    out, quote, index = [], None, 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'":
            out.append(text[index:index + 2])
            index += 2
            continue
        if quote is None and char == "#" and (index == 0 or text[index - 1] in " \t\n"):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        if char in "'\"" and quote in (None, char):
            quote = None if quote else char
        out.append(char)
        index += 1
    return "".join(out)


def words(text):
    """Shell words with quotes removed and operators as words of their own; backticks are kept (JavaScript template
    literals). Never raises."""
    lexer = shlex.shlex(bash_expand(text).replace("\\\n", " "), posix=True, punctuation_chars=shell.PUNCTUATION)
    lexer.whitespace, lexer.whitespace_split, lexer.commenters = " \t\r", True, ""
    found = []
    try:
        found.extend(lexer)
    except ValueError:  # an unbalanced quote: what was read before it still counts
        pass
    return found


def runs(text):
    """The argv of each simple command of the text."""
    found, argv = [], []
    for word in words(text) + [";"]:
        if word and set(word) <= shell.SEPARATORS:
            if argv:
                found.append(argv)
            argv = []
        else:
            argv.append(word)
    return found


def heredocs(command):
    """(the command without here-document bodies, [(the line that opens it, its body)]); the body of an unquoted
    here-document is expanded by the shell, so it is read as bash hands it on."""
    lines, kept, found, index = command.split("\n"), [], [], 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        for match in shell.HEREDOC_RE.finditer(line):
            word = next(group for group in match.groups() if group)
            quoted = not match.group(3) or "\\" in match.group(0)
            end = next((n for n in range(index, len(lines)) if lines[n].strip() == word), None)
            if end is not None:
                body = "\n".join(lines[index:end])
                found.append((line, body if quoted else bash_expand(body, quotes=False)))
                index = end + 1
                break
    return "\n".join(kept), found


def reads_stdin(args):
    """True when a node command runs the script it reads from standard input."""
    return operands(args)[:1] in ([], ["-"]) and not any(EVAL_FLAG.match(arg) for arg in args)


def here_strings(args):
    """The word after each `<<<` of a node command that runs its standard input."""
    return [args[at + 1] for at, arg in enumerate(args[:-1]) if arg == "<<<"] if reads_stdin(args) else []


def eval_sources(args):
    """The code of each -e, --eval, -p and --print of a node command."""
    found = []
    for at, arg in enumerate(args):
        inline = EVAL_INLINE.match(arg)
        if inline:
            found.append(inline.group(1))
        elif EVAL_FLAG.match(arg) and at + 1 < len(args):
            found.append(args[at + 1])
    return found


def operands(args):
    """The arguments of a command that are not options, redirections or the word after a redirection."""
    found, skip = [], False
    for word in args:
        if word and set(word) <= shell.REDIRECTION:
            skip = True
        elif skip:
            skip = False
        elif word in TAKES_VALUE:
            skip = True
        elif not word.startswith("-") or word == "-":
            found.append(word)
    return found


def written_paths(argv):
    """The files a command line writes: after > and >>, and the operands of tee."""
    found = [word for prev, word in zip(argv, argv[1:]) if prev in (">", ">>", ">|")]
    name, args = shell.program(argv)
    return found + (operands(args) if name == "tee" else [])


def runs_script(argvs, path):
    """True when a node command of the command line names the file."""
    for argv in argvs:
        name, args = shell.program(argv)
        if name in NODE and any(os.path.basename(arg) == os.path.basename(path) for arg in operands(args)):
            return True
    return False


def heredoc_is_script(line, argvs):
    """True when the here-document of this line is JavaScript node runs: fed to node as stdin, or written to a
    .js, .mjs or .cjs file the command line runs with node."""
    for argv in runs(line):
        name, args = shell.program(argv)
        if name in NODE and reads_stdin(args):
            return True
        if any(JS_FILE.search(path) and runs_script(argvs, path) for path in written_paths(argv)):
            return True
    return False


def js_sources(command, depth=0):
    """The JavaScript the command runs: node's eval code and print code, and the here-documents that are scripts."""
    stripped, docs = heredocs(command)
    argvs = runs(drop_comments(stripped))
    found = []
    for argv in argvs:
        name, args = shell.program(argv)
        if name in NODE:
            found += eval_sources(args) + here_strings(args)
        elif depth < shell.MAX_DEPTH and name in shell.SHELLS | {"eval"}:
            flag = next((i for i, arg in enumerate(args) if SHELL_C_FLAG.match(arg)), None)
            script = " ".join(args) if name == "eval" else args[flag + 1] if flag is not None and flag + 1 < len(args) else ""
            found += js_sources(script, depth + 1) if script else []
    return found + [body for line, body in docs if heredoc_is_script(line, argvs)]


def problem(command, entry=None, parse=None):
    """The refusal text for a JavaScript replacement text that holds `$`` , `$'` or `$$`, or None."""
    try:
        if not isinstance(command, str) or len(command) > MAX_CHARS or not CALL.search(command):
            return None
        for src in js_sources(command):
            try:
                text = js_problem(src)
            except Stop:
                continue
            if text:
                return text
        return None
    except Exception:  # a guard never refuses for its own fault
        return None
