"""Orchestrator service package.

Implements the Controller -> Orchestrator -> Services topology: thin HTTP controllers delegate to
the Orchestrator, which is the sole integrator that composes the underlying single-responsibility
services (validator, deriver, and — separately — the generator). Nothing here depends on the model:
the model is reachable only from the generator service.
"""
