# Arcane Scroll — Progress Log

A public, high-level record of how the project is coming along — newest first. Detailed design
notes live elsewhere; this is the "follow along" view.

## The idea in one line

A compact, **locally-run** language model proposes the *creative* parts of a character; a
**deterministic engine** owns all the *rules and arithmetic* and validates every result.
Creativity and correctness in separate lanes, delivered as a small self-contained HTTP service
that the *Arcane Desk* web app consumes.

---

## Log

### Building the service
- Standing up the HTTP API and the data layer behind it.

### Generation — complete & validated
- The model now makes **every creative choice** a character needs — identity and personality,
  proficiencies, ability priorities, spells, class features, advancement options, and starting
  gear — and each choice is **valid by construction** thanks to constrained decoding plus a
  deterministic repair/validation pass.
- Covered the full breadth of the rules surface, single-class and multi-class, across levels.
- Separate **narrative generation** (physical description, personality, and a short backstory)
  proven — fast, varied, and grounded in the character.

### Foundations — proven
- Chose a **compact model that runs entirely on local hardware** (no external AI APIs) and proved
  the core principle: the model chooses, code computes.
- Built a **strict validator** and a locked **output contract**, with an objective way to score
  any generated result.
- Established the key lesson early: correctness has to be **engineered** (constrained generation
  + deterministic checks), not hoped for from the model alone.

---

*This log is intentionally high-level. If you'd like to know more about the approach, reach out via
GitHub — see the README.*
