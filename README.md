# Smart Repetition Agent

An AI-powered spaced repetition system that reads from your Obsidian vault, generates contextual questions using Claude, and uses FSRS (Free Spaced Repetition Scheduler) for optimal review scheduling. Learning progress is recorded on-chain for verifiable proof of knowledge.

## What It Does

```
Your Obsidian Notes → AI Generates Questions → You Answer → AI Scores Your Answer → FSRS Schedules Reviews → Blockchain Proves You Learned
```

**The Problem:** Traditional flashcard apps make you write your own cards, use outdated algorithms, quiz surface-level facts, and can't prove you actually learned anything.

**The Solution:** This agent reads your actual course notes, generates progressively harder questions (lesson → chapter → course → cross-course) using Claude API, scores your free-text answers, schedules reviews using state-of-the-art FSRS algorithm (20-30% more efficient than Anki's SM-2), and records your learning on Ethereum for verifiable credentials.

## Features

- **Obsidian vault parsing** - Reads course structure from YAML configs and lesson content from markdown files
- **FSRS spaced repetition** - State-of-the-art scheduling that learns your memory patterns
- **AI question generation** - Claude API generates contextual quiz questions from your notes
- **AI answer assessment** - Claude API scores your free-text answers (1-4 scale) with explanations
- **Dynamic prompt building** - Question difficulty adapts to your mastery level (consolidation levels 1-4)
- **Progressive consolidation** - Questions evolve from basic recall to cross-course synthesis as you master material
- **Review sessions** - Structured study sessions with stats tracking (duration, rating distribution)
- **JSON persistence** - Review state (FSRS card data) saved between sessions
- **CLI interface** - Terminal commands for status, review, and stats
- **Telegram bot interface** - Daily review reminders and inline interaction
- **On-chain proof of knowledge** - Review proofs submitted to Ethereum Sepolia via oracle pattern
- **Credential NFTs** - Mint verifiable learning credentials on completion

## Project Structure

```
obsidian-knowledge-agent/
├── agent/
│   └── src/
│       ├── course_parser/
│       │   ├── __init__.py
│       │   ├── parser.py          # Reads vault, extracts content
│       │   └── models.py          # Lesson, Chapter, Course dataclasses
│       ├── scheduler/
│       │   ├── __init__.py
│       │   ├── review.py          # ReviewItem, SchedulerManager, ReviewSession,
│       │   │                      # SessionStats, persistence (save/load)
│       │   └── cli.py             # CLI interface (status, review, stats)
│       └── ai/
│           ├── __init__.py
│           ├── question_generator.py  # Claude API question generation
│           ├── answer_assessor.py     # Claude API answer scoring
│           └── prompt_builder.py      # Dynamic prompts based on card state
├── bot/
│   └── telegram_bot.py            # Telegram interface with daily reminders
├── contracts/
│   ├── ProofOfKnowledge.sol       # On-chain review proof storage
│   ├── LearningOracle.sol         # Off-chain → on-chain bridge
│   └── CredentialNFT.sol          # ERC-721 learning credentials
├── data/
│   ├── courses.json               # Parsed course structure
│   └── review_state.json          # FSRS card states (persisted)
├── .gitignore
└── README.md
```

## Obsidian Vault Structure

The agent reads courses from your Obsidian vault:

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
```

### Lesson Frontmatter

Each `.md` file can include optional frontmatter:

```markdown
---
date: 2024-01-15
tags: [topic1, topic2]
difficulty: intermediate
estimated_review_minutes: 25
lesson_number: 1
---

# Lesson Content Here
```

## Installation

```bash
# Clone the repository
git clone https://github.com/dassmod/obsidian-knowledge-agent.git
cd obsidian-knowledge-agent

# Install dependencies
pip install pyyaml py-fsrs anthropic python-telegram-bot web3

# Set your Claude API key
export ANTHROPIC_API_KEY="sk-ant-api03-your-key-here"

# Configure vault path in agent/src/scheduler/cli.py
VAULT_COURSES_PATH = Path("/path/to/your/vault/02 Source Material/Courses")
```

## Usage

### Parse Your Courses

```bash
cd agent/src/course_parser
python parser.py
```

### CLI Commands

```bash
# Check what's due
python -m agent.src.scheduler.cli status

# Start a review session (AI-powered questions)
python -m agent.src.scheduler.cli review

# View overall stats
python -m agent.src.scheduler.cli stats
```

### Review Session Flow

```
$ python -m agent.src.scheduler.cli review

--- Card 1 of 7 ---
  Lesson:    Lesson 01 - Decentralized Training Protocols
  Chapter:   Foundations of Distributed AI
  Course:    Engineering Decentralized AI Systems
  Remaining: 7

  Question: Why does gradient staleness affect convergence in
            asynchronous distributed training?
  Hint:     Think about what happens when workers use outdated parameters.

  Your answer: Gradient staleness happens when workers compute gradients
  using old model parameters. By the time a stale gradient is applied,
  the model has already moved, so the update pushes it in a slightly
  wrong direction, slowing convergence.

  Score:          3/4
  Explanation:    Good understanding of the core mechanism. Missing the
                  connection to learning rate adjustment as a mitigation.
  Correct answer: Stale gradients are computed on outdated parameters...

--- Session Complete ---
  Reviewed: 7
  Duration: 342.5s
  Ratings:  {'again': 1, 'hard': 1, 'good': 4, 'easy': 1}
```

## How Progressive Consolidation Works

As you master material, questions get progressively harder:

| Level | Stability | Scope | Example Question |
|-------|-----------|-------|------------------|
| 1 | < 5 days | Single lesson recall | "What is gradient staleness?" |
| 2 | 5-19 days | Why/how reasoning | "Compare synchronous vs asynchronous SGD" |
| 3 | 20-59 days | Cross-lesson connections | "Design a Byzantine-fault-tolerant training system" |
| 4 | 60+ days | Cross-course synthesis | "How would you implement the oracle pattern in Solidity?" |

Promotion is automatic based on FSRS stability - as your memory strengthens, the agent challenges you with deeper questions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Off-chain (Your Computer)                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Obsidian Vault                                             │
│       ↓                                                     │
│  Course Parser (models.py, parser.py)                       │
│       ↓                                                     │
│  courses.json                                               │
│       ↓                                                     │
│  FSRS Scheduler (review.py)                                 │
│   ├── ReviewItem (lesson ↔ FSRS card bridge)                │
│   ├── SchedulerManager (scheduling logic)                   │
│   ├── ReviewSession (study session orchestration)           │
│   └── Persistence (save/load to JSON)                       │
│       ↓                                                     │
│  AI Layer (question_generator.py, answer_assessor.py)       │
│   ├── QuestionGenerator (Claude API → quiz questions)       │
│   ├── AnswerAssessor (Claude API → answer scoring)          │
│   └── PromptBuilder (dynamic prompts by consolidation level)│
│       ↓                                                     │
│  Interface Layer (interface-agnostic)                        │
│   ├── CLI (cli.py)                                          │
│   └── Telegram Bot (telegram_bot.py)                        │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ web3.py (oracle pattern)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 On-chain (Ethereum Sepolia)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ProofOfKnowledge.sol  →  LearningOracle.sol  →  NFT.sol    │
│       ↓                        ↓                    ↓       │
│  Review hashes            Streak/score          Credential  │
│  (what you studied)       validation            minting     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Why FSRS Over SM-2?

FSRS (Free Spaced Repetition Scheduler) replaced SM-2 as the default in Anki:

| Feature | SM-2 (Anki legacy) | FSRS |
|---------|---------------------|------|
| Efficiency | Baseline | 20-30% fewer reviews |
| Personalization | Fixed intervals | Learns your memory patterns |
| Accuracy | Good | 99.6% superiority in benchmarks |

FSRS uses machine learning to model your individual forgetting curve, scheduling reviews at the optimal moment for retention.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Vault Parser | pathlib, PyYAML, regex |
| Spaced Repetition | py-fsrs (FSRS algorithm) |
| AI Question Generation | Claude API (Anthropic) |
| AI Answer Assessment | Claude API (Anthropic) |
| CLI Interface | sys.argv, built-in Python |
| Telegram Interface | python-telegram-bot |
| Blockchain | Solidity, Foundry, Sepolia testnet |
| Bridge | web3.py (oracle pattern) |

## Design Principles

- **Interface-agnostic core** - `ReviewSession` and `SchedulerManager` work identically whether driven by CLI, Telegram, or any future frontend
- **Oracle pattern** - Expensive AI compute happens off-chain; only proofs and results go on-chain
- **Progressive difficulty** - Questions adapt to your mastery level automatically
- **Persistence** - All FSRS card states survive between sessions via JSON serialization

## License

MIT

## Author

Das - Building at the intersection of AI agents and blockchain.
