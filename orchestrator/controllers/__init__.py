"""Controller layer for the orchestrator service.

Controllers are thin HTTP adapters: they translate HTTP <-> the Orchestrator and hold NO business
logic of their own (Controller -> Orchestrator -> Services). The integration logic lives on the
Orchestrator.
"""
