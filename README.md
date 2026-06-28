# Arcane Scroll

*An AI-powered brain for tabletop RPGs — starting with character creation.*

## What it does today

Arcane Scroll turns a single sentence — *"a high elf wizard, level 5"*, or even just a name and
a class — into a **complete, rules-correct tabletop RPG character sheet**. Ability scores,
proficiencies, saving throws, hit points, spells, starting equipment: a full sheet, ready to
play, generated in seconds.

The hard part was never writing words — language models do that easily. The hard part is being
*right*. A character sheet obeys hundreds of interlocking rules, and a model that "mostly" gets
the maths right is a model you can't trust. So Arcane Scroll is built around a deliberate
division of labour between what an AI is genuinely good at and what should never be left to
chance. Getting that line in exactly the right place took a fair amount of head-scratching — and
it's the part of this project I'm quietly rather proud of. The payoff is output that is both
*imaginative* and *correct*, every single time.

## Under the hood (the short version)

- A **compact language model, fine-tuned** specifically for this task and run **entirely on
  local hardware** — no third-party AI APIs, no per-request fees, nothing leaving the building.
- A **deterministic engine** that owns everything a model shouldn't: the rules, the arithmetic,
  the validation. Creativity and correctness, kept firmly in their own lanes.
- Delivered as a small, self-contained service that the *Arcane Desk* web app consumes.

It all runs on my own **homelab** — a single, modest machine quietly doing the work.

## Where it's going

Character creation is just the first tool on the shelf. The bigger ambition is an **AI-powered
brain for the tabletop**: a growing toolkit for both game masters and players — generators,
references, assistants, and on-hand companions that take the busywork out of preparing and
running a campaign, so everyone can spend more time at the actual table. This is step one of
many.

## Get in touch

I'm building this in the open, and I'm genuinely **open to ideas, feedback, and suggestions**.
If there's a feature you'd love, a rules edge case I've missed, or you just want to nerd out
about RPGs and local AI, reach out through **GitHub** — [@EderBorella](https://github.com/EderBorella).
Issues and discussions are very welcome.

---

© 2026 Eder Borella. Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE) —
free to use for any non-commercial purpose.
