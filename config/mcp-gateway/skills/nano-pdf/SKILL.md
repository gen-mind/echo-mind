---
name: nano-pdf
description: "Edit PDFs with natural-language instructions using the nano-pdf CLI"
command: "nano-pdf ${command}"
args:
  - name: command
    description: "nano-pdf subcommand and arguments"
    required: true
tags: [pdf, edit, document]
timeout: 60
max_output_bytes: 131072
---

# Nano PDF Skill

Edit PDFs with natural-language instructions using the nano-pdf CLI.

> **Prerequisite:** Requires `nano-pdf` CLI tool installed in the container.

## Overview

nano-pdf is a command-line tool for manipulating PDF files. It supports editing pages, adding text and annotations, merging and splitting documents, extracting text, and more.

## Common Subcommands

| Subcommand | Description |
|------------|-------------|
| `edit <file> --instruction "<text>"` | Edit PDF with natural-language instruction |
| `merge <file1> <file2> -o <output>` | Merge multiple PDFs into one |
| `split <file> --pages <range> -o <output>` | Extract page range into new PDF |
| `extract-text <file>` | Extract all text from a PDF |
| `info <file>` | Show PDF metadata and page count |
| `add-text <file> --text "<text>" --page <n> --x <x> --y <y>` | Add text at a position |
| `rotate <file> --pages <range> --angle <deg> -o <output>` | Rotate pages |
| `compress <file> -o <output>` | Compress a PDF to reduce file size |

## Page Range Syntax

| Range | Description |
|-------|-------------|
| `1` | Single page |
| `1-5` | Pages 1 through 5 |
| `1,3,5` | Specific pages |
| `1-3,7-9` | Multiple ranges |

## Examples

**Edit a PDF with natural language:**
```
command: "edit report.pdf --instruction \"Remove the header from all pages\""
```

**Merge two PDFs:**
```
command: "merge part1.pdf part2.pdf -o combined.pdf"
```

**Split out specific pages:**
```
command: "split document.pdf --pages 1-5 -o first-five.pdf"
```

**Extract text from a PDF:**
```
command: "extract-text contract.pdf"
```

**Add text to a page:**
```
command: "add-text form.pdf --text \"APPROVED\" --page 1 --x 400 --y 50 -o stamped.pdf"
```

**Get PDF info:**
```
command: "info report.pdf"
```
