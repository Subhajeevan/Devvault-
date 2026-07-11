---
title: DevVault
emoji: 🧠
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: A developer's AI second brain — grounded, cited RAG over your own sources.
---

# DevVault

A developer's AI second brain: ingest PDFs (text and scanned, via OCR), web pages,
and notes, then ask questions and get answers grounded in your own material — with
citations. Built with FastAPI, ChromaDB (local embeddings), and Groq/Claude.

> **This file is the Hugging Face Space config.** When you create the Space,
> replace its auto-generated `README.md` with this file's contents (the YAML
> frontmatter above is what tells Spaces to build the Dockerfile on port 7860).
> Set your `GROQ_API_KEY` as a **Secret** in the Space settings — never commit it.

See `DEPLOY.md` for full step-by-step instructions.
