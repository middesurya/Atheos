"""
ÆTHER-Grid Command Line Interface

Entry point for running the grid management system.
"""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from aether_grid import __version__
from aether_grid.core.config import get_config

app = typer.Typer(
    name="aether",
    help="ÆTHER-Grid: Autonomous Energy Transition & Hybrid Evolutionary Response",
    add_completion=False,
)

console = Console()


@app.command()
def version():
    """Show version information."""
    console.print(f"ÆTHER-Grid v{__version__}")


@app.command()
def config():
    """Show current configuration."""
    cfg = get_config()

    table = Table(title="ÆTHER-Grid Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Environment", cfg.environment)
    table.add_row("Log Level", cfg.log_level.value)
    table.add_row("Debug Mode", str(cfg.debug))
    table.add_row("Max Concurrent Tasks", str(cfg.orchestrator.max_concurrent_tasks))
    table.add_row("Quantum Backend", cfg.quantum.backend.value)
    table.add_row("Vector DB Type", cfg.vector_db.type.value)
    table.add_row("Audit Enabled", str(cfg.audit.enabled))

    console.print(table)


@app.command()
def simulate(
    duration: int = typer.Option(3600, help="Simulation duration in seconds"),
    time_step: int = typer.Option(60, help="Time step in seconds"),
):
    """Run grid simulation."""
    from aether_grid.simulation import GridSimulator

    async def run():
        console.print("[bold blue]Starting ÆTHER-Grid Simulation[/bold blue]")

        sim = GridSimulator(time_step_seconds=time_step)

        with console.status("[bold green]Running simulation..."):
            states = await sim.run(duration_seconds=duration)

        console.print(f"\n[bold green]Simulation complete![/bold green]")
        console.print(f"Total time steps: {len(states)}")

        # Show final state
        if states:
            final = states[-1]
            table = Table(title="Final Grid State")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total Generation", f"{final.total_generation_mw:.1f} MW")
            table.add_row("Total Load", f"{final.total_load_mw:.1f} MW")
            table.add_row("Renewable", f"{final.total_renewable_mw:.1f} MW")
            table.add_row("Frequency", f"{final.frequency_hz:.2f} Hz")
            table.add_row("Stable", str(final.is_stable))

            console.print(table)

    asyncio.run(run())


@app.command()
def agents():
    """List available agents."""
    table = Table(title="ÆTHER-Grid Agents")
    table.add_column("Agent", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Description", style="green")

    agents_info = [
        ("AnalystAgent", "analyst", "Real-time telemetry processing with semantic enrichment"),
        ("RiskAgent", "risk", "Security monitoring and threat detection"),
        ("ExecutionAgent", "execution", "Smart grid interaction and control"),
    ]

    for name, agent_type, desc in agents_info:
        table.add_row(name, agent_type, desc)

    console.print(table)


@app.command()
def run(
    agents_enabled: Optional[str] = typer.Option(
        "all", help="Comma-separated list of agents to enable (analyst,risk,execution)"
    ),
):
    """Run the ÆTHER-Grid orchestrator."""
    from aether_grid import Orchestrator
    from aether_grid.core.agents import AnalystAgent, ExecutionAgent, RiskAgent
    from aether_grid.core.orchestrator import AgentType

    async def start_system():
        console.print("[bold blue]Starting ÆTHER-Grid System[/bold blue]")

        orchestrator = Orchestrator()

        # Register agents based on selection
        enabled = agents_enabled.lower().split(",") if agents_enabled != "all" else ["all"]

        if "all" in enabled or "analyst" in enabled:
            await orchestrator.register_agent(AnalystAgent(), AgentType.ANALYST)
            console.print("  [green]+ Analyst Agent registered[/green]")

        if "all" in enabled or "risk" in enabled:
            await orchestrator.register_agent(RiskAgent(), AgentType.RISK)
            console.print("  [green]+ Risk Agent registered[/green]")

        if "all" in enabled or "execution" in enabled:
            await orchestrator.register_agent(ExecutionAgent(), AgentType.EXECUTION)
            console.print("  [green]+ Execution Agent registered[/green]")

        await orchestrator.start()
        console.print("\n[bold green]ÆTHER-Grid is running![/bold green]")
        console.print("Press Ctrl+C to stop.\n")

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
            await orchestrator.stop()
            console.print("[green]ÆTHER-Grid stopped.[/green]")

    asyncio.run(start_system())


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
