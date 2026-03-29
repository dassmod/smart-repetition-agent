# Smart Repetition Agent

An AI-powered spaced repetition system that reads from your Obsidian vault, generates contextual questions using Claude, and uses FSRS (Free Spaced Repetition Scheduler) for optimal review scheduling. Learning progress is recorded on-chain for verifiable proof of knowledge.

## What It Does

```
Your Obsidian Notes → AI Generates Questions → You Answer → FSRS Schedules Reviews → Blockchain Proves You Learned
```

**The Problem:** Traditional flashcard apps make you write your own cards, use outdated algorithms, and can't prove you actually learned anything.

**The Solution:** This agent reads your actual course notes, generates smart questions that get progressively harder (lesson → chapter → course → cross-course), schedules reviews using state-of-the-art FSRS algorithm (20-30% more efficient than Anki's SM-2), and records your learning on Ethereum for verifiable credentials.

## Features

### Implemented
- [x] Course structure parsing from Obsidian vault
- [x] YAML configuration for chapters and lessons
- [x] Markdown content extraction with frontmatter
- [x] Heading extraction for content structure
- [x] Data models (Lesson, Chapter, Course)
- [x] JSON export for FSRS integration

### Coming Soon
- [ ] FSRS spaced repetition scheduling
- [ ] Claude-powered question generation
- [ ] Answer assessment with scoring
- [ ] Progressive consolidation (lesson → chapter → course)
- [ ] Telegram bot interface
- [ ] On-chain proof of knowledge (Ethereum/Sepolia)
- [ ] Web dashboard

## Project Structure

```
obsidian-knowledge-agent/
├── agent/
│   └── src/
│       └── course_parser/
│           ├── __init__.py
│           ├── parser.py      # Reads vault, extracts content
│           └── models.py      # Lesson, Chapter, Course classes
├── data/
│   └── courses.json           # Parsed course data for FSRS
├── contracts/                  # (Coming) Solidity smart contracts
│   ├── ProofOfKnowledge.sol
│   ├── LearningOracle.sol
│   └── CredentialNFT.sol
├── bot/                        # (Coming) Telegram interface
└── README.md
```

## Obsidian Vault Structure

The agent reads courses from your Obsidian vault. Structure your courses like this:

```
Your-Vault/
└── 02 Source Material/
    └── Courses/
        └── Your Course Name/
            ├── _course.yaml              # Required: defines structure
            ├── Lesson 01 - Topic.md
            ├── Lesson 02 - Topic.md
            └── ...
```

### `_course.yaml` Format

```yaml
title: "Your Course Title"
description: "Optional description"
chapters:
  - name: "Chapter 1 Name"
    lessons:
      - "Lesson 01 - Topic"      # Must match filename (without .md)
      - "Lesson 02 - Topic"
  - name: "Chapter 2 Name"
    lessons:
      - "Lesson 03 - Topic"
      - "Lesson 04 - Topic"
```

### Lesson Frontmatter

Each lesson `.md` file can include optional frontmatter:

```markdown
---
date: 2024-01-15
tags: [topic1, topic2, topic3]
difficulty: intermediate        # beginner, intermediate, advanced
estimated_review_minutes: 25
lesson_number: 1
---

# Lesson Title

Your lesson content here...

## Section 1

Content...

## Section 2

More content...
```

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/obsidian-knowledge-agent.git
cd obsidian-knowledge-agent

# Install dependencies
pip install pyyaml

# Configure vault path
# Edit agent/src/course_parser/parser.py line 27:
VAULT_PATH = Path("/path/to/your/obsidian/vault")
```

## Usage

### Parse Your Courses

```bash
cd agent/src/course_parser
python parser.py
```

Output:
```
==================================================
Smart Repetition Agent - Course Parser
==================================================

Scanning: /path/to/vault/02 Source Material/Courses

Found: Decentralized AI

========================================
Course: Decentralized AI
========================================
  Total chapters: 1
  Total lessons: 6
  Total words: 15420

  Chapter: Foundations of Distributed AI
    Lessons: 6
    Words: 15420

      ✓ Lesson 01 - Decentralized Training Protocols
        Words: 2847
        Headings: 23
        Difficulty: intermediate

Saved 1 courses to data/courses.json

==================================================
Total courses: 1
Output saved to: data/courses.json
==================================================
```

### JSON Output

The parser generates `data/courses.json` with this structure:

```json
[
  {
    "title": "Decentralized AI",
    "path": "/path/to/course",
    "description": "",
    "total_lessons": 6,
    "total_words": 15420,
    "chapters": [
      {
        "name": "Foundations of Distributed AI",
        "lesson_count": 6,
        "total_words": 15420,
        "lessons": [
          {
            "name": "Lesson 01 - Decentralized Training Protocols",
            "chapter": "Foundations of Distributed AI",
            "word_count": 2847,
            "difficulty": "intermediate",
            "tags": ["decentralized-ai", "distributed-training"],
            "consolidation_level": 1,
            "headings": [
              {"level": 1, "text": "Decentralized Training Protocols"},
              {"level": 2, "text": "Overview"}
            ]
          }
        ]
      }
    ]
  }
]
```

## How Progressive Consolidation Works

The agent doesn't just quiz you on isolated facts. As you master material, questions get progressively harder:

| Level | Scope | Example Question |
|-------|-------|------------------|
| 1 | Single Lesson | "What is gradient staleness?" |
| 2 | Chapter | "Compare synchronous vs asynchronous SGD" |
| 3 | Entire Course | "Design a Byzantine-fault-tolerant training system" |
| 4 | Cross-Course | "How would you implement the oracle pattern using Solidity?" |

The agent promotes topics to higher levels when:
- FSRS stability is high (you remember it well)
- You've scored 4/4 multiple times
- Related lessons are also mastered

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Vault Parser | pathlib, PyYAML, regex |
| Spaced Repetition | py-fsrs (FSRS algorithm) |
| Question Generation | Claude API (Anthropic) |
| Interface | python-telegram-bot |
| Blockchain | Solidity, Foundry, Sepolia testnet |
| Vector Search | ChromaDB (planned) |

## Why FSRS Over SM-2?

FSRS (Free Spaced Repetition Scheduler) is the state-of-the-art algorithm that replaced SM-2 in Anki:

| Feature | SM-2 (Anki default) | FSRS |
|---------|---------------------|------|
| Efficiency | Baseline | 20-30% fewer reviews |
| Personalization | Fixed intervals | Learns YOUR memory patterns |
| Accuracy | Good | 99.6% superiority in benchmarks |

FSRS uses machine learning to model your individual forgetting curve, scheduling reviews at the optimal moment.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Off-chain (Your Computer)                │
├─────────────────────────────────────────────────────────────┤
│  Obsidian Vault → Parser → FSRS Scheduler → Claude API      │
│       ↓              ↓           ↓              ↓           │
│  Course files    courses.json  Schedule    Questions        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   On-chain (Ethereum Sepolia)                │
├─────────────────────────────────────────────────────────────┤
│  ProofOfKnowledge.sol  →  LearningOracle.sol  →  NFT.sol    │
│       ↓                        ↓                    ↓       │
│  Note hashes              Streaks/scores      Credentials   │
└─────────────────────────────────────────────────────────────┘
```

## Contributing

This is a portfolio project built for learning. Feel free to fork and adapt for your own use.

## License

MIT

## Author

Das - Building at the intersection of AI agents and blockchain.

---
